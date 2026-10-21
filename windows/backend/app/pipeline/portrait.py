"""Pipeline de retrato "calidad": fondo fuera + rasgos marcados + líneas.

Es la ruta que mejor funciona con fotos de webcam reales:

    YuNet (rostro) + U2Net ∩ elipse  ->  recorte limpio (pelo y barbilla)
    + MediaPipe landmarks            ->  contorno de mandíbula, cejas, ojos
    + XDoG                           ->  pelo, barba, lentes, textura
    = máscara de líneas lista para vectorizar

El detalle de "por qué la elipse": BiSeNet clasifica la barba y el mentón
como "no piel" y recorta la mandíbula; U2Net sí conserva todo el cuerpo pero
incluye la ropa. Al intersectar U2Net con una elipse centrada en la cara,
ganamos el pelo y la barbilla sin la ropa.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from . import sketch as sketch_ops
from . import vectorize as vectorize_ops
from .landmarks import FaceLandmarks
from .segmentation import FaceDetector, U2NetHuman

ELLIPSE_AXES = (0.95, 1.0)  # respecto al ancho/alto del bbox de YuNet
FEATHER = 25
TARGET_PX = 900


def ellipse_alpha(shape: tuple[int, int], face: dict, axes=ELLIPSE_AXES, feather: int = FEATHER):
    """Máscara suave con forma de elipse centrada en la cara."""
    height, width = shape[:2]
    x, y, w, h = (float(value) for value in face["bbox"])
    centre = (int(round(x + w / 2)), int(round(y + h / 2)))
    semi_axes = (int(round(w * axes[0] / 2)), int(round(h * axes[1] / 2)))
    mask = np.zeros((height, width), dtype=np.float32)
    cv2.ellipse(mask, centre, semi_axes, 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    if feather > 0:
        mask = cv2.GaussianBlur(mask, (feather * 2 + 1, feather * 2 + 1), 0)
    return np.clip(mask, 0.0, 1.0)


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

    x0, y0, x1, y1 = box
    crop = image[y0:y1, x0:x1]
    longest = max(crop.shape[:2])
    if longest < target_px:
        scale = min(2.5, target_px / longest)
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return crop, box


class PortraitRenderer:
    """Genera la máscara de líneas de un retrato, lista para vectorizar."""

    def __init__(self, models_dir: Path) -> None:
        self.face = FaceDetector(models_dir / "face_detection_yunet_2023mar.onnx")
        self.u2net = U2NetHuman(models_dir / "u2net_human_seg.onnx")
        self.landmarks = FaceLandmarks(models_dir / "face_landmarker.task")

    def health(self) -> dict:
        return {
            "face_detector": self.face.available,
            "u2net": self.u2net.available,
            "landmarks": self.landmarks.available,
        }

    def render(
        self,
        image: np.ndarray,
        sigma: float = 1.0,
        phi: float = 40.0,
        epsilon: float = 0.0,
        contrast: float = 0.6,
        threshold: float = 0.15,
        use_landmarks: bool = True,
        use_ellipse: bool = True,
        target_px: int = TARGET_PX,
    ) -> dict:
        started = time.perf_counter()
        height, width = image.shape[:2]

        face = self.face.detect(image) if self.face.available else None
        alpha = (
            self.u2net.predict(image)
            if self.u2net.available
            else np.ones((height, width), dtype=np.float32)
        )
        if use_ellipse and face is not None:
            alpha = alpha * ellipse_alpha(image.shape, face)
        alpha = np.clip(alpha, 0.0, 1.0)

        cutout_full = sketch_ops.composite_on_white(image, alpha)
        crop, box = crop_to_subject(cutout_full, alpha, target_px=target_px)

        gray = sketch_ops.to_gray(crop, contrast)
        lines = sketch_ops.xdog(gray, sigma=sigma, epsilon=epsilon, phi=phi)

        landmark_lines = None
        if use_landmarks and face is not None and self.landmarks.available:
            landmarks = self.landmarks.detect(image)
            if landmarks is not None:
                # Los landmarks están en coordenadas de la imagen completa:
                # hay que llevarlos al recorte (x0, y0) y escalarlos.
                x0, y0, x1, y1 = box
                crop_width, crop_height = crop.shape[1], crop.shape[0]
                scale_x = crop_width / max(1, (x1 - x0))
                scale_y = crop_height / max(1, (y1 - y0))
                scaled = landmarks.copy()
                scaled[:, 0] = (scaled[:, 0] * width - x0) * scale_x
                scaled[:, 1] = (scaled[:, 1] * height - y0) * scale_y
                landmark_lines = self.landmarks.draw_lines(
                    scaled, (crop_width, crop_height)
                )
                # Los landmarks mandan: se borra el halo del XDoG alrededor del
                # trazo (si no, la mandíbula saldría doble) y se pinta la línea.
                band = (landmark_lines > 0.2).astype(np.uint8)
                band = cv2.dilate(band, np.ones((3, 3), np.uint8), iterations=1)
                lines = np.where(band > 0, landmark_lines, lines)
                lines = np.maximum(lines, landmark_lines)

        mask = vectorize_ops.remove_specks(
            vectorize_ops.lines_to_mask(lines, threshold)
        )

        return {
            "face": face,
            "alpha": alpha,
            "cutout": cutout_full,
            "crop": crop,
            "crop_box": {"x": box[0], "y": box[1], "width": box[2] - box[0], "height": box[3] - box[1]},
            "lines": lines,
            "landmark_lines": landmark_lines,
            "mask": mask,
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        }
