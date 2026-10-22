"""Fase 2: quitar fondo con U2Net-p (4.7 MB) en CPU via onnxruntime.

Misma firma que `bg_opencv.remove_background`, asi server y UI no cambian.
"""

from __future__ import annotations

import os
import time

import cv2
import numpy as np

from . import BgResult, bbox_of, largest_component

_SESSION = None
_ENGINE_NAME = ""
# Se prefiere el grande (persona); si no esta, el pequeno generico.
_MODEL_CANDIDATES = (
    ("onnx-u2net-huseg", ("u2net_human_seg.onnx",)),
    ("onnx-u2netp", ("u2netp.onnx",)),
)
_MODEL_PATHS = ()
for _name, _files in _MODEL_CANDIDATES:
    for _f in _files:
        _MODEL_PATHS += (
            os.path.join("models", _f),
            os.path.join(os.path.dirname(__file__), "..", "models", _f),
        )
SIZE = 320
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def available() -> bool:
    return any(os.path.exists(p) for p in _MODEL_PATHS)


def _session():
    global _SESSION, _ENGINE_NAME
    if _SESSION is None:
        import onnxruntime as ort

        for name, files in _MODEL_CANDIDATES:
            for f in files:
                for base in (".", os.path.join(os.path.dirname(__file__), "..")):
                    path = os.path.join(base, "models", f)
                    if os.path.exists(path):
                        _SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
                        _ENGINE_NAME = name
                        break
                if _SESSION is not None:
                    break
            if _SESSION is not None:
                break
        if _SESSION is None:
            raise FileNotFoundError("ningun .onnx en models/")
    return _SESSION


def engine_name() -> str:
    _session()
    return _ENGINE_NAME


def remove_background(bgr: np.ndarray, max_side: int = 640) -> BgResult:
    t0 = time.perf_counter()
    oh, ow = bgr.shape[:2]
    scale = min(1.0, float(max_side) / max(oh, ow))
    if scale < 1.0:
        small = cv2.resize(bgr, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = bgr
    sh, sw = small.shape[:2]
    t_resize = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR)
    tensor = (resized.astype(np.float32) / 255.0 - MEAN) / STD
    tensor = tensor.transpose(2, 0, 1)[None, :]
    t_pre = (time.perf_counter() - t1) * 1000

    t2 = time.perf_counter()
    session = _session()
    name = session.get_inputs()[0].name
    out_name = session.get_outputs()[-1].name
    (prob,) = session.run([out_name], {name: tensor})
    prob = np.asarray(prob, dtype=np.float64)[0, 0]
    if not (prob.min() >= 0.0 and prob.max() <= 1.0):
        prob = 1.0 / (1.0 + np.exp(-prob))
    mask_small = (prob > 0.5).astype(np.uint8) * 255
    t_infer = (time.perf_counter() - t2) * 1000

    t3 = time.perf_counter()
    mask_small = cv2.resize(mask_small, (sw, sh), interpolation=cv2.INTER_LINEAR)
    mask_small = (mask_small > 127).astype(np.uint8) * 255
    # Refinado: GrabCut solo en una banda alrededor del borde. Ajusta el
    # corte a los bordes reales de color (recupera orejas, quita halos).
    k7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    k31 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31))
    sure_fg = cv2.erode(mask_small, k7)
    band = cv2.dilate(mask_small, k31)
    gc_mask = np.where(band == 0, cv2.GC_BGD, cv2.GC_PR_BGD).astype(np.uint8)
    gc_mask[sure_fg > 0] = cv2.GC_FGD
    cv2.setRNGSeed(123)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(small, gc_mask, None, bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)
    mask_small = np.where(
        (gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD), 255, 0
    ).astype(np.uint8)
    keep = largest_component(mask_small)
    # Abre con kernel medio ANTES de elegir componente: rompe los puentes
    # delgados por donde el fondo pegado al borde se cuela al sujeto.
    k7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    keep = cv2.morphologyEx(keep, cv2.MORPH_OPEN, k7)
    keep = largest_component(keep)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, kernel)
    # Tira pegada a los bordes laterales/superior: corta los puentes por
    # donde el fondo (sillas, muebles) se cuelga del sujeto, sin tocar el
    # cuerpo (el borde inferior se respeta porque ahi sale el torso).
    m = max(6, int(0.015 * max(sh, sw)))
    keep[:, :m] = 0
    keep[:, -m:] = 0
    keep[:m, :] = 0
    keep = largest_component(keep)
    # Anclaje por identidad (YuNet, modelo local ya presente): si otra
    # persona quedo conectada por un puente delgado, quedarse solo con la
    # del usuario. El open rompe el puente, se elige el componente con
    # mayor solape con la caja de cara, y se dilata intersectado con la
    # mascara original para recuperar el detalle sin cruzar el puente.
    # Sin cara o sin solape: comportamiento anterior, sin romper nada.
    face_anchored = False
    try:
        from .sketch import face_box

        box = face_box(small)
    except Exception:
        box = None
    if box is not None:
        H_, W_ = keep.shape[:2]
        x, y, w, h = (int(v) for v in box)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W_, x + w), min(H_, y + h)
        if x1 > x0 and y1 > y0:
            k15 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
            opened = cv2.morphologyEx(keep, cv2.MORPH_OPEN, k15)
            count, labels, _stats, _ = cv2.connectedComponentsWithStats(
                (opened > 0).astype(np.uint8), connectivity=8
            )
            best, best_ov = 0, 0
            if count > 1:
                roi = labels[y0:y1, x0:x1]
                for i in range(1, count):
                    ov = int((roi == i).sum())
                    if ov > best_ov:
                        best, best_ov = i, ov
            min_ov = max(100, int(0.05 * (x1 - x0) * (y1 - y0)))
            if best > 0 and best_ov >= min_ov:
                sel = (labels == best).astype(np.uint8) * 255
                k11 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
                grown = cv2.dilate(sel, k11)
                keep = np.where(grown > 0, keep, 0).astype(np.uint8)
                face_anchored = True
    if scale < 1.0:
        keep = cv2.resize(keep, (ow, oh), interpolation=cv2.INTER_LINEAR)
        keep = (keep > 127).astype(np.uint8) * 255
    t_post = (time.perf_counter() - t3) * 1000

    total = (time.perf_counter() - t0) * 1000
    return BgResult(
        mask=keep,
        bbox=bbox_of(keep),
        face_found=True,
        timings_ms={
            "resize": round(t_resize, 1),
            "pre": round(t_pre, 1),
            "infer": round(t_infer, 1),
            "post": round(t_post, 1),
            "total": round(total, 1),
            "face_anchor": face_anchored,
        },
    )
