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
    clahe_clip: float = 2.0,
    bilateral: float = LAB_BILATERAL,
) -> np.ndarray:
    """Gris del laboratorio: bilateral 35 y CLAHE 8×8."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=float(bilateral), sigmaSpace=7)
    contrast = float(np.clip(contrast, 0.0, 1.0))
    if contrast > 0:
        equalized = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8)).apply(gray)
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


# Barba corta: el XDoG dibuja cada pelo como puntito abierto y el robot lo
# deja como grumo. En la banda labio->mentón (+medio largo hacia el cuello)
# solo sobrevive tinta fuerte (boca, contorno); la boca se conserva porque
# los landmarks la protegen.
BEARD_THRESH = 0.45
# Puntito aislado (sin tocar ningun rasgo) hasta este area se borra en la
# banda: los puntos de barba son fuertes (>=0.45) y el umbral no los mata.
BEARD_BLOB = 80


def beard_band_mask(
    shape: tuple[int, int], landmarks_px: np.ndarray | None
) -> np.ndarray:
    """Booleano por fila: banda labio->mentón + medio largo al cuello."""
    mask = np.zeros(shape, dtype=bool)
    if landmarks_px is None:
        return mask
    try:
        from .landmarks import CHIN, UPPER_LIP

        lip_y = float(landmarks_px[UPPER_LIP][1])
        chin_y = float(landmarks_px[CHIN][1])
        if not (np.isfinite(lip_y) and np.isfinite(chin_y)) or chin_y <= lip_y:
            return mask
        top = int(max(0, lip_y))
        bottom = int(min(shape[0], chin_y + 0.5 * (chin_y - lip_y)))
        mask[top:bottom, :] = True
        return mask
    except Exception:
        return mask


def drop_isolated_blobs(
    ink: np.ndarray, band: np.ndarray, touch: np.ndarray, max_area: int = BEARD_BLOB
) -> np.ndarray:
    """Borra manchas chicas dentro de la banda que no tocan ningun rasgo."""
    cand = ((ink == 255) & band & ~touch).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    kill = np.zeros_like(ink)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] <= max_area:
            kill[labels == index] = 255
    return np.where(kill == 255, 0, ink).astype(np.uint8)


def beard_threshold_map(
    zone: np.ndarray,
    landmarks_px: np.ndarray | None,
    bg: float = 0.28,
    face: float = 0.12,
    beard: float = BEARD_THRESH,
) -> np.ndarray:
    """Mapa de umbral: base fondo/cara + banda de barba estricta."""
    base = bg - (bg - face) * zone
    band = beard_band_mask(zone.shape, landmarks_px)
    out = base.copy()
    out[band] = beard
    return out


def lab_portrait_lines(
    crop: np.ndarray,
    landmarks_px: np.ndarray | None,
    landmarker,
    sigma: float = LAB_SIGMA,
    phi: float = LAB_PHI,
    epsilon: float = 0.0,
    contrast: float = LAB_CONTRAST,
    bilateral: float = LAB_BILATERAL,
    clahe_clip: float = 2.0,
    bg_thresh: float = 0.28,
    face_thresh: float = 0.12,
    flat_thresh: float = 0.20,
    beard_thresh: float = BEARD_THRESH,
    ink_high: float | None = None,
    ink_span: float | None = None,
    speck_area: int = SPECK_AREA,
    stages: dict | None = None,
    faceparse=None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Boceto del laboratorio sobre el recorte ya puesto en blanco.

    XDoG + rasgos de MediaPipe (cejas un poco más gruesas, sin ojos si hay
    lentes oscuros) + fundido del torso + umbral más suave dentro de la cara.
    Los parámetros llegan de SketchParams (punto 4: sin reiniciar para
    probar); los defaults son los afinados en la cabina.
    Devuelve (intensidad 0..1, máscara con 255 en la tinta, metadatos).

    Los argumentos extra repiten las constantes de la cabina. Si no se
    pasan, el dibujo es el de siempre. Con ``stages`` se guardan las
    imágenes intermedias para el laboratorio, sin alterar la tinta.
    """
    gray = lab_to_gray(crop, contrast=contrast, clahe_clip=clahe_clip, bilateral=bilateral)
    lines = xdog(gray, sigma=sigma, epsilon=epsilon, phi=phi)
    xdog_only = lines.copy() if stages is not None else None
    glasses, ratio = "clear", 1.0
    landmark_map = None
    faded = False
    zoned = False
    parsed = False
    small_eyes = False

    if landmarks_px is not None and landmarker is not None:
        try:
            from .landmarks import (
                CHIN,
                LEFT_EYE_OUTER,
                RIGHT_EYE_OUTER,
                _eye_disc_mask,
                _simple_eyes,
                _small_eyes,
            )

            eye_y = 0.5 * (
                float(landmarks_px[RIGHT_EYE_OUTER][1])
                + float(landmarks_px[LEFT_EYE_OUTER][1])
            )
            chin_y = float(landmarks_px[CHIN][1])
            small_eyes = bool(_small_eyes(landmarks_px, chin_y - eye_y))
            raw = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            dark, ratio = _dark_glasses(raw, landmarks_px)
            glasses = "dark" if dark else "clear"
            width, height = crop.shape[1], crop.shape[0]
            features = (
                ("jaw", "brows", "lips", "nose")
                if dark
                else ("jaw", "brows", "eyes", "lips", "nose")
            )
            if small_eyes:
                # Ojo chico: no entra al mapa (la limpieza lo mata disparejo);
                # se estampa simétrico sobre la máscara final.
                features = tuple(name for name in features if name != "eyes")
            base = tuple(name for name in features if name != "brows")
            drawn_base = landmarker.draw_lines(
                landmarks_px, (width, height), thickness=1.2, features=base
            )
            drawn_brows = landmarker.draw_lines(
                landmarks_px, (width, height), thickness=1.5, features=("brows",)
            )
            landmark_map = np.maximum(drawn_base, drawn_brows)
            lines = np.maximum(lines, landmark_map)
            try:
                if small_eyes:
                    # Ojo chico (lentes): el XDoG adentro del ojo es reflejo
                    # asimétrico; se apaga y el ojo se estampa al final.
                    discs = _eye_disc_mask((height, width), landmarks_px)
                    lines = lines * (1.0 - discs) + landmark_map * discs
            except Exception:
                pass
        except Exception:
            landmark_map = None

        if faceparse is not None:
            # Base estilo mariposa: bordes ENTRE regiones (0/1, ya limpios).
            # El XDoG solo sobrevive adentro del pelo (hebras); los rasgos
            # MediaPipe se conservan (pupilas, parpados). El bloque de
            # zonificado de abajo respeta las lineas fuertes tal cual.
            try:
                from .faceparse import HAIR_GROUP, boundaries

                grouped = faceparse.parse(crop)
                if grouped is not None:
                    base = 1.0 - boundaries(grouped).astype(np.float32) / 255.0
                    hair = (grouped == HAIR_GROUP).astype(np.float32)
                    hair = cv2.dilate(hair, np.ones((5, 5), np.uint8))
                    strand = lines * hair
                    keep = landmark_map if landmark_map is not None else 0.0
                    lines = np.maximum(np.maximum(base, strand), keep)
                    parsed = True
            except Exception:
                parsed = False

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
            if ink_high is not None and ink_span is not None:
                threshold = ink_high - ink_span * zone
            else:
                threshold = beard_threshold_map(
                    zone, landmarks_px, bg_thresh, face_thresh, beard_thresh
                )
            ink = _drop_specks(_open_mask(lines, threshold), speck_area)
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
                # Barba: los puntos son fuertes y el umbral no los mata; se
                # borran por area si flotan sin tocar ningun rasgo.
                band = beard_band_mask(ink.shape, landmarks_px)
                if band.any():
                    ink = drop_isolated_blobs(ink, band, protect)
            zoned = True
        except Exception:
            zoned = False

    if not zoned:
        ink = _drop_specks(_open_mask(lines, flat_thresh), speck_area)

    try:
        if small_eyes and landmarks_px is not None:
            # Ojo chico: párpado + punto estampados tal cual, simétricos.
            # Van DESPUÉS de la limpieza porque la apertura 2x2 borra las
            # líneas de 1-2 px de un ojo sí y del otro no.
            from .landmarks import _simple_eyes as _stamp_eyes

            stamp = np.zeros((ink.shape[0], ink.shape[1]), dtype=np.float32)
            _stamp_eyes(stamp, landmarks_px, 2.0)
            ink = np.where(stamp > 0.5, 255, ink).astype(np.uint8)
    except Exception:
        pass

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
        "parsed": parsed,
    }


def pencil_sketch(image: np.ndarray) -> np.ndarray:
    """Fallback clásico de OpenCV, para comparar con XDoG."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, sketch = cv2.pencilSketch(image, sigma_s=50, sigma_r=0.07, shade_factor=0.05)
    return sketch
