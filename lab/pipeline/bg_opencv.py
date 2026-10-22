"""Fase 1: quitar fondo solo con OpenCV en CPU.

Foto -> cara Haar -> rect ampliado (pelo + hombros) -> GrabCut -> limpieza.
Sin modelos ONNX, sin descargas.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from . import BgResult, bbox_of, largest_component

_FACE = None


def _face_cascade() -> cv2.CascadeClassifier | None:
    global _FACE
    if _FACE is None:
        import os

        candidates = [
            os.path.join("models", "haarcascade_frontalface_default.xml"),
            os.path.join(os.path.dirname(__file__), "..", "models",
                         "haarcascade_frontalface_default.xml"),
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
        ]
        for path in candidates:
            if os.path.exists(path):
                cascade = cv2.CascadeClassifier(path)
                if not cascade.empty():
                    _FACE = cascade
                    break
        if _FACE is None:
            return None
    return _FACE


def detect_face(gray: np.ndarray) -> tuple[int, int, int, int] | None:
    cascade = _face_cascade()
    if cascade is None or cascade.empty():
        return None
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60)
    )
    if len(faces) == 0:
        return None
    faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
    return tuple(int(v) for v in faces[0])


def grabcut_rect(
    w: int, h: int, face: tuple[int, int, int, int] | None
) -> tuple[int, int, int, int]:
    if face is None:
        return (int(w * 0.08), int(h * 0.03), int(w * 0.84), int(h * 0.94))
    fx, fy, fw, fh = face
    x = max(2, int(fx - 0.35 * fw))
    y = max(2, int(fy - 0.6 * fh))
    x2 = min(w - 3, int(fx + fw * 1.35))
    y2 = min(h - 3, int(fy + fh * 2.0))
    if x2 - x < 10 or y2 - y < 10:
        return (2, 2, max(10, w - 4), max(10, h - 4))
    return (x, y, x2 - x, y2 - y)


def remove_background(bgr: np.ndarray, max_side: int = 512) -> BgResult:
    t0 = time.perf_counter()
    oh, ow = bgr.shape[:2]
    scale = min(1.0, float(max_side) / max(oh, ow))
    if scale < 1.0:
        small = cv2.resize(bgr, (int(ow * scale), int(oh * scale)), interpolation=cv2.INTER_AREA)
    else:
        small = bgr
        scale = 1.0
    sh, sw = small.shape[:2]
    t_resize = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    face = detect_face(gray)
    t_face = (time.perf_counter() - t1) * 1000

    t2 = time.perf_counter()
    rect = grabcut_rect(sw, sh, face)
    gc_mask = np.zeros((sh, sw), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.setRNGSeed(123)
    cv2.grabCut(small, gc_mask, rect, bgd, fgd, 3, cv2.GC_INIT_WITH_RECT)
    raw = ((gc_mask == cv2.GC_FGD) | (gc_mask == cv2.GC_PR_FGD)).astype(np.uint8) * 255
    t_grabcut = (time.perf_counter() - t2) * 1000

    t3 = time.perf_counter()
    keep = largest_component(raw)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    keep = cv2.morphologyEx(keep, cv2.MORPH_CLOSE, kernel_close)
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    keep = cv2.morphologyEx(keep, cv2.MORPH_OPEN, kernel_open)
    if scale < 1.0:
        keep = cv2.resize(keep, (ow, oh), interpolation=cv2.INTER_LINEAR)
        keep = (keep > 127).astype(np.uint8) * 255
    t_clean = (time.perf_counter() - t3) * 1000

    bbox = bbox_of(keep)
    total = (time.perf_counter() - t0) * 1000
    return BgResult(
        mask=keep,
        bbox=bbox,
        face_found=face is not None,
        timings_ms={
            "resize": round(t_resize, 1),
            "face": round(t_face, 1),
            "grabcut": round(t_grabcut, 1),
            "clean": round(t_clean, 1),
            "total": round(total, 1),
        },
    )


def apply_mask(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """BGR + mascara -> BGRA con transparencia."""
    alpha = (mask > 0).astype(np.uint8) * 255
    b, g, r = cv2.split(bgr)
    return cv2.merge((b, g, r, alpha))


def preview_on_white(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    white = np.full_like(bgr, 255)
    fg = (mask > 0)[:, :, None]
    return np.where(fg, bgr, white).astype(np.uint8)
