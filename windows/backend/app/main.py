"""API de la Cabina de Retratos (Dobot MG400).

Contrato que consume el frontend React (`windows/frontend`):

    POST /api/sketch        foto (data URL) -> boceto + SVG + trayectoria
    POST /api/jobs          boceto aprobado  -> trabajo de dibujo del robot
    GET  /api/jobs/{id}     progreso del trabajo
    GET  /api/health        estado del backend y de los modelos
"""

from __future__ import annotations

import asyncio
import logging
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
from app.pipeline import providers  # noqa: E402
from app.pipeline import vectorize as vectorize_ops  # noqa: E402
from app.pipeline.caption import CAPTION_BUDGET_S, append_caption  # noqa: E402
from app.pipeline.providers import DEFAULT_STYLE  # noqa: E402
from app.pipeline.portrait import PortraitRenderer  # noqa: E402
from app.robot.client import Segment, Trajectory, robot_from_env  # noqa: E402
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
        # La app de Android (android/capacitor) sirve la UI desde
        # https://localhost, así que su origen no es un puerto de Vite: sin
        # esta línea el APK se queda con la pantalla en «convirtiendo» porque
        # el navegador rechaza la primera llamada.
        "https://localhost",
        "capacitor://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

renderer = PortraitRenderer(MODELS_DIR)
robot = robot_from_env()
robot_log = logging.getLogger("robot")
sketches = SketchStore()
jobs = JobStore()


class SketchParams(BaseModel):
    """Ajustes del boceto (los mismos que se tocan en el laboratorio)."""

    sigma: float = Field(1.2, ge=0.2, le=4.0)
    phi: float = Field(40.0, ge=1.0, le=80.0)
    epsilon: float = Field(0.0, ge=0.0, le=0.5)
    contrast: float = Field(0.7, ge=0.0, le=1.0)
    threshold: float = Field(0.12, ge=0.02, le=0.9)
    bg_threshold: float = Field(0.28, ge=0.02, le=0.9)
    beard_thresh: float = Field(0.45, ge=0.02, le=0.9)
    use_landmarks: bool = True
    target_width_mm: float = Field(140.0, ge=20.0, le=400.0)
    spacing_mm: float = Field(1.5, ge=0.2, le=10.0)
    simplify_px: float = Field(2.5, ge=0.0, le=5.0)
    smooth_iters: int = Field(2, ge=0, le=4, description="Pasadas Chaikin antes de RDP (lineas mas rectas)")
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
    # Ruta nueva: el boceto lo dibuja un modelo de imagen (ver providers.py).
    # use_ai=False obliga al XDoG de siempre, que queda como respaldo sin red.
    use_ai: bool = True
    ai_min_stroke_px: float = Field(
        10.0, ge=1.0, le=40.0, description="Trazos mínimos que sobreviven al trazar la tinta"
    )
    # Unión de los huecos de la binarización antes de adelgazar. Sin esto la
    # línea se corta donde el modelo aclaró la pluma y el dibujo sale a guiones.
    ai_bridge_gap_px: float = Field(16.0, ge=0.0, le=40.0)
    ai_bridge_angle_deg: float = Field(60.0, ge=0.0, le=180.0)


class SketchRequest(BaseModel):
    image: str = Field(..., description="Foto capturada en base64 (data URL)")
    params: SketchParams = Field(default_factory=SketchParams)
    # Ids de rasgo (chef, sombrero…). El texto libre no se reenvía al modelo.
    traits: list[str] = Field(default_factory=list)
    # retrato, caricatura, anime o cartoon. Otro valor cae en caricatura.
    style: str = DEFAULT_STYLE


class JobRequest(BaseModel):
    sketch_id: str | None = None
    image: str | None = Field(default=None, description="Alternativa a sketch_id")


def build_sketch(
    image,
    params: SketchParams,
    traits: list[str] | None = None,
    style: str | None = None,
) -> dict:
    """Foto -> líneas -> trazos -> SVG + trayectoria en mm.

    Las líneas las pone el proveedor de IA (`providers.py`). Si no hay red, no
    hay key o el modelo falla, se cae al XDoG congelado y la cabina sigue
    funcionando: un boceto peor es mejor que una pantalla de error delante del
    visitante.
    """
    ai_meta: dict | None = None
    mask = None
    if params.use_ai:
        try:
            mask, ai_meta = providers.generate_mask(
                image, models_dir=MODELS_DIR, traits=traits, style=style
            )
        except providers.SketchProviderError as exc:
            ai_meta = {"provider": "xdog", "fallback_reason": str(exc)}

    portrait: dict = {}
    if mask is not None:
        mask = vectorize_ops.trim_to_ink(mask)
        crop_height, crop_width = mask.shape[:2]
        # Línea central: cada trazo que dibuja el modelo se recorre una sola vez.
        # Trazarlo por contorno recorría los dos bordes y en papel se veía doble,
        # sobre todo donde el modelo aprieta la pluma (pelo, cuello, audífonos).
        strokes_px = vectorize_ops.strokes_from_centerline(
            mask,
            min_length_px=params.ai_min_stroke_px,
            bridge_gap_px=params.ai_bridge_gap_px,
            bridge_angle_deg=params.ai_bridge_angle_deg,
        )
        portrait_ms = int(float((ai_meta or {}).get("seconds") or 0) * 1000)
        face_detected = True
    else:
        portrait = renderer.render(
            image,
            sigma=params.sigma,
            phi=params.phi,
            epsilon=params.epsilon,
            contrast=params.contrast,
            threshold=params.threshold,
            bg_threshold=params.bg_threshold,
            beard_thresh=params.beard_thresh,
            use_landmarks=params.use_landmarks,
            use_lineart=params.use_lineart,
            lineart_strong=params.lineart_strong,
            lineart_weak=params.lineart_weak,
        )
        mask = portrait["mask"]
        crop = portrait["crop"]
        crop_height, crop_width = crop.shape[:2]
        strokes_px = vectorize_ops.strokes_from_mask(mask, min_length_px=params.min_stroke_px)
        portrait_ms = portrait["total_ms"]
        face_detected = portrait["face"] is not None

    simplified = [vectorize_ops.simplify_and_smooth(s, params.simplify_px, params.smooth_iters) for s in strokes_px]
    ordered = [stroke for stroke, _ in vectorize_ops.order_strokes(simplified)]
    # Tope de tiempo: si el retrato sale muy largo se van los trazos mas
    # cortos (textura) antes de mandar al robot.
    ordered = vectorize_ops.prune_to_budget(
        ordered,
        crop_width,
        max_seconds=max(12.0, params.max_draw_seconds - CAPTION_BUDGET_S),
        target_width_mm=params.target_width_mm,
    )
    # El rótulo va después de podar: si entrara antes, el recorte de tiempo
    # se lo comería por ser de los trazos más cortos.
    ordered, crop_height = append_caption(ordered, crop_width, crop_height)

    trajectory = vectorize_ops.build_trajectory(
        ordered,
        crop_width,
        crop_height,
        target_width_mm=params.target_width_mm,
        spacing_mm=params.spacing_mm,
    )

    # Vista previa: los mismos contornos que va a trazar el robot.
    preview = vectorize_ops.render_black_strokes(ordered, crop_width, crop_height, thickness=2)
    svg = vectorize_ops.strokes_to_svg(ordered, crop_width, crop_height)

    stats = {
        **trajectory.stats,
        "width": crop_width,
        "height": crop_height,
        "portrait_ms": portrait_ms,
        "face_detected": face_detected,
        **portrait.get("lab", {}),
    }
    if ai_meta:
        stats["ai"] = ai_meta

    return {
        "preview": encode_data_url(preview),
        "svg": svg,
        "strokes": [
            {"points": [[float(x), float(y)] for x, y in stroke]} for stroke in ordered
        ],
        "segments": trajectory.segments,
        "stats": stats,
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
        result = await run_in_threadpool(
            build_sketch, image, payload.params, payload.traits, payload.style
        )
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
        height_mm=float(sketch.stats.get("height_mm", 0.0)),
    )
    job = Job(id=f"job_{uuid.uuid4().hex[:10]}", sketch_id=sketch.id, status="drawing")
    jobs.put(job.id, job)

    async def run() -> None:
        total = trajectory.total_length or 1.0
        started = time.monotonic()
        robot_log.info(
            "%s: inicia con %s (boceto %s, %d segmentos, %.0f x %.0f mm)",
            job.id,
            robot.name,
            sketch.id,
            len(trajectory.segments),
            trajectory.width_mm,
            trajectory.height_mm,
        )
        try:
            await robot.connect()

            async def on_progress(value: float, _segment: Segment) -> None:
                job.progress = value
                job.eta_seconds = max(0.0, (1.0 - value) * total / 80.0)

            await robot.draw(trajectory, on_progress)
            job.status = "done"
            job.progress = 1.0
            job.eta_seconds = 0.0
            robot_log.info("%s: terminado en %.1f s", job.id, time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            robot_log.exception(
                "%s: fallo al %.1f%% tras %.1f s",
                job.id,
                job.progress * 100,
                time.monotonic() - started,
            )

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
