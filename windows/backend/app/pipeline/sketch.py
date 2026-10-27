"""Conversión de imagen a líneas (XDoG) y utilidades de composición."""

from __future__ import annotations

import cv2
import numpy as np


def composite_on_white(image: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Compone BGR + alpha (0..1) sobre fondo blanco."""
    alpha_3 = np.clip(alpha, 0.0, 1.0)[..., None]
    return np.clip(image.astype(np.float32) * alpha_3 + 255.0 * (1.0 - alpha_3), 0, 255).astype(np.uint8)


# Rango de gris que el bilateral promedia. Con 35 (el valor anterior) se
# borraba cualquier escalon de hasta 35 niveles: justo el tamano del pliegue
# del parpado y del brillo del iris. Medido sobre una webcam real, 35 dejaba
# la zona de los ojos con un 42 % menos de gradiente que la foto original;
# con 16 se conserva el rasgo y la piel sigue suave.
DENOISE_RANGE = 16
# El CLAHE con 8x8 tiles y clip 2.0 apenas recuperaba lo que perdia el
# bilateral (quedaba un 11 % por debajo del gradiente de la foto). Con 16x16
# y clip 3.0 el ojo detras de los lentes vuelve a leerse.
CLAHE_CLIP = 3.0
CLAHE_TILES = 16


def to_gray(image: np.ndarray, contrast: float = 0.4) -> np.ndarray:
    """Gris suavizado con contraste local opcional (CLAHE).

    El CLAHE recupera ojos, labios y barba en fotos de webcam con luz plana.
    Se mezcla con el gris original para no amplificar el ruido del fondo.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Suaviza textura de piel sin borrar rasgos.
    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=DENOISE_RANGE, sigmaSpace=5)

    contrast = float(np.clip(contrast, 0.0, 1.0))
    if contrast > 0:
        equalized = cv2.createCLAHE(
            clipLimit=CLAHE_CLIP, tileGridSize=(CLAHE_TILES, CLAHE_TILES)
        ).apply(gray)
        gray = cv2.addWeighted(gray, 1.0 - contrast, equalized, contrast, 0)

    return gray.astype(np.float32) / 255.0


def xdog(
    gray: np.ndarray,
    sigma: float = 0.9,
    k: float = 1.6,
    tau: float = 0.98,
    epsilon: float = 0.0,
    phi: float = 32.0,
) -> np.ndarray:
    """Devuelve intensidad de línea en 0..1 (0 = sin línea)."""
    sigma = max(0.1, float(sigma))
    g1 = cv2.GaussianBlur(gray, (0, 0), sigma)
    g2 = cv2.GaussianBlur(gray, (0, 0), sigma * max(1.01, float(k)))
    dog = g1 - float(tau) * g2

    # Normalizar el DoG: sin esto, las zonas planas quedan grises y el
    # resultado parece una foto con sombras en vez de un dibujo de líneas.
    peak = float(np.abs(dog).max())
    if peak > 1e-6:
        dog = dog / peak

    out = 1.0 + np.tanh(float(phi) * (dog - float(epsilon)))
    out = np.clip(out, 0.0, 1.0)
    lines = np.clip(1.0 - out, 0.0, 1.0)
    return lines


def render_lines(lines: np.ndarray) -> np.ndarray:
    """Líneas -> imagen gris con fondo blanco."""
    image = np.clip(255.0 * (1.0 - lines), 0, 255).astype(np.uint8)
    return cv2.medianBlur(image, 3)


def binarize(lines: np.ndarray, threshold: float = 0.20) -> np.ndarray:
    """Líneas -> blanco/negro listo para mostrar (fondo blanco, línea negra).

    Para vectorizar, invertir con ``255 - binarize(...)`` y así obtener la
    máscara con 255 en las líneas.
    """
    mask = (lines >= threshold).astype(np.uint8) * 255
    # Elimina motas de 1-2 px.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return 255 - mask


# Parámetros del laboratorio: son los que dejaban el boceto limpio en la
# cabina (bilateral suave, XDoG un poco más ancho que el de la ruta vieja).
LAB_SIGMA = 1.2
LAB_PHI = 40.0
LAB_CONTRAST = 0.4
LAB_BILATERAL = 35.0
# Dentro de la cara el umbral es INK_HIGH - INK_SPAN (más tinta). Afuera, INK_HIGH.
INK_HIGH = 0.28
INK_SPAN = 0.16
SPECK_AREA = 8


def lab_to_gray(
    image: np.ndarray,
    contrast: float = LAB_CONTRAST,
    bilateral: float = LAB_BILATERAL,
) -> np.ndarray:
    """Gris del laboratorio: bilateral 35 y CLAHE 8×8."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=float(bilateral), sigmaSpace=7)
    contrast = float(np.clip(contrast, 0.0, 1.0))
    if contrast > 0:
        equalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        gray = cv2.addWeighted(gray, 1.0 - contrast, equalized, contrast, 0)
    return gray.astype(np.float32) / 255.0


def _dark_glasses(gray: np.ndarray, points: np.ndarray) -> tuple[bool, float]:
    """True si hay lentes oscuros. Compara el brillo de los ojos con las mejillas."""
    height, width = gray.shape[:2]
    eye_ids = (468, 473) if len(points) > 468 else (159, 386)
    cheek_ids = (205, 425)

    def sample(index: int, radius: int = 4) -> float:
        x, y = int(points[index][0]), int(points[index][1])
        x0, x1 = max(0, x - radius), min(width, x + radius)
        y0, y1 = max(0, y - radius), min(height, y + radius)
        if x0 == x1 or y0 == y1:
            return 127.0
        return float(gray[y0:y1, x0:x1].mean())

    eye_mean = sum(sample(index) for index in eye_ids) / 2.0
    cheek_mean = sum(sample(index) for index in cheek_ids) / 2.0
    ratio = eye_mean / max(cheek_mean, 1e-6)
    # En esta webcam un ojo normal ya ronda 0.40. Solo se omiten los ojos
    # si el iris está tapado de verdad (lentes oscuros).
    return ratio < 0.34, ratio


def _torso_fade(shape: tuple[int, int], chin_y: float, face_h: float) -> np.ndarray | None:
    """Máscara 1..0 que apaga las arrugas de la playera bajo el pecho."""
    height, width = shape[:2]
    start = chin_y + 0.7 * face_h
    end = min(float(height), chin_y + 1.8 * face_h)
    if end <= start or face_h <= 0:
        return None
    rows = np.arange(height, dtype=np.float32)
    fade = np.clip((end - rows) / max(1.0, end - start), 0.0, 1.0)
    return np.broadcast_to(fade[:, None], (height, width)).copy()


def _open_mask(lines: np.ndarray, threshold) -> np.ndarray:
    """Umbral (escalar o mapa) → 255 donde hay línea, sin motas de 1-2 px."""
    mask = (lines >= threshold).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _drop_specks(mask: np.ndarray, min_area: int = SPECK_AREA) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros_like(mask)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == index] = 255
    return keep


def lab_portrait_lines(
    crop: np.ndarray,
    landmarks_px: np.ndarray | None,
    landmarker,
    sigma: float = LAB_SIGMA,
    phi: float = LAB_PHI,
    contrast: float = LAB_CONTRAST,
    bilateral: float = LAB_BILATERAL,
    ink_high: float = INK_HIGH,
    ink_span: float = INK_SPAN,
    speck_area: int = SPECK_AREA,
    stages: dict | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Boceto del laboratorio sobre el recorte ya puesto en blanco.

    XDoG + rasgos de MediaPipe (cejas un poco más gruesas, sin ojos si hay
    lentes oscuros) + fundido del torso + umbral más suave dentro de la cara.
    Devuelve (intensidad 0..1, máscara con 255 en la tinta, metadatos).

    Los argumentos extra repiten las constantes de la cabina. Si no se
    pasan, el dibujo es el de siempre. Con ``stages`` se guardan las
    imágenes intermedias para el laboratorio, sin alterar la tinta.
    """
    gray = lab_to_gray(crop, contrast=contrast, bilateral=bilateral)
    lines = xdog(gray, sigma=sigma, phi=phi)
    xdog_only = lines.copy() if stages is not None else None
    glasses, ratio = "clear", 1.0
    landmark_map = None
    faded = False
    zoned = False

    if landmarks_px is not None and landmarker is not None:
        try:
            raw = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            dark, ratio = _dark_glasses(raw, landmarks_px)
            glasses = "dark" if dark else "clear"
            width, height = crop.shape[1], crop.shape[0]
            features = (
                ("jaw", "brows", "lips", "nose")
                if dark
                else ("jaw", "brows", "eyes", "lips", "nose")
            )
            base = tuple(name for name in features if name != "brows")
            drawn_base = landmarker.draw_lines(
                landmarks_px, (width, height), thickness=1.2, features=base
            )
            drawn_brows = landmarker.draw_lines(
                landmarks_px, (width, height), thickness=1.5, features=("brows",)
            )
            landmark_map = np.maximum(drawn_base, drawn_brows)
            lines = np.maximum(lines, landmark_map)
        except Exception:
            landmark_map = None

        try:
            from .landmarks import CHIN, LEFT_EYE_OUTER, RIGHT_EYE_OUTER

            height, width = crop.shape[:2]
            eye_y = 0.5 * (
                float(landmarks_px[RIGHT_EYE_OUTER][1]) + float(landmarks_px[LEFT_EYE_OUTER][1])
            )
            chin_y = float(landmarks_px[CHIN][1])
            fade = _torso_fade((height, width), chin_y, chin_y - eye_y)
            if fade is not None:
                lines = lines * fade
                faded = True
        except Exception:
            pass

        try:
            height, width = crop.shape[:2]
            hull = cv2.convexHull(np.round(landmarks_px[landmarker.oval_indices()]).astype(np.int32))
            zone = np.zeros((height, width), np.float32)
            cv2.fillConvexPoly(zone, hull, 1.0)
            zone = cv2.GaussianBlur(zone, (0, 0), max(3, int(0.01 * (width + height) / 2)))
            outside = 1.0 - zone
            weak = (lines < 0.5).astype(np.float32)
            lines = lines * (1.0 - outside * weak * 0.8)
            ink = _drop_specks(_open_mask(lines, ink_high - ink_span * zone), speck_area)
            if landmark_map is not None:
                # Tinta débil y aislada dentro de la cara que no toca un rasgo:
                # se borra. Lo fuerte y los rasgos (dilatados) se quedan.
                protect = (
                    cv2.dilate((landmark_map > 0.5).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                )
                inside = zone > 0.5
                weak_skin = ((ink == 255) & inside & (lines < 0.5) & ~protect).astype(np.uint8) * 255
                kept = _drop_specks(weak_skin, 16)
                ink = np.where((weak_skin == 255) & (kept == 0), 0, ink).astype(np.uint8)
            zoned = True
        except Exception:
            zoned = False

    if not zoned:
        ink = _drop_specks(_open_mask(lines, 0.20), speck_area)

    if stages is not None:
        stages["gray"] = gray
        stages["xdog"] = xdog_only
        stages["landmarks"] = None if landmark_map is None else landmark_map.copy()
        stages["fused"] = lines.copy()
        stages["ink"] = ink.copy()

    return lines, ink, {
        "glasses": glasses,
        "glasses_ratio": round(float(ratio), 3),
        "fade": faded,
        "zoned": zoned,
    }


def pencil_sketch(image: np.ndarray) -> np.ndarray:
    """Fallback clásico de OpenCV, para comparar con XDoG."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, sketch = cv2.pencilSketch(image, sigma_s=50, sigma_r=0.07, shade_factor=0.05)
    return sketch
