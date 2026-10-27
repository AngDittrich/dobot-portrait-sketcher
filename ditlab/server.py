"""Foto de la webcam y cada capa del boceto que dibuja la cabina.

Usa el pipeline de ``windows/backend`` (YuNet, U2Net, XDoG, vectorizado).
Los controles rehacen solo el boceto: la segmentación queda en memoria.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT.parent / "windows" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.imaging import decode_data_url, encode_data_url, fit_max_side  # noqa: E402
from app.pipeline import sketch as sketch_ops  # noqa: E402
from app.pipeline import vectorize as vectorize_ops  # noqa: E402
from app.pipeline.portrait import PortraitRenderer  # noqa: E402
from app.pipeline.sketch import (  # noqa: E402
    INK_HIGH,
    INK_SPAN,
    LAB_BILATERAL,
    LAB_CONTRAST,
    LAB_PHI,
    LAB_SIGMA,
    SPECK_AREA,
)

MODELS_DIR = Path(os.environ.get("MODELS_DIR", BACKEND / "models"))
STATIC = ROOT / "static"
MAX_CAPTURES = 4

app = FastAPI(title="Ditlab")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

renderer = PortraitRenderer(MODELS_DIR)
captures: dict[str, dict] = {}


class CaptureIn(BaseModel):
    image: str


class TuneIn(BaseModel):
    id: str
    sigma: float = Field(LAB_SIGMA, ge=0.2, le=4.0)
    phi: float = Field(LAB_PHI, ge=1.0, le=80.0)
    contrast: float = Field(LAB_CONTRAST, ge=0.0, le=1.0)
    bilateral: float = Field(LAB_BILATERAL, ge=1.0, le=80.0)
    ink_high: float = Field(INK_HIGH, ge=0.02, le=0.9)
    ink_span: float = Field(INK_SPAN, ge=0.0, le=0.5)
    speck_area: int = Field(SPECK_AREA, ge=1, le=80)
    min_stroke_px: float = Field(12.0, ge=1.0, le=80.0)
    simplify_px: float = Field(1.2, ge=0.0, le=5.0)
    max_draw_seconds: float = Field(150.0, ge=5.0, le=600.0)


def _require_models() -> None:
    missing = []
    if not renderer.u2net.available:
        missing.append(Path(renderer.u2net.model_path).name)
    if not renderer.face.available:
        missing.append(Path(renderer.face.model_path).name)
    if missing:
        raise HTTPException(
            status_code=503,
            detail=(
                "Faltan modelos: "
                + ", ".join(missing)
                + ". Corre windows/backend/download_models.py"
            ),
        )


def _layer(layer_id: str, title: str, note: str, image: np.ndarray) -> dict:
    height, width = image.shape[:2]
    return {
        "id": layer_id,
        "title": title,
        "note": note,
        "width": int(width),
        "height": int(height),
        "image": encode_data_url(image),
    }


def _gray_image(values: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(values, dtype=np.float32) * 255.0, 0, 255).astype(np.uint8)


def _ink_image(lines: np.ndarray) -> np.ndarray:
    return np.clip(255.0 * (1.0 - np.asarray(lines, dtype=np.float32)), 0, 255).astype(np.uint8)


def _fit_stage(image: np.ndarray, width: int, height: int) -> np.ndarray:
    if image.shape[1] == width and image.shape[0] == height:
        return image
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)


def _face_view(fitted: np.ndarray, face: dict | None) -> np.ndarray:
    view = fitted.copy()
    if face is None:
        return view
    x, y, width, height = (int(round(float(value))) for value in face["bbox"])
    cv2.rectangle(view, (x, y), (x + width, y + height), (255, 255, 255), 2, cv2.LINE_AA)
    return view


def _vector_layers(mask: np.ndarray, params: TuneIn) -> list[dict]:
    height, width = mask.shape[:2]
    strokes = vectorize_ops.strokes_from_mask(mask, min_length_px=params.min_stroke_px)
    simplified = [vectorize_ops.simplify_stroke(stroke, params.simplify_px) for stroke in strokes]
    ordered = [stroke for stroke, _ in vectorize_ops.order_strokes(simplified)]
    pruned = vectorize_ops.prune_to_budget(
        ordered,
        width,
        max_seconds=params.max_draw_seconds,
        target_width_mm=140.0,
    )
    return [
        _layer(
            "contours",
            "Contorno de la tinta",
            (
                f"{len(strokes)} trazos. Es el borde de cada mancha, no su centro: "
                "un trazo grueso sale doble."
            ),
            vectorize_ops.render_black_strokes(strokes, width, height, thickness=2),
        ),
        _layer(
            "simplified",
            "Trazos simplificados",
            f"{len(simplified)} trazos, con menos puntos en cada curva.",
            vectorize_ops.render_black_strokes(simplified, width, height, thickness=2),
        ),
        _layer(
            "robot",
            "Lo que dibujaría el robot",
            (
                f"{len(pruned)} trazos después del tope de tiempo. "
                "Esto es lo que iría al papel."
            ),
            vectorize_ops.render_black_strokes(pruned, width, height, thickness=2),
        ),
    ]


def _sketch_layers(stages: dict, params: TuneIn) -> list[dict]:
    landmarks = stages.get("landmarks")
    if landmarks is None:
        mark_note = "No hubo cara utilizable, así que esta capa queda en blanco."
        mark_img = np.full_like(_ink_image(stages["xdog"]), 255)
    else:
        mark_note = "Geometría de la cara: mandíbula, cejas, ojos, labios y nariz."
        mark_img = _ink_image(landmarks)
    return [
        _layer(
            "gray",
            "Gris",
            "Bilateral y contraste local. Aquí se decide qué arruga sigue viva.",
            _gray_image(stages["gray"]),
        ),
        _layer(
            "xdog",
            "Líneas del boceto",
            (
                f"XDoG con sigma {params.sigma:g} y phi {params.phi:g}, "
                "antes de sumar los rasgos."
            ),
            _ink_image(stages["xdog"]),
        ),
        _layer("landmarks", "Rasgos de la cara", mark_note, mark_img),
        _layer(
            "fused",
            "Boceto con torso y cara",
            (
                "Líneas y rasgos juntos. Abajo se apaga la playera y dentro "
                "de la cara se admite tinta más débil."
            ),
            _ink_image(stages["fused"]),
        ),
        _layer(
            "ink",
            "Tinta",
            (
                f"Umbral {params.ink_high:g} − {params.ink_span:g} × zona de la cara. "
                f"Motas de menos de {params.speck_area} px fuera."
            ),
            stages["ink"],
        ),
        *_vector_layers(stages["ink"], params),
    ]


def _remember(capture_id: str, crop: np.ndarray, scaled, landmarker) -> None:
    captures[capture_id] = {
        "crop": crop,
        "landmarks": scaled,
        "landmarker": landmarker,
    }
    while len(captures) > MAX_CAPTURES:
        captures.pop(next(iter(captures)))


def _defaults() -> TuneIn:
    return TuneIn(id="_")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    models = renderer.health()
    return {
        "ok": bool(models["u2net"] and models["face_detector"]),
        "models": models,
        "models_dir": str(MODELS_DIR),
    }


@app.post("/api/capture")
def capture(payload: CaptureIn) -> dict:
    _require_models()
    started = time.perf_counter()
    try:
        raw = decode_data_url(payload.image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    fitted = fit_max_side(raw)
    params = _defaults()
    stages: dict = {}
    try:
        # lab_sigma pisa a sigma dentro de render; no se mandan los dos.
        portrait = renderer.render(
            fitted,
            stages=stages,
            lab_sigma=params.sigma,
            lab_phi=params.phi,
            lab_contrast=params.contrast,
            lab_bilateral=params.bilateral,
            ink_high=params.ink_high,
            ink_span=params.ink_span,
            speck_area=params.speck_area,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"No se pudo procesar la foto: {exc}") from exc

    face = portrait["face"]
    height, width = fitted.shape[:2]
    work_w, work_h = stages.get("work_wh", (width, height))
    same_size = raw.shape[1] == width and raw.shape[0] == height
    fit_note = (
        "Ya cabía en 2048 px, así que es la misma foto."
        if same_size
        else "El lado mayor quedó en 2048 px. El resto del pipeline usa esta."
    )
    face_note = (
        "YuNet no encontró una cara. El recorte será la foto entera."
        if face is None
        else "La caja es la cara. De aquí se arma el recorte de la cabeza."
    )
    layers = [
        _layer(
            "raw",
            "Foto de la cámara",
            "Tal como salió de la webcam, antes de cualquier proceso.",
            raw,
        ),
        _layer("fitted", "Foto a tamaño de trabajo", fit_note, fitted),
        _layer("face", "Cara detectada", face_note, _face_view(fitted, face)),
        _layer(
            "prob",
            "Probabilidad de persona",
            (
                "U2Net mira la foto a 320 px. Este mapa se calculó a "
                f"{work_w}×{work_h} y está estirado a la foto: el pelo nace borroso aquí."
            ),
            _gray_image(_fit_stage(stages["prob"], width, height)),
        ),
        _layer(
            "mask_before",
            "Máscara antes de afinar el borde",
            "Umbral a la mitad de esa probabilidad, todavía sin GrabCut.",
            _fit_stage(stages["mask_before"], width, height),
        ),
        _layer(
            "mask_after",
            "Máscara de persona",
            "GrabCut retoca solo la banda del borde: orejas, halo, lo que se pegó del fondo.",
            _fit_stage(stages["mask_after"], width, height),
        ),
        _layer(
            "cutout",
            "Persona sobre blanco",
            "La máscara compuesta sobre blanco. El boceto ve este borde duro.",
            portrait["cutout"],
        ),
        _layer(
            "crop",
            "Recorte de la cabeza",
            "Pelo hasta el mentón, agrandado hasta 900 px. Ese aumento marca el grano.",
            portrait["crop"],
        ),
        *_sketch_layers(stages, params),
    ]
    capture_id = uuid.uuid4().hex[:12]
    scaled = stages.get("scaled_landmarks")
    _remember(
        capture_id,
        portrait["crop"],
        scaled,
        renderer.landmarks if scaled is not None else None,
    )
    return {
        "id": capture_id,
        "ms": round((time.perf_counter() - started) * 1000),
        "face": face is not None,
        "layers": layers,
    }


@app.post("/api/retune")
def retune(payload: TuneIn) -> dict:
    cached = captures.get(payload.id)
    if cached is None:
        raise HTTPException(status_code=404, detail="Esa foto ya no está en memoria. Tómala otra vez.")
    stages: dict = {}
    try:
        sketch_ops.lab_portrait_lines(
            cached["crop"],
            cached["landmarks"],
            cached["landmarker"],
            sigma=payload.sigma,
            phi=payload.phi,
            contrast=payload.contrast,
            bilateral=payload.bilateral,
            ink_high=payload.ink_high,
            ink_span=payload.ink_span,
            speck_area=payload.speck_area,
            stages=stages,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"No se pudo rehacer el boceto: {exc}") from exc
    return {"id": payload.id, "layers": _sketch_layers(stages, payload)}


print(f"[ditlab] models {renderer.health()} dir={MODELS_DIR}", flush=True)
