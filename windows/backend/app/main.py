"""API de la Cabina de Retratos (Dobot MG400).

Contrato que consume el frontend React (`windows/src`):

    POST /api/sketch        foto (data URL) -> boceto + SVG + trayectoria
    POST /api/jobs          boceto aprobado  -> trabajo de dibujo del robot
    GET  /api/jobs/{id}     progreso del trabajo
    GET  /api/health        estado del backend y de los modelos
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import cv2

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from app.imaging import decode_data_url, encode_data_url, fit_max_side  # noqa: E402
from app.pipeline import vectorize as vectorize_ops  # noqa: E402
from app.pipeline.portrait import PortraitRenderer  # noqa: E402
from app.robot.client import MockRobotClient, Segment, Trajectory  # noqa: E402
from app.store import Job, JobStore, Sketch, SketchStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.environ.get("MODELS_DIR", ROOT / "models"))
# Con SAVE_RAW=1 cada captura cruda queda en disco (windows/backend/captures).
# Sirve para volver a correr el boceto sobre la misma foto al ajustar params.
SAVE_RAW = os.environ.get("SAVE_RAW", "").lower() in {"1", "true", "yes"}
CAPTURES_DIR = ROOT / "captures"


def save_raw_capture(image) -> None:
    """Guarda la foto tal como llegó del navegador (solo con SAVE_RAW=1)."""
    if not SAVE_RAW:
        return
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(str(CAPTURES_DIR / f"capture_{stamp}.jpg"), image)

app = FastAPI(title="Dobot Portrait Sketcher API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

renderer = PortraitRenderer(MODELS_DIR)
robot = MockRobotClient()
sketches = SketchStore()
jobs = JobStore()


class SketchParams(BaseModel):
    """Ajustes del boceto (los mismos que se tocan en el laboratorio)."""

    sigma: float = Field(0.9, ge=0.2, le=4.0)
    phi: float = Field(32.0, ge=1.0, le=80.0)
    epsilon: float = Field(0.0, ge=0.0, le=0.5)
    contrast: float = Field(0.7, ge=0.0, le=1.0)
    threshold: float = Field(0.12, ge=0.02, le=0.9)
    use_landmarks: bool = True
    target_width_mm: float = Field(140.0, ge=20.0, le=400.0)
    spacing_mm: float = Field(1.5, ge=0.2, le=10.0)
    simplify_px: float = Field(1.2, ge=0.0, le=5.0)
    min_stroke_px: float = Field(12.0, ge=1.0, le=80.0)
    # Union de trazos: solo si el hueco es pequeño y la linea sigue recta.
    bridge_gap_px: float = Field(16.0, ge=0.0, le=40.0)
    bridge_angle_deg: float = Field(40.0, ge=0.0, le=180.0)
    # Umbrales del modelo de line art (1 = papel, 0 = linea).
    lineart_strong: float = Field(0.72, ge=0.0, le=1.0)
    lineart_weak: float = Field(0.86, ge=0.0, le=1.0)
    # Ruta opcional de line art estilo anime (opt-in, por defecto XDoG).
    use_lineart: bool = False
    # Tope de tiempo de dibujo: si el retrato sale largo se recorta el
    # detalle fino para que el robot no se eternice en la expo.
    # 150 s deja margen bajo el límite de 180 s del MG400 sin podar
    # retratos normales (50-70 s sin podar).
    max_draw_seconds: float = Field(150.0, ge=5.0, le=600.0)


class SketchRequest(BaseModel):
    image: str = Field(..., description="Foto capturada en base64 (data URL)")
    params: SketchParams = Field(default_factory=SketchParams)


class JobRequest(BaseModel):
    sketch_id: str | None = None
    image: str | None = Field(default=None, description="Alternativa a sketch_id")


def build_sketch(image, params: SketchParams) -> dict:
    """Foto -> recorte -> líneas -> trazos -> SVG + trayectoria en mm."""
    portrait = renderer.render(
        image,
        sigma=params.sigma,
        phi=params.phi,
        epsilon=params.epsilon,
        contrast=params.contrast,
        threshold=params.threshold,
        use_landmarks=params.use_landmarks,
        use_lineart=params.use_lineart,
        lineart_strong=params.lineart_strong,
        lineart_weak=params.lineart_weak,
    )

    mask = portrait["mask"]
    crop = portrait["crop"]
    crop_height, crop_width = crop.shape[:2]

    skeleton = vectorize_ops.skeletonize(mask)
    strokes_px = vectorize_ops.extract_strokes(
        skeleton, min_length_px=params.min_stroke_px
    )
    simplified = [vectorize_ops.simplify_stroke(s, params.simplify_px) for s in strokes_px]
    bridged = vectorize_ops.bridge_aligned_strokes(
        simplified,
        max_gap_px=params.bridge_gap_px,
        max_angle_deg=params.bridge_angle_deg,
    )
    smoothed = [vectorize_ops.smooth_stroke(s) for s in bridged]
    ordered = [stroke for stroke, _ in vectorize_ops.order_strokes(smoothed)]
    # Tope de tiempo: si el retrato sale muy largo se van los trazos mas
    # cortos (textura) antes de mandar al robot.
    ordered = vectorize_ops.prune_to_budget(
        ordered,
        crop_width,
        max_seconds=params.max_draw_seconds,
        target_width_mm=params.target_width_mm,
    )

    trajectory = vectorize_ops.build_trajectory(
        ordered,
        crop_width,
        crop_height,
        target_width_mm=params.target_width_mm,
        spacing_mm=params.spacing_mm,
    )

    # Vista previa: exactamente las líneas que dibuja el robot (finas, sobre
    # blanco). Antes se mostraba la máscara binaria y se veía gruesa y sucia.
    preview = vectorize_ops.render_black_strokes(ordered, crop_width, crop_height, thickness=2)
    svg = vectorize_ops.strokes_to_svg(ordered, crop_width, crop_height)

    return {
        "preview": encode_data_url(preview),
        "svg": svg,
        "strokes": [
            {"points": [[float(x), float(y)] for x, y in stroke]} for stroke in ordered
        ],
        "segments": trajectory.segments,
        "stats": {
            **trajectory.stats,
            "width": crop_width,
            "height": crop_height,
            "portrait_ms": portrait["total_ms"],
            "face_detected": portrait["face"] is not None,
        },
    }


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "models": renderer.health(),
        "models_dir": str(MODELS_DIR),
        "robot": robot.name,
    }


@app.post("/api/sketch")
async def create_sketch(payload: SketchRequest) -> dict:
    try:
        image = decode_data_url(payload.image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_raw_capture(image)
    image = fit_max_side(image)
    try:
        result = await run_in_threadpool(build_sketch, image, payload.params)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Error generando el boceto: {exc}") from exc

    sketch_id = f"sk_{uuid.uuid4().hex[:10]}"
    sketches.put(
        sketch_id,
        Sketch(
            id=sketch_id,
            preview=result["preview"],
            svg=result["svg"],
            strokes=result["strokes"],
            segments=result["segments"],
            stats=result["stats"],
        ),
    )
    return {"id": sketch_id, "image": result["preview"], **result}


@app.post("/api/jobs")
async def create_job(payload: JobRequest) -> dict:
    sketch = sketches.get(payload.sketch_id) if payload.sketch_id else None

    if sketch is None:
        if not payload.image:
            raise HTTPException(status_code=400, detail="Falta sketch_id o image")
        try:
            image = fit_max_side(decode_data_url(payload.image))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            result = await run_in_threadpool(build_sketch, image, SketchParams())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Error generando el boceto: {exc}") from exc
        sketch_id = f"sk_{uuid.uuid4().hex[:10]}"
        sketch = Sketch(
            id=sketch_id,
            preview=result["preview"],
            svg=result["svg"],
            strokes=result["strokes"],
            segments=result["segments"],
            stats=result["stats"],
        )
        sketches.put(sketch_id, sketch)

    trajectory = Trajectory(
        segments=[Segment(type=item["type"], points=item["points"]) for item in sketch.segments],
        width_mm=float(sketch.stats.get("target_width_mm", 140.0)),
    )
    job = Job(id=f"job_{uuid.uuid4().hex[:10]}", sketch_id=sketch.id, status="drawing")
    jobs.put(job.id, job)

    async def run() -> None:
        total = trajectory.total_length or 1.0
        try:
            await robot.connect()

            async def on_progress(value: float, _segment: Segment) -> None:
                job.progress = value
                job.eta_seconds = max(0.0, (1.0 - value) * total / 80.0)

            await robot.draw(trajectory, on_progress)
            job.status = "done"
            job.progress = 1.0
            job.eta_seconds = 0.0
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)

    asyncio.create_task(run())
    return {
        "job_id": job.id,
        "sketch_id": sketch.id,
        "status": job.status,
        "est_seconds": round(trajectory.draw_length / 80.0, 1),
        "stats": sketch.stats,
    }


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    return {
        "job_id": job.id,
        "sketch_id": job.sketch_id,
        "status": job.status,
        "progress": round(job.progress, 3),
        "eta_seconds": round(job.eta_seconds, 1),
        "error": job.error,
    }
