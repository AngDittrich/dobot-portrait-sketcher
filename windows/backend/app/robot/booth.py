"""Calibración de la cabina que se edita en el panel admin.

El `.env` solo llena el primer arranque. Al guardar, estos valores quedan en
`data/robot.json` (fuera de la carpeta que recarga uvicorn) y a partir de ahí
mandan ellos: la hoja enseñada con tres esquinas, cuánto sube el lápiz, la IP.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.robot import frame as frame_ops
from app.robot.client import MG400Client, MockRobotClient, RobotClient
from app.robot.frame import Frame, FrameError

PATH = Path(__file__).resolve().parents[4] / "data" / "robot.json"

logger = logging.getLogger("robot")


class BoothError(ValueError):
    """La calibración no se puede guardar."""


@dataclass
class Booth:
    backend: str
    host: str
    dry_run: bool
    user: int
    tool: int
    speed_factor: int
    cp_draw: int
    corners: dict | None = None
    lift_mm: float = frame_ops.DEFAULT_LIFT_MM
    margin_mm: float = frame_ops.DEFAULT_MARGIN_MM

    @property
    def frame(self) -> Frame | None:
        return None if self.corners is None else Frame.from_dict(self.corners)

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "host": self.host,
            "dry_run": self.dry_run,
            "user": self.user,
            "tool": self.tool,
            "speed_factor": self.speed_factor,
            "cp_draw": self.cp_draw,
            "corners": self.corners,
            "lift_mm": self.lift_mm,
            "margin_mm": self.margin_mm,
        }


def load_booth() -> dict | None:
    """El archivo guardado, o None si la cabina todavía sale del `.env`."""
    if not PATH.exists():
        return None
    try:
        raw = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoothError(f"robot.json no se pudo leer: {exc}") from exc
    if not isinstance(raw, dict):
        raise BoothError("robot.json no tiene una calibración")
    if raw.get("corners") is None and "origin_x" in raw:
        logger.warning(
            "robot.json es de la calibración vieja (centro y signos): enseña las tres esquinas en el panel"
        )
    return raw


def write_booth(booth: Booth) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(booth.as_dict(), indent=2) + "\n", encoding="utf-8")


def parse_corners(raw: object) -> dict | None:
    """Esquinas enseñadas, ya revisadas. None si todavía no se enseñaron."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BoothError("las esquinas no tienen el formato esperado")
    try:
        frame = Frame.from_dict(raw)
    except FrameError as exc:
        raise BoothError(str(exc)) from exc
    errors, _ = frame_ops.reach_report(frame)
    if errors:
        raise BoothError(errors[0])
    return frame.as_dict()


def parse_booth(payload: dict) -> Booth:
    backend = str(payload.get("backend") or "").strip().lower()
    if backend not in {"mg400", "mock"}:
        raise BoothError("el modo tiene que ser robot o simulador")
    host = str(payload.get("host") or "").strip()
    if not host or len(host) > 64 or any(char.isspace() for char in host):
        raise BoothError("la IP del robot no es válida")
    lift = _float(payload.get("lift_mm", frame_ops.DEFAULT_LIFT_MM), "levantar lápiz")
    if lift < 2 or lift > 40:
        raise BoothError("levantar lápiz va de 2 a 40 mm")
    margin = _float(payload.get("margin_mm", frame_ops.DEFAULT_MARGIN_MM), "margen")
    if margin < 0 or margin > 40:
        raise BoothError("el margen va de 0 a 40 mm")
    return Booth(
        backend=backend,
        host=host,
        dry_run=_bool(payload.get("dry_run")),
        user=_int(payload.get("user", 0), 0, 9, "usuario"),
        tool=_int(payload.get("tool", 0), 0, 9, "herramienta"),
        speed_factor=_int(payload.get("speed_factor", 20), 1, 100, "velocidad del dibujo"),
        cp_draw=_int(payload.get("cp_draw", 0), 0, 100, "CP"),
        corners=parse_corners(payload.get("corners")),
        lift_mm=lift,
        margin_mm=margin,
    )


def client_from_booth(payload: dict) -> RobotClient:
    booth = parse_booth(payload)
    if booth.backend == "mock":
        return MockRobotClient()
    if booth.frame is None:
        # Sin esquinas todavía: centro y signos del `.env`, con la conexión del panel.
        client = MG400Client.from_env()
        _copy_connection(client, booth)
        return client
    frame = booth.frame
    return MG400Client(
        host=booth.host,
        user=booth.user,
        tool=booth.tool,
        z_draw=frame.tl.z,
        z_travel=frame.tl.z + booth.lift_mm,
        r=frame.tl.r,
        speed_factor=booth.speed_factor,
        dry_run=booth.dry_run,
        cp_draw=booth.cp_draw,
        frame=frame,
        lift_mm=booth.lift_mm,
        margin_mm=booth.margin_mm,
    )


def booth_from_client(robot: RobotClient) -> dict:
    """Lo que el panel muestra. En el simulador se muestra lo guardado."""
    if robot.name != "mg400":
        saved = {}
        try:
            saved = load_booth() or {}
        except BoothError:
            saved = {}
        saved.setdefault("backend", "mock")
        return saved
    frame = getattr(robot, "frame", None)
    return {
        "backend": "mg400",
        "host": robot.host,  # type: ignore[attr-defined]
        "dry_run": bool(robot.dry_run),  # type: ignore[attr-defined]
        "user": int(robot.user),  # type: ignore[attr-defined]
        "tool": int(robot.tool),  # type: ignore[attr-defined]
        "speed_factor": int(robot.speed_factor),  # type: ignore[attr-defined]
        "cp_draw": int(robot.cp_draw),  # type: ignore[attr-defined]
        "corners": frame.as_dict() if frame is not None else None,
        "lift_mm": float(getattr(robot, "lift_mm", frame_ops.DEFAULT_LIFT_MM)),
        "margin_mm": float(getattr(robot, "margin_mm", frame_ops.DEFAULT_MARGIN_MM)),
    }


def apply_booth(robot: MG400Client, booth: Booth) -> None:
    """Copia la calibración al cliente vivo y suelta el socket para que el próximo enlace la use."""
    _copy_connection(robot, booth)
    robot.set_frame(booth.frame, booth.lift_mm, booth.margin_mm)
    robot._drop()


def _copy_connection(robot: MG400Client, booth: Booth) -> None:
    robot.host = booth.host
    robot.user = booth.user
    robot.tool = booth.tool
    robot.speed_factor = booth.speed_factor
    robot.speed_travel = min(100, max(1, booth.speed_factor * 2))
    robot.dry_run = booth.dry_run
    robot.cp_draw = booth.cp_draw


def _float(value: object, label: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise BoothError(f"{label} tiene que ser un número") from exc
    if abs(number) > 2000:
        raise BoothError(f"{label} se sale del rango")
    return number


def _int(value: object, low: int, high: int, label: str) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise BoothError(f"{label} tiene que ser un entero") from exc
    if isinstance(value, float) and number != value:
        raise BoothError(f"{label} tiene que ser un entero")
    if number < low or number > high:
        raise BoothError(f"{label} va de {low} a {high}")
    return number


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "si", "sí"}
