"""Pipeline de retrato "calidad": fondo fuera + rasgos marcados + líneas.

Ruta por defecto (la del laboratorio, la que dibuja el MG400):

    YuNet (rostro) + U2Net refinado con GrabCut  ->  persona sin fondo
    recorte de la cabeza (pelo + cara)
    + XDoG del laboratorio
    + MediaPipe (cejas más marcadas, sin ojos si hay lentes oscuros)
    + fundido del torso y umbral más suave dentro de la cara
    = máscara de líneas lista para vectorizar

Ruta opcional (`use_lineart=True`): modelo line-drawings.onnx (estilo
anime, Apache-2.0). Genera sombreado con tramas ruidosas que fragmentan
los trazos y empeoran el reconocimiento facial; se mantiene solo como
opt-in para comparar.

Por qué NO una elipse fija: la elipse recortaba el pelo y dejaba un "huevo"
calvo con un contorno liso muy artificial. Ahora la caja de la cabeza se
deduce de la silueta real de la persona (U2Net): se toma el pelo de arriba y
se cierra por debajo del mentón, así el contorno exterior es el del pelo de
verdad y no el de una elipse.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from . import sketch as sketch_ops
from . import vectorize as vectorize_ops
from .faceparse import MODEL_NAME as FaceParserModelName
from .faceparse import FaceParser
from .landmarks import FaceLandmarks
from .lineart import LineArtModel
from .segmentation import FaceDetector, U2NetHuman

ELLIPSE_AXES = (0.95, 1.0)  # respecto al ancho/alto del bbox de YuNet
FEATHER = 25
TARGET_PX = 900
# Umbrales del modelo de line art, en escala de gris (1 = papel, 0 = linea).
# "strong" es la tinta segura; "weak" son los trazos tenues (pelo, barba) que
# solo se conservan si tocan a una linea fuerte. Con un unico umbral fijo
# el dibujo salia troceado: se perdian los ojos y la barba.
LINEART_STRONG = 0.72
LINEART_WEAK = 0.86
# Cierre morfológico antes de adelgazar: une los huecos de 1-2 px que deja
# el umbral para que el esqueleto salga en trazos largos, no en guiones.
LINEART_CLOSE = 3
# Motas de ruido que se descartan (en px de area). Con 24 se perdia pelo.
LINEART_SPECK_AREA = 6


def prepare_for_lineart(image: np.ndarray) -> np.ndarray:
    """Limpia la foto antes del modelo: quita el granulado y recupera pelo oscuro."""
    denoised = image
    for _ in range(2):
        denoised = cv2.bilateralFilter(denoised, 7, 50, 50)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    lightness, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    lab = cv2.merge((clahe.apply(lightness), a_channel, b_channel))
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

# Landmark de la barbilla (el punto más bajo de la cara).
CHIN_LANDMARK = 152
# Landmark de la frente (arriba del óvalo de la cara).
FOREHEAD_LANDMARK = 10


def ellipse_alpha(shape: tuple[int, int], face: dict, axes=ELLIPSE_AXES, feather: int = FEATHER):
    """Máscara suave con forma de elipse centrada en la cara (respaldo)."""
    height, width = shape[:2]
    x, y, w, h = (float(value) for value in face["bbox"])
    centre = (int(round(x + w / 2)), int(round(y + h / 2)))
    semi_axes = (int(round(w * axes[0] / 2)), int(round(h * axes[1] / 2)))
    mask = np.zeros((height, width), dtype=np.float32)
    cv2.ellipse(mask, centre, semi_axes, 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    if feather > 0:
        mask = cv2.GaussianBlur(mask, (feather * 2 + 1, feather * 2 + 1), 0)
    return np.clip(mask, 0.0, 1.0)


def head_region(
    shape: tuple[int, int],
    face: dict,
    alpha: np.ndarray,
    chin_y: float | None = None,
) -> tuple[int, int, int, int]:
    """Caja de la cabeza (pelo + cara) deducida de la silueta de la persona.

    - arriba: el pelo, leído en la columna del centro de la cara (donde solo
      puede estar el pelo; si el modelo se comió un mueble del fondo, no
      afecta);
    - abajo: ~1 cara bajo el mentón (cuello + hombros, la ropa sí entra);
    - lados: la cara más un margen fijo para el pelo (la silueta completa
      serviría: a veces el modelo incluye la silla y la caja se iba de lado).
    """
    height, width = shape[:2]
    x, y, w, h = (float(value) for value in face["bbox"])
    binary = alpha > 0.5

    # Columna del centro de la cara: el pelo es lo primero que aparece.
    center_col = int(round(x + w / 2))
    column = binary[:, max(0, min(width - 1, center_col))]
    rows = np.nonzero(column)[0]
    hair_top = int(rows.min()) if len(rows) else int(y - 0.3 * h)
    top = max(hair_top, int(y - 1.1 * h))
    top = min(top, int(y - 0.02 * h))

    if chin_y is None:
        chin_y = y + h * 1.05
    # Cuello + hombros: ~1 cara bajo el mentón para que la ropa entre.
    bottom = int(min(height, chin_y + 1.0 * h))

    left = int(max(0, x - 0.40 * w))
    right = int(min(width, x + 1.40 * w))

    head_width = max(1, right - left)
    head_height = max(1, bottom - top)
    pad_x = int(round(0.02 * head_width)) + 2
    pad_y = int(round(0.02 * head_height)) + 2

    return (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(width, right + pad_x),
        min(height, bottom + pad_y),
    )


def crop_to_subject(image: np.ndarray, alpha: np.ndarray, target_px: int = TARGET_PX):
    """Recorta el sujeto y lo agranda (para que el XDoG vea los rasgos)."""
    ys, xs = np.nonzero(alpha > 0.1)
    height, width = image.shape[:2]
    if len(xs) == 0:
        box = (0, 0, width, height)
    else:
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        pad = int(round(0.06 * max(x1 - x0, y1 - y0))) + 2
        box = (
            max(0, x0 - pad),
            max(0, y0 - pad),
            min(width, x1 + pad),
            min(height, y1 + pad),
        )
    return crop_and_upscale(image, box, target_px), box


def crop_and_upscale(image: np.ndarray, box, target_px: int = TARGET_PX):
    """Recorta la caja indicada y la agranda hasta `target_px` de lado largo."""
    x0, y0, x1, y1 = (int(value) for value in box)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return image.copy()
    longest = max(crop.shape[:2])
    if longest < target_px:
        scale = min(2.5, target_px / longest)
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return crop


def silhouette_lines(
    alpha: np.ndarray,
    box,
    crop_size: tuple[int, int],
    thickness: float = 2.2,
) -> np.ndarray:
    """Contorno de la silueta (pelo/cabeza) como mapa de líneas.

    El XDoG no ve el borde del pelo: contra el fondo blanco la transición es
    suave y no da línea. El contorno de la máscara de persona sí es el pelo
    de verdad, así que se dibuja a mano (suavizado, porque U2Net trabaja a
    320x320 y al ampliar sale escalonado).
    """
    crop_width, crop_height = crop_size
    canvas = np.zeros((crop_height, crop_width), dtype=np.float32)

    binary = (alpha > 0.5).astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return canvas
    contour = max(contours, key=cv2.contourArea)
    approx = cv2.approxPolyDP(contour, 2.5, True).reshape(-1, 2).astype(np.float32)

    x0, y0, x1, y1 = (float(value) for value in box)
    scale_x = crop_width / max(1.0, x1 - x0)
    scale_y = crop_height / max(1.0, y1 - y0)
    points = approx.copy()
    points[:, 0] = (points[:, 0] - x0) * scale_x
    points[:, 1] = (points[:, 1] - y0) * scale_y

    cv2.polylines(
        canvas,
        [np.round(points).astype(np.int32)],
        True,
        1.0,
        int(round(thickness)),
        cv2.LINE_AA,
    )
    return canvas


class PortraitRenderer:
    """Genera la máscara de líneas de un retrato, lista para vectorizar."""

    def __init__(self, models_dir: Path) -> None:
        self.face = FaceDetector(models_dir / "face_detection_yunet_2023mar.onnx")
        self.u2net = U2NetHuman(models_dir / "u2netp.onnx")
        self.landmarks = FaceLandmarks(models_dir / "face_landmarker.task")
        self.lineart = LineArtModel(models_dir)
        self.faceparse = FaceParser(models_dir / FaceParserModelName)

    def health(self) -> dict:
        return {
            "face_detector": self.face.available,
            "u2net": self.u2net.available,
            "landmarks": self.landmarks.available,
            "lineart": self.lineart.available,
            "faceparse": self.faceparse.available,
        }

    def render(
        self,
        image: np.ndarray,
        sigma: float = 1.2,
        phi: float = 40.0,
        epsilon: float = 0.0,
        contrast: float = 0.7,
        threshold: float = 0.12,
        bg_threshold: float = 0.28,
        beard_thresh: float = 0.45,
        use_landmarks: bool = True,
        use_ellipse: bool = True,
        target_px: int = TARGET_PX,
        use_lineart: bool = False,
        lineart_strong: float = LINEART_STRONG,
        lineart_weak: float = LINEART_WEAK,
        lab_sigma: float | None = None,
        lab_phi: float | None = None,
        lab_contrast: float | None = None,
        lab_bilateral: float | None = None,
        ink_high: float | None = None,
        ink_span: float | None = None,
        speck_area: int | None = None,
        stages: dict | None = None,
        use_faceparse: bool = False,
    ) -> dict:
        started = time.perf_counter()
        height, width = image.shape[:2]

        face = self.face.detect(image) if self.face.available else None

        landmarks = None
        if use_landmarks and self.landmarks.available:
            landmarks = self.landmarks.detect(image)

        # Máscara de persona del laboratorio: U2Net + GrabCut en el borde.
        # ``stages`` solo se llena para el laboratorio; la máscara no cambia.
        seg_stages: dict | None = {} if stages is not None else None
        alpha = (
            self.u2net.segment(image, face["bbox"] if face else None, stages=seg_stages)
            if self.u2net.available
            else None
        )
        if stages is not None and seg_stages:
            stages.update(seg_stages)
        if alpha is None:
            # Respaldo: sin U2Net se usa una elipse alrededor de la cara.
            alpha = (
                ellipse_alpha(image.shape, face)
                if use_ellipse and face is not None
                else np.ones((height, width), dtype=np.float32)
            )
        alpha = np.clip(alpha, 0.0, 1.0)

        cutout_full = sketch_ops.composite_on_white(image, alpha)

        # Caja de la cabeza: pelo arriba, mentón abajo.
        if face is not None:
            chin_y = (
                float(landmarks[CHIN_LANDMARK][1]) * height if landmarks is not None else None
            )
            box = head_region(image.shape, face, alpha, chin_y=chin_y)
        else:
            box = (0, 0, width, height)

        crop = crop_and_upscale(cutout_full, box, target_px=target_px)

        landmark_lines = None
        lab_meta: dict = {}
        if use_lineart and self.lineart.available:
            # Ruta opcional: el modelo de line art estilo anime genera tramas
            # ruidosas que fragmentan los trazos del robot y empeoran el
            # parecido. Se mantiene como opt-in para comparar.
            # La máscara sale con histéresis (tinta fuerte siempre, tinta
            # débil solo si toca a una fuerte) y encima se superponen los
            # landmarks de MediaPipe, que son la geometría correcta de la
            # cara.
            art = self.lineart.art(prepare_for_lineart(crop))
            mask = self.lineart.hysteresis(
                art, strong=lineart_strong, weak=lineart_weak
            )
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (LINEART_CLOSE, LINEART_CLOSE)
            )
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            if use_landmarks and landmarks is not None:
                landmark_lines = self._landmark_lines(landmarks, box, crop, image.shape)
                mask = np.maximum(
                    mask, (landmark_lines > 0.5).astype(np.uint8) * 255
                )
            lines = mask.astype(np.float32) / 255.0
            mask = vectorize_ops.remove_specks(mask, min_area=LINEART_SPECK_AREA)
        else:
            # Boceto del laboratorio sobre el recorte (lentes, zonas, torso).
            # Esta ruta usa los valores afinados en el lab. La silueta de
            # U2Net no se redibuja: el borde duro contra el blanco ya entra
            # en el XDoG.
            scaled = self._scaled_landmarks(landmarks, box, crop, image.shape)
            sketch_stages: dict | None = {} if stages is not None else None
            # Un solo diccionario: lab_sigma y sigma no pueden llegar los dos.
            tune = {
                "sigma": sigma if lab_sigma is None else lab_sigma,
                "phi": phi if lab_phi is None else lab_phi,
                "epsilon": epsilon,
                "bg_thresh": bg_threshold,
                "face_thresh": threshold,
                "beard_thresh": beard_thresh,
                "stages": sketch_stages,
                "faceparse": (
                    self.faceparse if use_faceparse and self.faceparse.available else None
                ),
            }
            if lab_contrast is not None:
                tune["contrast"] = lab_contrast
            if lab_bilateral is not None:
                tune["bilateral"] = lab_bilateral
            if ink_high is not None:
                tune["ink_high"] = ink_high
            if ink_span is not None:
                tune["ink_span"] = ink_span
            if speck_area is not None:
                tune["speck_area"] = speck_area
            lines, mask, lab_meta = sketch_ops.lab_portrait_lines(
                crop,
                scaled,
                self.landmarks if scaled is not None else None,
                **tune,
            )
            if stages is not None and sketch_stages:
                stages.update(sketch_stages)
                stages["scaled_landmarks"] = scaled

        return {
            "face": face,
            "alpha": alpha,
            "cutout": cutout_full,
            "crop": crop,
            "crop_box": {
                "x": box[0],
                "y": box[1],
                "width": box[2] - box[0],
                "height": box[3] - box[1],
            },
            "lines": lines,
            "landmark_lines": landmark_lines,
            "mask": mask,
            "lab": lab_meta,
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    def _scaled_landmarks(self, landmarks, box, crop, image_shape):
        """Landmarks de la foto completa, en píxeles del recorte."""
        if landmarks is None:
            return None
        height, width = image_shape[:2]
        x0, y0, x1, y1 = box
        crop_width, crop_height = crop.shape[1], crop.shape[0]
        scale_x = crop_width / max(1, (x1 - x0))
        scale_y = crop_height / max(1, (y1 - y0))
        scaled = landmarks.copy()
        scaled[:, 0] = (scaled[:, 0] * width - x0) * scale_x
        scaled[:, 1] = (scaled[:, 1] * height - y0) * scale_y
        return scaled

    def _xdog_lines(self, crop, alpha, box, sigma, epsilon, phi, contrast) -> np.ndarray:
        gray = sketch_ops.to_gray(crop, contrast)
        lines = sketch_ops.xdog(gray, sigma=sigma, epsilon=epsilon, phi=phi)
        # Silueta (pelo) + rasgos: por encima de lo que encuentre el XDoG.
        silhouette = silhouette_lines(alpha, box, (crop.shape[1], crop.shape[0]))
        return np.maximum(lines, silhouette)

    def _landmark_lines(self, landmarks, box, crop, image_shape):
        scaled = self._scaled_landmarks(landmarks, box, crop, image_shape)
        if scaled is None:
            return None
        return self.landmarks.draw_lines(scaled, (crop.shape[1], crop.shape[0]))
