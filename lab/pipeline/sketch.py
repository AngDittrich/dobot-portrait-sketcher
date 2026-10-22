"""Fase 3: boceto a lineas (XDoG) sobre el recorte, listo para vectorizar."""

from __future__ import annotations

import os
import time

import cv2
import numpy as np

_FACE_CASCADE = None
_YUNET = None
_LANDMARKS = None


def _landmarker():
    """FaceLandmarker MediaPipe: geometria de rasgos, independiente del gradiente."""
    global _LANDMARKS
    if _LANDMARKS is None:
        from pathlib import Path

        from pipeline.landmarks import FaceLandmarks

        here = Path(__file__).resolve()
        for base in (Path("."), here.parent.parent, here.parent):
            path = base / "models" / "face_landmarker.task"
            if path.exists():
                _LANDMARKS = FaceLandmarks(path)
                break
        if _LANDMARKS is None:
            from pipeline.landmarks import FaceLandmarks as _FL

            _LANDMARKS = _FL(Path("models") / "face_landmarker.task")
    return _LANDMARKS


def _yunet():
    """Detector YuNet (ONNX): el Haar cascade fallaba con luz plana de webcam."""
    global _YUNET
    if _YUNET is None:
        for base in (".", os.path.join(os.path.dirname(__file__), "..")):
            path = os.path.join(base, "models", "face_detection_yunet_2023mar.onnx")
            if os.path.exists(path):
                _YUNET = cv2.FaceDetectorYN.create(path, "", (320, 320), 0.6, 0.3, 5000)
                break
    return _YUNET



def _face_detector():
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        for base in (".", os.path.join(os.path.dirname(__file__), "..")):
            path = os.path.join(base, "models", "haarcascade_frontalface_default.xml")
            if os.path.exists(path):
                _FACE_CASCADE = cv2.CascadeClassifier(path)
                break
        if _FACE_CASCADE is not None:
            # Precalentado: el primer detectMultiScale del proceso tarda ~2 s.
            blank = np.zeros((120, 160), np.uint8)
            _FACE_CASCADE.detectMultiScale(blank, scaleFactor=1.3, minNeighbors=5, minSize=(60, 60))
    return _FACE_CASCADE


def face_box(bgr: np.ndarray):
    """Caja de la cara mas grande (x, y, w, h) o None si no hay cara."""
    det = _yunet()
    if det is not None:
        H, W = bgr.shape[:2]
        s = min(1.0, 640.0 / max(H, W))
        small = (
            cv2.resize(bgr, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
            if s < 1.0
            else bgr
        )
        det.setInputSize((small.shape[1], small.shape[0]))
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            x, y, w, h = max(faces[:, :4], key=lambda r: float(r[2] * r[3]))
            return (np.array([x, y, w, h]) / s).astype(int)

    clf = _face_detector()
    if clf is None:
        return None
    H, W = bgr.shape[:2]
    gray8 = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    s = min(1.0, 480.0 / max(H, W))
    small = cv2.resize(gray8, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA) if s < 1.0 else gray8
    faces = clf.detectMultiScale(small, scaleFactor=1.3, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
    return (np.array([x, y, w, h]) / s).astype(int)


def _silhouette_top(bgr: np.ndarray, x: int, w: int) -> int | None:
    """Primera fila con silueta (no blanca) en la columna de la cara."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    x0 = max(0, x)
    band = gray[:, x0:max(x0 + 1, x + w)]
    if band.size == 0:
        return None
    rows = np.where((band < 245).sum(axis=1) > max(2, int(0.02 * band.shape[1])))[0]
    return int(rows[0]) if len(rows) else None


def crop_to_head(bgr: np.ndarray, target_px: int = 900) -> tuple[np.ndarray, bool]:
    """Recorta cabeza + hombros y agranda hasta `target_px`.

    Sin recorte la cabeza ocupa un tercio del papel y el robot gasta el mismo
    tiempo de dibujo en el fondo; con demasiado zoom se corta el pelo. El alto
    se mide desde la silueta (arriba del pelo) hasta el menton, no desde la
    caja del detector: YuNet a veces ya incluye el pelo y a veces no, y ahi
    estaba el corte. Devuelve (imagen, recortado).
    """
    box = face_box(bgr)
    if box is None:
        return bgr, False
    H, W = bgr.shape[:2]
    x, y, w, h = [int(v) for v in box]
    cx = x + w / 2.0
    chin = y + h
    head_top = _silhouette_top(bgr, x, w)
    if head_top is None or head_top >= chin - 0.2 * h:
        head_top = y - 0.35 * h  # sin silueta util: aproximar por la caja
    head_h = chin - head_top
    top = head_top - 0.07 * head_h   # aire sobre el pelo
    bottom = chin + 0.72 * head_h    # cuello y hombros
    out_h = int(round(bottom - top))
    out_w = int(round(out_h * 0.8))  # lienzo vertical 4:5
    if out_h < 8 or out_w < 8:
        return bgr, False
    x0 = int(round(cx - out_w / 2.0))
    y0 = int(round(top))
    # Lienzo blanco: si la caja se sale de la foto, el aire queda blanco en
    # vez de recortar y volver a hacer zoom.
    canvas = np.full((out_h, out_w, 3), 255, np.uint8)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(W, x0 + out_w), min(H, y0 + out_h)
    if sx1 <= sx0 or sy1 <= sy0:
        return bgr, False
    canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = bgr[sy0:sy1, sx0:sx1]

    # Donde la foto original se corta (borde del cuadro), el contenido termina
    # en linea recta y el boceto la dibuja como una raya horizontal. Se apaga
    # el contenido hacia blanco antes del corte, como un retrato que se funde.
    alpha = np.ones((out_h, out_w), np.float32)
    ramp = max(8, int(0.10 * out_h))
    bottom_pad = (y0 + out_h) - sy1
    top_pad = sy0 - y0
    left_pad = sx0 - x0
    right_pad = (x0 + out_w) - sx1
    fade_down = np.linspace(1.0, 0.0, ramp, dtype=np.float32)
    if bottom_pad > 0:
        e = sy1 - y0
        s = max(0, e - ramp)
        n = e - s
        alpha[s:e, :] = np.minimum(alpha[s:e, :], fade_down[ramp - n:][:, None])
    if top_pad > 0:
        n = min(out_h, ramp)
        alpha[0:n, :] = np.minimum(alpha[0:n, :], np.linspace(0.0, 1.0, n, dtype=np.float32)[:, None])
    if right_pad > 0:
        e = sx1 - x0
        s = max(0, e - ramp)
        n = e - s
        alpha[:, s:e] = np.minimum(alpha[:, s:e], fade_down[ramp - n:][None, :])
    if left_pad > 0:
        n = min(out_w, ramp)
        alpha[:, 0:n] = np.minimum(alpha[:, 0:n], np.linspace(0.0, 1.0, n, dtype=np.float32)[None, :])
    a3 = alpha[..., None]
    canvas = (canvas.astype(np.float32) * a3 + 255.0 * (1.0 - a3)).astype(np.uint8)

    crop = canvas
    longest = max(crop.shape[:2])
    if longest < target_px:
        scale = min(2.5, target_px / longest)
        crop = cv2.resize(
            crop,
            (int(crop.shape[1] * scale), int(crop.shape[0] * scale)),
            interpolation=cv2.INTER_CUBIC,
        )
    return crop, True


def to_gray(bgr: np.ndarray, contrast: float = 0.4) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Valores originales del lab (los que daban el resultado limpio).
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=35, sigmaSpace=7)
    contrast = float(np.clip(contrast, 0.0, 1.0))
    if contrast > 0:
        eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        gray = cv2.addWeighted(gray, 1.0 - contrast, eq, contrast, 0)
    return gray.astype(np.float32) / 255.0


def xdog(
    gray: np.ndarray,
    sigma: float = 1.2,
    k: float = 1.6,
    tau: float = 0.98,
    epsilon: float = 0.0,
    phi: float = 40.0,
) -> np.ndarray:
    """Intensidad de linea en 0..1 (0 = sin linea)."""
    sigma = max(0.1, float(sigma))
    g1 = cv2.GaussianBlur(gray, (0, 0), sigma)
    g2 = cv2.GaussianBlur(gray, (0, 0), sigma * max(1.01, float(k)))
    dog = g1 - float(tau) * g2
    peak = float(np.abs(dog).max())
    if peak > 1e-6:
        dog = dog / peak
    out = 1.0 + np.tanh(float(phi) * (dog - float(epsilon)))
    return np.clip(1.0 - np.clip(out, 0.0, 1.0), 0.0, 1.0)


def render_lines(lines: np.ndarray) -> np.ndarray:
    img = np.clip(255.0 * (1.0 - lines), 0, 255).astype(np.uint8)
    return cv2.medianBlur(img, 3)


def binarize(lines: np.ndarray, threshold: float = 0.20) -> np.ndarray:
    """Lineas -> fondo blanco, linea negra (para mostrar / vectorizar)."""
    mask = (lines >= threshold).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return 255 - mask


def _dark_glasses(gray: np.ndarray, pts: np.ndarray) -> tuple[bool, float]:
    """True si hay lentes oscuros. Compara brillo promedio de ojos vs mejillas."""
    H, W = gray.shape[:2]
    px = pts.copy()
    px[:, 0] *= W
    px[:, 1] *= H

    # Si el modelo no tiene el refinamiento de iris (puntos > 468),
    # usamos los puntos aproximados del centro del ojo en el modelo base.
    if len(px) > 468:
        eye_ids = (468, 473)
    else:
        eye_ids = (159, 386)  # Puntos superiores del parpado (aproximacion aceptable)

    cheek_ids = (205, 425)  # Mejillas izq/der

    def sample(idx, r=4):
        x, y = int(px[idx][0]), int(px[idx][1])
        x0, x1 = max(0, x - r), min(W, x + r)
        y0, y1 = max(0, y - r), min(H, y + r)
        # Evitamos colapsos si el ROI queda vacio por estar al borde
        if x0 == x1 or y0 == y1:
            return 127.0
        return float(gray[y0:y1, x0:x1].mean())

    # Promediamos para mitigar sombras laterales de iluminacion
    eye_mean = sum(sample(i) for i in eye_ids) / 2.0
    cheek_mean = sum(sample(i) for i in cheek_ids) / 2.0

    ratio = eye_mean / max(cheek_mean, 1e-6)

    # 0.45 es buen umbral, pero un ojo normal en sombra rara vez baja de 0.55
    return ratio < 0.45, ratio


def _torso_fade(shape, chin_y, face_h):
    """Mascara vertical 1..0: disuelve el torso bajo el pecho (viñeta).

    Las arrugas de la playera no tienen contraste real y el XDoG las dibuja
    como curvas sueltas que deforman el cuerpo. El fundido apaga el mapa de
    lineas hacia abajo sin tocar cara, cuello ni audifonos (quedan arriba
    del arranque). Rampa larga para no dejar un corte que el umbral dibuje.
    """
    H, W = shape[:2]
    start = chin_y + 0.7 * face_h
    end = min(float(H), chin_y + 1.8 * face_h)
    if end <= start or face_h <= 0:
        return None
    rows = np.arange(H, dtype=np.float32)
    fade = np.clip((end - rows) / max(1.0, end - start), 0.0, 1.0)
    return np.broadcast_to(fade[:, None], (H, W))


def sketch_cutout(cutout_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Recorte sobre blanco -> (boceto gris, lineas binarias, tiempos).

    Version base original del lab (la que daba el resultado limpio):
    XDoG directo + binarizado 0.20. Sin recorte con zoom, sin boost por zona,
    sin landmarks. Todo eso se probo despues y ensucio el dibujo.
    """
    t0 = time.perf_counter()
    gray = to_gray(cutout_bgr)
    t_gray = (time.perf_counter() - t0) * 1000
    lines = xdog(gray)
    t_xdog = (time.perf_counter() - t0) * 1000 - t_gray
    # Rasgos por geometria (MediaPipe, trazo fino): la abertura de la boca,
    # la nariz y los ojos no dependen del gradiente, asi que sobreviven a la
    # luz plana. Con lentes oscuros no se dibujan ojos: no hay nada que ver
    # ahi y el marco lo pone el XDoG. Ambos mapas usan 1.0 = linea, por eso
    # la fusion es con maximum.
    glasses, ratio = "clear", 1.0
    pts = None
    lm_all = None
    try:
        lm = _landmarker()
        pts = lm.detect(cutout_bgr) if lm is not None and lm.available else None
        if pts is not None:
            raw = cv2.cvtColor(cutout_bgr, cv2.COLOR_BGR2GRAY)
            dark, ratio = _dark_glasses(raw, pts)
            glasses = "dark" if dark else "clear"
            Hc, Wc = cutout_bgr.shape[:2]
            scaled = pts.copy()
            scaled[:, 0] *= Wc
            scaled[:, 1] *= Hc
            features = (
                ("jaw", "brows", "lips", "nose")
                if dark
                else ("jaw", "brows", "eyes", "lips", "nose")
            )
            # Ojos en base (1 px), solo cejas reforzadas (2 px): con maximum
            # no hay peso fraccional y la nariz ya esta en el minimo de 1 px.
            # Con lentes oscuros no hay ojos tampoco aqui.
            _strong = [f for f in ("brows",) if f in features]
            _base = [f for f in features if f not in _strong]
            lm_base = lm.draw_lines(scaled, (Wc, Hc), thickness=1.2, features=tuple(_base))
            lm_strong = lm.draw_lines(scaled, (Wc, Hc), thickness=1.5, features=tuple(_strong))
            lm_all = np.maximum(lm_base, lm_strong)
            lines = np.maximum(lines, lm_all)
    except Exception:
        pass
    # Fundido inferior: apaga arrugas de playera bajo el pecho. Anclado al
    # menton (geometria, no fraccion de imagen) para que no dependa de que
    # tan cerca este la silla. Sin cara no hay fundido.
    faded = False
    try:
        if pts is not None:
            from pipeline.landmarks import CHIN, LEFT_EYE_OUTER, RIGHT_EYE_OUTER

            Hf, Wf = cutout_bgr.shape[:2]
            eye_y = 0.5 * (float(pts[RIGHT_EYE_OUTER][1]) + float(pts[LEFT_EYE_OUTER][1])) * Hf
            chin_y = float(pts[CHIN][1]) * Hf
            fade = _torso_fade((Hf, Wf), chin_y, chin_y - eye_y)
            if fade is not None:
                lines = lines * fade
                faded = True
    except Exception:
        pass
    # Tratamiento por zonas con mascara facial de landmarks: adentro se
    # conserva todo (los rasgos los puso la geometria); afuera solo se
    # atenua lo debil (marcos de lentes y pelo fuerte sobreviven) y el
    # umbral es mas exigente. Sin cara no hay zonas: todo global.
    zoned = False
    try:
        if pts is not None:
            Hm, Wm = cutout_bgr.shape[:2]
            hull = cv2.convexHull(np.round(scaled[lm.oval_indices()]).astype(np.int32))
            m = np.zeros((Hm, Wm), np.float32)
            cv2.fillConvexPoly(m, hull, 1.0)
            mask = cv2.GaussianBlur(m, (0, 0), max(3, int(0.01 * (Wm + Hm) / 2)))
            outside = 1.0 - mask
            weak = (lines < 0.5).astype(np.float32)
            lines = lines * (1.0 - outside * weak * 0.8)
            # EXPERIMENTO reversible (oreja/cuello, con plan de reversion):
            # la oreja sale gruesa porque el XDoG dispara sobre el escalon
            # del borde; se atenua x0.6 solo fuera del ovalo y solo entre
            # la linea de ojos y el menton (ahi viven las orejas; el pelo
            # de arriba y la mandibula de abajo no se tocan). Las dos
            # verticales del cuello se aclaran x0.8 fuera de la cara para
            # que la mandibula tenga mas peso relativo. Si come pelo o
            # mandibula, se quita este bloque y queda solo la limpieza.
            try:
                from pipeline.landmarks import CHIN as _EC
                from pipeline.landmarks import LEFT_EYE_OUTER as _EL
                from pipeline.landmarks import RIGHT_EYE_OUTER as _ER

                _eey = 0.5 * (float(pts[_ER][1]) + float(pts[_EL][1])) * Hm
                _ech = float(pts[_EC][1]) * Hm
                _hx0 = int(hull[..., 0].min())
                _hx1 = int(hull[..., 0].max())
                _mg = int(0.03 * Wm)
                _ear = np.zeros((Hm, Wm), np.float32)
                _ear[max(0, int(_eey)):min(Hm, int(_ech)), :] = 1.0
                _side = np.zeros((Hm, Wm), np.float32)
                _side[:, :max(0, _hx0 + _mg)] = 1.0
                _side[:, min(Wm, _hx1 - _mg):] = 1.0
                lines = lines * (1.0 - 0.4 * _ear * _side)
                _nb = np.zeros((Hm, Wm), np.float32)
                _nb[int(_ech):min(Hm, int(_ech + 0.7 * max(1.0, _ech - _eey))), :] = 1.0
                lines = lines * (1.0 - 0.2 * _nb * outside)
            except Exception:
                pass
            binary = binarize_map(lines, 0.28 - 0.16 * mask)
            if lm_all is not None:
                # Limpieza selectiva en piel: tinta debil y aislada adentro
                # de la cara que no toca ningun rasgo. Lo fuerte sobrevive
                # siempre y los rasgos se protegen dilatando su mapa.
                protect = (
                    cv2.dilate(
                        (lm_all > 0.5).astype(np.uint8),
                        np.ones((3, 3), np.uint8),
                    )
                    > 0
                )
                inside = mask > 0.5
                weak_skin = (
                    (binary == 0) & inside & (lines < 0.5) & ~protect
                ).astype(np.uint8) * 255
                weak_keep = remove_specks(weak_skin, 16)
                binary = np.where(
                    (weak_skin == 255) & (weak_keep == 0), 255, binary
                ).astype(np.uint8)
                # Cuello/hombros: banda entre el menton y el arranque del
                # fundido, fuera de la cara. Misma regla que en piel pero
                # mas alta (<80 px): ahi no hay rasgos que proteger, solo
                # pelusa y arrugas sueltas. Lo largo y fuerte (collares,
                # audifonos, mandibula protegida) sobrevive siempre.
                from pipeline.landmarks import CHIN as _CHIN
                from pipeline.landmarks import LEFT_EYE_OUTER as _LEO
                from pipeline.landmarks import RIGHT_EYE_OUTER as _REO
                _eye_y = 0.5 * (float(pts[_REO][1]) + float(pts[_LEO][1])) * Hm
                _chin_y = float(pts[_CHIN][1]) * Hm
                _face_h = max(1.0, _chin_y - _eye_y)
                _n0, _n1 = int(_chin_y), int(min(Hm, _chin_y + 0.7 * _face_h))
                if _n1 > _n0:
                    _band = np.zeros((Hm, Wm), bool)
                    _band[_n0:_n1, :] = True
                    weak_neck = (
                        (binary == 0) & ~inside & _band & (lines < 0.5) & ~protect
                    ).astype(np.uint8) * 255
                    neck_keep = remove_specks(weak_neck, 80)
                    binary = np.where(
                        (weak_neck == 255) & (neck_keep == 0), 255, binary
                    ).astype(np.uint8)
            zoned = True
    except Exception:
        pass
    if not zoned:
        binary = binarize(lines)
    sketch = render_lines(lines)
    total = (time.perf_counter() - t0) * 1000
    return sketch, binary, {
        "gray": round(t_gray, 1),
        "xdog": round(t_xdog, 1),
        "total": round(total, 1),
        "glasses": glasses,
        "glasses_ratio": round(float(ratio), 3),
        "fade": faded,
        "zoned": zoned,
    }


# Manchas menores a esto se consideran ruido, no dibujo.
SPECK_AREA = 8


def binarize_mask(lines: np.ndarray, thr) -> np.ndarray:
    """Umbral por pixel (escalar o mapa): 255 donde hay linea."""
    mask = (lines >= thr).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def remove_specks(mask: np.ndarray, min_area: int = SPECK_AREA) -> np.ndarray:
    """Borra las componentes de menos de `min_area` px."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros_like(mask)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep[labels == i] = 255
    return keep


def binarize_map(lines: np.ndarray, thr) -> np.ndarray:
    """Umbral por pixel: mas bajo dentro de la cara, normal fuera."""
    return 255 - remove_specks(binarize_mask(lines, thr))


def _face_zone(bgr: np.ndarray) -> np.ndarray:
    """Mapa 0..1 con la zona de la cara (rectangulo ampliado, borde suave)."""
    H, W = bgr.shape[:2]
    box = face_box(bgr)
    if box is None:
        return np.zeros((H, W), np.float32)
    x, y, w, h = [int(v) for v in box]
    # Rectangulo ampliado: incluye pelo, orejas y cuello.
    x0 = max(0, int(x - 0.25 * w))
    y0 = max(0, int(y - 0.35 * h))
    x1 = min(W, int(x + 1.25 * w))
    y1 = min(H, int(y + 1.35 * h))
    # Zona en baja resolucion (el blur grande en full-res tarda segundos).
    ds = 0.25
    zone = np.zeros((max(1, int(H * ds)), max(1, int(W * ds))), np.float32)
    zone[int(y0 * ds):int(y1 * ds), int(x0 * ds):int(x1 * ds)] = 1.0
    feather = max(3, min(12, int(0.02 * max(w, h) * ds)) | 1)
    zone = cv2.GaussianBlur(zone, (0, 0), feather)
    return cv2.resize(zone, (W, H), interpolation=cv2.INTER_LINEAR)
