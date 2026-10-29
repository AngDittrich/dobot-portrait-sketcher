"""API de la Cabina de Retratos (Dobot MG400).

Contrato que consume el frontend React (`windows/frontend`):

    POST /api/sketch        foto (data URL) -> boceto + SVG + trayectoria
    POST /api/jobs          boceto aprobado  -> trabajo de dibujo del robot
    GET  /api/jobs/{id}     progreso del trabajo
    GET  /api/health        estado del backend y de los modelos
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import time
import uuid
from pathlib import Path

import cv2

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Body, FastAPI, Header, HTTPException, Query, Response  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from app.imaging import decode_data_url, encode_data_url, fit_max_side  # noqa: E402
from app.pipeline import providers  # noqa: E402
from app.pipeline import vectorize as vectorize_ops  # noqa: E402
from app.pipeline.caption import CAPTION_BUDGET_S, append_caption  # noqa: E402
from app.pipeline.providers import DEFAULT_STYLE  # noqa: E402
from app.pipeline.portrait import PortraitRenderer  # noqa: E402
from app.admin_ops import (  # noqa: E402
    AdminOpError,
    describe_alarms,
    issue_token,
    mode_label,
    pin_ok,
    plan,
    rate_for,
    token_ok,
)
from app.robot import busy  # noqa: E402
from app.robot.booth import (  # noqa: E402
    BoothError,
    apply_booth,
    booth_from_client,
    client_from_booth,
    load_booth,
    parse_booth,
    write_booth,
)
from app.robot.client import MockRobotClient, Segment, Trajectory, configure_logging, robot_from_env  # noqa: E402
from app.store import Job, JobStore, Sketch, SketchStore  # noqa: E402
from app.robot import frame as frame_ops  # noqa: E402
from app.robot import sheet as sheet_ops  # noqa: E402
from app.robot.frame import Frame, FrameError  # noqa: E402
from app.robot.text import syscom_trajectory  # noqa: E402

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
configure_logging()
robot = robot_from_env()
try:
    _saved_booth = load_booth()
except BoothError:
    logging.getLogger("robot").exception("robot.json ignorado; sigo con .env")
    _saved_booth = None
if _saved_booth:
    try:
        robot = client_from_booth(_saved_booth)
    except Exception:  # noqa: BLE001 - una calibración rota no tumba la cabina
        logging.getLogger("robot").exception("robot.json ignorado; sigo con .env")
robot_log = logging.getLogger("robot")
sketches = SketchStore()
jobs = JobStore()
# Contadores desde el arranque (el JobStore es LRU y olvida; esto no).
activity_totals = {"done": 0, "error": 0}


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
    rotate: bool = Field(False, description="Gira el retrato 90 grados. Apagado: arriba es la esquina enseñada")
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
        rotate=params.rotate,
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


def _portrait_width_mm() -> float:
    """Ancho del retrato: el que llena la hoja enseñada sin pasarse de alto."""
    frame = getattr(robot, "frame", None)
    if frame is not None:
        return frame_ops.portrait_width_mm(frame, getattr(robot, "margin_mm", frame_ops.DEFAULT_MARGIN_MM))
    return sheet_ops.draw_width_mm(sheet_ops.DEFAULT)


@app.post("/api/sketch")
async def create_sketch(payload: SketchRequest) -> dict:
    try:
        image = decode_data_url(payload.image)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_raw_capture(image)
    image = fit_max_side(image)
    # La hoja enseñada manda en el tamaño: el retrato se genera al ancho que
    # luego ocupa en el papel y el robot casi no tiene que escalarlo.
    payload.params.target_width_mm = _portrait_width_mm()
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
    if robot.name == "mg400" and getattr(robot, "frame", None) is None and not getattr(robot, "dry_run", False):
        # Sin esquinas mandaría las alturas viejas del `.env` y el lápiz se
        # clavaría en la mesa si esta cambió de altura.
        raise HTTPException(
            status_code=409,
            detail="falta calibrar la hoja: enseña las tres esquinas en el panel admin",
        )
    sketch = sketches.get(payload.sketch_id) if payload.sketch_id else None

    if sketch is None:
        if not payload.image:
            raise HTTPException(status_code=400, detail="Falta sketch_id o image")
        try:
            image = fit_max_side(decode_data_url(payload.image))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            params = SketchParams()
            params.target_width_mm = _portrait_width_mm()
            result = await run_in_threadpool(build_sketch, image, params)
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
            busy.enter()
            await robot.connect()

            async def on_progress(value: float, _segment: Segment) -> None:
                job.progress = value
                job.eta_seconds = max(0.0, (1.0 - value) * total / 80.0)

            await robot.draw(trajectory, on_progress)
            job.status = "done"
            job.progress = 1.0
            job.eta_seconds = 0.0
            activity_totals["done"] += 1
            robot_log.info("%s: terminado en %.1f s", job.id, time.monotonic() - started)
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            activity_totals["error"] += 1
            robot_log.exception(
                "%s: fallo al %.1f%% tras %.1f s",
                job.id,
                job.progress * 100,
                time.monotonic() - started,
            )
        finally:
            job.finished_at = time.time()
            busy.leave()

    asyncio.create_task(run())
    return {
        "job_id": job.id,
        "sketch_id": sketch.id,
        "status": job.status,
        "est_seconds": round(trajectory.draw_length / 80.0, 1),
        "stats": sketch.stats,
    }


class PinRequest(BaseModel):
    pin: str


class AdminCommand(BaseModel):
    action: str
    axis: str | None = None
    mm: float | None = None
    value: int | None = None
    on: bool | None = None
    index: int | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
    r: float | None = None
    speed: int | None = None


def _admin_pin() -> str:
    raw = os.environ.get("ADMIN_PIN", "").strip()
    if raw:
        return raw
    from app.robot.client import _setting

    return _setting("ADMIN_PIN", "2026") or "2026"


def _require_admin(x_admin_token: str | None) -> None:
    if not token_ok(x_admin_token or ""):
        raise HTTPException(status_code=401, detail="hace falta el pin")


def _first_number(value: str) -> float | None:
    cleaned = value.replace("{", " ").replace("}", " ").replace("[", " ").replace("]", " ")
    for chunk in cleaned.replace(",", " ").split():
        try:
            return float(chunk)
        except ValueError:
            continue
    return None


@app.post("/api/admin/unlock")
def admin_unlock(body: PinRequest) -> dict:
    if not pin_ok(body.pin.strip(), _admin_pin()):
        raise HTTPException(status_code=401, detail="pin incorrecto")
    return {"token": issue_token()}


@app.get("/api/admin/status")
async def admin_status(x_admin_token: str | None = Header(default=None)) -> dict:
    _require_admin(x_admin_token)
    snapshot: dict = {
        "backend": robot.name,
        "busy": busy.active(),
        "connected": False,
        "frame": booth_from_client(robot),
        "calibration": _calibration_of(getattr(robot, "frame", None), getattr(robot, "margin_mm", None)),
        "sheets": sheet_ops.catalog(),
    }
    if robot.name != "mg400":
        snapshot["detail"] = "el backend está en simulador"
        return snapshot
    try:
        _, mode_value = await robot.ask("RobotMode()")  # type: ignore[attr-defined]
        _, pose_value = await robot.ask("GetPose()")  # type: ignore[attr-defined]
        _, angle_value = await robot.ask("GetAngle()")  # type: ignore[attr-defined]
        _, error_value = await robot.ask("GetErrorID()")  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        snapshot["detail"] = str(exc)
        return snapshot
    mode = _first_number(mode_value)
    pose = _numbers(pose_value)[:4]
    snapshot.update(
        {
            "connected": True,
            "mode": int(mode) if mode is not None else None,
            "mode_label": mode_label(int(mode)) if mode is not None else "",
            "pose": pose if len(pose) == 4 else [],
            "angles": _numbers(angle_value)[:4],
            "alarms": error_value,
            "alarm_text": describe_alarms(error_value),
        }
    )
    return snapshot


@app.post("/api/admin/settings")
def admin_settings(
    body: dict = Body(...),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Guarda la hoja, las alturas y la IP. El `.env` deja de mandar en el próximo arranque."""
    global robot
    _require_admin(x_admin_token)
    if busy.active():
        raise HTTPException(status_code=409, detail="el robot está dibujando")
    try:
        booth = parse_booth(body)
    except BoothError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if booth.backend == "mock":
        robot = MockRobotClient()
    elif getattr(robot, "name", "") == "mg400":
        apply_booth(robot, booth)  # type: ignore[arg-type]
    else:
        robot = client_from_booth(booth.as_dict())
    try:
        write_booth(booth)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="no se pudo guardar la cabina") from exc
    return booth.as_dict()


@app.post("/api/admin/command")
async def admin_command(
    body: AdminCommand,
    x_admin_token: str | None = Header(default=None),
) -> dict:
    _require_admin(x_admin_token)
    if robot.name != "mg400":
        raise HTTPException(status_code=409, detail="el backend está en simulador")
    try:
        payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
        command, is_move, prepare = plan(body.action, payload, busy=busy.active())
        rate = rate_for(body.action, payload) if prepare else None
    except AdminOpError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        if prepare:
            await robot.prepare_motion(rate)  # type: ignore[attr-defined]
        code, value = await robot.ask(command, move=is_move)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if code != 0:
        raise HTTPException(status_code=502, detail=f"{command} devolvio {code} {value}".strip())
    return {"command": command, "code": code, "value": value}


def _calibration_of(frame: Frame | None, margin_mm: float | None) -> dict | None:
    if frame is None:
        return None
    return frame_ops.summary(frame, frame_ops.DEFAULT_MARGIN_MM if margin_mm is None else float(margin_mm))


def _frame_from_body(body: dict) -> Frame | None:
    """Las esquinas del formulario (todavía sin guardar) o, si no vienen, las guardadas."""
    corners = body.get("corners")
    if corners is None:
        return getattr(robot, "frame", None)
    try:
        return Frame.from_dict(corners)
    except FrameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/admin/calibration")
def admin_calibration(
    body: dict = Body(...),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Medida, orientación, caja del retrato y avisos de unas esquinas, sin guardarlas."""
    _require_admin(x_admin_token)
    frame = _frame_from_body(body)
    if frame is None:
        raise HTTPException(status_code=409, detail="faltan esquinas: enseña las tres")
    margin = body.get("margin_mm", frame_ops.DEFAULT_MARGIN_MM)
    try:
        return frame_ops.summary(frame, float(margin))
    except (FrameError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/admin/goto")
async def admin_goto(
    body: dict = Body(...),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Lleva el brazo a una esquina o al centro. Viaja con el lápiz arriba y baja al plano."""
    _require_admin(x_admin_token)
    if robot.name != "mg400":
        raise HTTPException(status_code=409, detail="el backend está en simulador")
    if busy.active():
        raise HTTPException(status_code=409, detail="el robot está dibujando")
    try:
        lift = float(body.get("lift_mm", getattr(robot, "lift_mm", frame_ops.DEFAULT_LIFT_MM)))
        speed = body.get("speed")
        point = body.get("point")
        if isinstance(point, dict):
            # Una esquina suelta, antes de tener las tres.
            x, y, z = float(point["x"]), float(point["y"]), float(point["z"])
            r = float(point.get("r", 0.0))
            if (x * x + y * y) ** 0.5 > frame_ops.REACH_MAX_MM:
                raise HTTPException(status_code=409, detail="ese punto queda fuera del alcance del brazo")
        else:
            frame = _frame_from_body(body)
            if frame is None:
                raise HTTPException(status_code=409, detail="faltan esquinas: enseña las tres")
            errors, _ = frame_ops.reach_report(frame)
            if errors:
                raise HTTPException(status_code=409, detail=errors[0])
            x, y, z, _r = frame.named(str(body.get("corner") or ""))
            # La muñeca no gira al ir de una esquina a otra: R fijo, el de arriba a la izquierda.
            r = frame.tl.r
    except (FrameError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        await robot.visit(x, y, z, r, None if speed is None else int(speed), lift=lift)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"corner": body.get("corner"), "x": x, "y": y, "z": z, "r": r}


@app.post("/api/admin/area")
async def admin_area(
    body: dict = Body(default_factory=dict),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Recorre un rectángulo con el lápiz arriba.

    Sin `sheet`, es el borde de las esquinas enseñadas. Con `sheet` (a5, a4…),
    es el marco de esa hoja estándar, centrado en las mismas esquinas, para ver
    el tamaño real sobre la mesa.
    """
    _require_admin(x_admin_token)
    if robot.name != "mg400":
        raise HTTPException(status_code=409, detail="el backend está en simulador")
    if busy.active():
        raise HTTPException(status_code=409, detail="el robot está dibujando")
    frame = _frame_from_body(body)
    if frame is None:
        raise HTTPException(status_code=409, detail="primero enseña y guarda las tres esquinas")
    sheet_name = str(body.get("sheet") or "").strip().lower()
    if sheet_name:
        if not sheet_ops.known(sheet_name):
            raise HTTPException(status_code=409, detail="esa hoja no existe")
        width, height = sheet_ops.place_mm(sheet_name)
        label = sheet_ops.label(sheet_name)
        blocked = frame_ops.outline_block(frame, width, height)
        if blocked:
            raise HTTPException(status_code=409, detail=blocked)
    else:
        width, height = frame.width, frame.height
        label = "la hoja enseñada"
    saved_frame = getattr(robot, "frame", None)
    saved_lift = float(getattr(robot, "lift_mm", frame_ops.DEFAULT_LIFT_MM))
    saved_margin = float(getattr(robot, "margin_mm", frame_ops.DEFAULT_MARGIN_MM))
    try:
        lift = float(body.get("lift_mm", saved_lift))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="la altura del lápiz no es un número") from exc
    robot.set_frame(frame, lift, saved_margin)  # type: ignore[attr-defined]
    try:
        await robot.mark_area(width, height)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        robot.set_frame(saved_frame, saved_lift, saved_margin)  # type: ignore[attr-defined]
    return {
        "width_mm": round(width, 1),
        "height_mm": round(height, 1),
        "label": label,
        "sheet": sheet_name or None,
    }


@app.post("/api/admin/test-draw")
async def admin_test_draw(
    body: dict = Body(default_factory=dict),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    """Escribe SYSCOM en el centro de la hoja enseñada, para probar la calibración."""
    _require_admin(x_admin_token)
    if robot.name != "mg400":
        raise HTTPException(status_code=409, detail="el backend está en simulador")
    if busy.active():
        raise HTTPException(status_code=409, detail="el robot está dibujando")
    frame = _frame_from_body(body)
    if frame is None:
        raise HTTPException(status_code=409, detail="primero enseña y guarda las tres esquinas")
    try:
        margin = float(body.get("margin_mm", getattr(robot, "margin_mm", frame_ops.DEFAULT_MARGIN_MM)))
        lift = float(body.get("lift_mm", getattr(robot, "lift_mm", frame_ops.DEFAULT_LIFT_MM)))
        trajectory = syscom_trajectory(frame.width, frame.height, margin)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    saved_frame = getattr(robot, "frame", None)
    saved_lift = float(getattr(robot, "lift_mm", frame_ops.DEFAULT_LIFT_MM))
    saved_margin = float(getattr(robot, "margin_mm", frame_ops.DEFAULT_MARGIN_MM))
    job = Job(id=f"job_{uuid.uuid4().hex[:10]}", sketch_id="prueba-syscom", status="drawing")
    jobs.put(job.id, job)

    async def run() -> None:
        robot.set_frame(frame, lift, margin)  # type: ignore[attr-defined]
        try:
            busy.enter()

            async def on_progress(value: float, _segment: Segment) -> None:
                job.progress = value

            await robot.draw(trajectory, on_progress, sheet_mm=True)  # type: ignore[attr-defined]
            job.status = "done"
            job.progress = 1.0
            activity_totals["done"] += 1
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            activity_totals["error"] += 1
            robot_log.exception("prueba SYSCOM: %s", exc)
        finally:
            job.finished_at = time.time()
            robot.set_frame(saved_frame, saved_lift, saved_margin)  # type: ignore[attr-defined]
            busy.leave()

    asyncio.create_task(run())
    return {"job_id": job.id, "text": "SYSCOM"}


@app.get("/api/admin/activity")
def admin_activity(x_admin_token: str | None = Header(default=None)) -> dict:
    """Dibujos recientes, contadores del arranque y proveedor de IA, para la página admin."""
    _require_admin(x_admin_token)
    settings = providers.load_settings()
    return {
        "jobs": [
            {
                "job_id": job.id,
                "sketch_id": job.sketch_id,
                "status": job.status,
                "progress": round(job.progress, 3),
                "error": job.error,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
            }
            for job in jobs.latest(20)
        ],
        "totals": dict(activity_totals),
        "provider": {
            "configured": settings.provider,
            "model": settings.model,
            "fallback_model": settings.fallback_model,
            "available": providers.available_providers(settings),
        },
    }


@app.get("/api/admin/sketches/{sketch_id}/preview")
def admin_sketch_preview(
    sketch_id: str,
    token: str = Query(default=""),
    x_admin_token: str | None = Header(default=None),
) -> Response:
    """Miniatura del boceto para la lista de actividad.

    El `<img>` del panel no puede mandar `X-Admin-Token`, así que aquí el
    token también vale como query param.
    """
    _require_admin(x_admin_token or token)
    sketch = sketches.get(sketch_id)
    if sketch is None:
        raise HTTPException(status_code=404, detail="boceto no encontrado")
    _, _, data = sketch.preview.partition(",")
    if not data:
        raise HTTPException(status_code=404, detail="el boceto no tiene imagen")
    try:
        payload = base64.b64decode(data)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="la imagen del boceto está corrupta") from exc
    return Response(content=payload, media_type="image/png")


def _numbers(value: str) -> list[float]:
    numbers: list[float] = []
    cleaned = value.replace("{", " ").replace("}", " ").replace("[", " ").replace("]", " ")
    for chunk in cleaned.replace(",", " ").split():
        try:
            numbers.append(float(chunk))
        except ValueError:
            continue
    return numbers


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
