"""Lab v2 desde cero: webcam -> quitar fondo (CPU, solo OpenCV)."""

from __future__ import annotations

import base64
import time

import cv2
import numpy as np
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.bg_onnx import available as onnx_available
from pipeline.bg_onnx import engine_name as onnx_engine_name
from pipeline.bg_onnx import remove_background as remove_background_onnx
from pipeline.bg_opencv import apply_mask, remove_background
from pipeline.bg_opencv import remove_background as remove_background_opencv
from pipeline.sketch import crop_to_head, sketch_cutout

ENGINE = onnx_engine_name() if onnx_available() else "opencv-grabcut"
print(f"[lab] engine: {ENGINE}", flush=True)

app = FastAPI(title="Lab v2 · fondo")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/samples", StaticFiles(directory="samples"), name="samples")


class RemoveBgIn(BaseModel):
    image: str  # dataURL jpeg/png del navegador


def decode_data_url(data_url: str) -> np.ndarray:
    _, _, b64 = data_url.partition(",")
    raw = base64.b64decode(b64)
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("no se pudo decodificar la imagen")
    return img


def encode_png(img: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("no se pudo codificar PNG")
    return "data:image/png;base64," + base64.b64encode(buf.tobytes()).decode()


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/remove-bg")
def remove_bg(payload: RemoveBgIn):
    t0 = time.perf_counter()
    cutout, result, engine, scale = _cutout(decode_data_url(payload.image))[:4]
    x, y, bw, bh = result.bbox
    bbox = [int(x / scale), int(y / scale), int(bw / scale), int(bh / scale)]
    total = (time.perf_counter() - t0) * 1000
    return {
        "engine": engine,
        "cutout_png": encode_png(cutout),
        "mask_png": encode_png(result.mask),
        "bbox": bbox,
        "face_found": result.face_found,
        "size": [int(cutout.shape[1]), int(cutout.shape[0])],
        "timings_ms": {**result.timings_ms, "request": round(total, 1)},
    }


def _cutout(bgr: np.ndarray):
    """Foto -> (recorte sobre negro, resultado, engine, escala)."""
    h, w = bgr.shape[:2]
    scale = 1.0
    if max(h, w) > 1600:
        scale = 1600.0 / max(h, w)
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    try:
        if ENGINE.startswith("onnx-"):
            result = remove_background_onnx(bgr)
        else:
            result = remove_background_opencv(bgr)
    except Exception:
        result = remove_background_opencv(bgr)
        engine = "opencv-grabcut-fallback"
    else:
        engine = ENGINE
    cutout = apply_mask(bgr, result.mask)
    return cutout, result, engine, scale, bgr


@app.post("/api/sketch")
def sketch(payload: RemoveBgIn):
    t0 = time.perf_counter()
    cutout, result, engine, _, bgr = _cutout(decode_data_url(payload.image))
    # Sin recorte con zoom: el encuadre original de cuerpo entero es el que
    # daba el resultado limpio. El crop agrandaba 2x el ruido y los artefactos.
    alpha = (result.mask > 127).astype(np.float32)[..., None]
    on_white = (bgr.astype(np.float32) * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
    gray_sketch, lines, t_sketch = sketch_cutout(on_white)
    total = (time.perf_counter() - t0) * 1000
    return {
        "engine": engine,
        "cropped": False,
        "glasses": t_sketch.get("glasses", "unknown"),
        "sketch_png": encode_png(gray_sketch),
        "lines_png": encode_png(lines),
        "timings_ms": {**t_sketch, "request": round(total, 1)},
    }


try:
    _warm = cv2.imread("samples/retrato_hombre_1.jpg")
    if _warm is None:
        _warm = cv2.imread("samples/retrato_mujer_1.jpg")
    if _warm is not None:
        _wc, _wr, _, _, _wb = _cutout(_warm)
        _wa = (_wr.mask > 127).astype(np.float32)[..., None]
        _ww = (_wb.astype(np.float32) * _wa + 255.0 * (1.0 - _wa)).astype(np.uint8)
        sketch_cutout(_ww)
        print("[lab] warmup ok", flush=True)
except Exception as e:
    print(f"[lab] warmup skip: {e}", flush=True)
