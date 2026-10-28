"""Calibración de la cabina que se edita en el panel admin.

El `.env` solo llena el primer arranque. Al guardar, estos valores quedan en
`data/robot.json` (fuera de la carpeta que recarga uvicorn) y a partir de ahí
mandan ellos: origen, esquina, alturas, IP.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from app.robot.client import MG400Client, MockRobotClient, RobotClient

PATH = Path(__file__).resolve().parents[4] / "data" / "robot.json"


class BoothError(ValueError):
    """La calibración no se puede guardar."""


@dataclass
class Booth:
    backend: str
    host: str
    dry_run: bool
    user: int
    tool: int
    z_draw: float
    z_travel: float
    r: float
    r_far: float
    far_x: float
    far_y: float
    speed_factor: int
    origin_x: float
    origin_y: float
    x_sign: int
    y_sign: int
    cp_draw: int

    def as_dict(self) -> dict:
        return asdict(self)


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
    return raw


def write_booth(booth: Booth) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(booth.as_dict(), indent=2) + "\n", encoding="utf-8")


def parse_booth(payload: dict) -> Booth:
    backend = str(payload.get("backend") or "").strip().lower()
    if backend not in {"mg400", "mock"}:
        raise BoothError("el modo tiene que ser robot o simulador")
    host = str(payload.get("host") or "").strip()
    if not host or len(host) > 64 or any(char.isspace() for char in host):
        raise BoothError("la IP del robot no es válida")
    z_draw = _float(payload.get("z_draw"), "Z de dibujo")
    z_travel = _float(payload.get("z_travel"), "Z de viaje")
    if z_travel <= z_draw:
        raise BoothError("Z de viaje tiene que quedar por encima de Z de dibujo")
    return Booth(
        backend=backend,
        host=host,
        dry_run=_bool(payload.get("dry_run")),
        user=_int(payload.get("user"), 0, 9, "usuario"),
        tool=_int(payload.get("tool"), 0, 9, "herramienta"),
        z_draw=z_draw,
        z_travel=z_travel,
        r=_float(payload.get("r"), "R del origen"),
        r_far=_float(payload.get("r_far"), "R de la esquina"),
        far_x=_float(payload.get("far_x"), "X de la esquina"),
        far_y=_float(payload.get("far_y"), "Y de la esquina"),
        speed_factor=_int(payload.get("speed_factor"), 1, 100, "velocidad del dibujo"),
        origin_x=_float(payload.get("origin_x"), "X del origen"),
        origin_y=_float(payload.get("origin_y"), "Y del origen"),
        x_sign=_sign(payload.get("x_sign"), "signo X"),
        y_sign=_sign(payload.get("y_sign"), "signo Y"),
        cp_draw=_int(payload.get("cp_draw"), 0, 100, "CP"),
    )


def client_from_booth(payload: dict) -> RobotClient:
    booth = parse_booth(payload)
    if booth.backend == "mock":
        return MockRobotClient()
    return MG400Client(
        host=booth.host,
        user=booth.user,
        tool=booth.tool,
        z_draw=booth.z_draw,
        z_travel=booth.z_travel,
        r=booth.r,
        speed_factor=booth.speed_factor,
        origin_x=booth.origin_x,
        origin_y=booth.origin_y,
        x_sign=booth.x_sign,
        y_sign=booth.y_sign,
        dry_run=booth.dry_run,
        cp_draw=booth.cp_draw,
        r_far=booth.r_far,
        far_x=booth.far_x,
        far_y=booth.far_y,
    )


def booth_from_client(robot: RobotClient) -> dict:
    """Lo que el panel muestra. En el simulador no hay hoja medida."""
    if robot.name != "mg400":
        saved = {}
        try:
            saved = load_booth() or {}
        except BoothError:
            saved = {}
        saved.setdefault("backend", "mock")
        return saved or {"backend": "mock"}
    return {
        "backend": "mg400",
        "host": robot.host,  # type: ignore[attr-defined]
        "dry_run": bool(robot.dry_run),  # type: ignore[attr-defined]
        "user": int(robot.user),  # type: ignore[attr-defined]
        "tool": int(robot.tool),  # type: ignore[attr-defined]
        "z_draw": robot.z_draw,  # type: ignore[attr-defined]
        "z_travel": robot.z_travel,  # type: ignore[attr-defined]
        "r": robot.r,  # type: ignore[attr-defined]
        "r_far": robot.r_far,  # type: ignore[attr-defined]
        "far_x": robot.far_x,  # type: ignore[attr-defined]
        "far_y": robot.far_y,  # type: ignore[attr-defined]
        "speed_factor": int(robot.speed_factor),  # type: ignore[attr-defined]
        "origin_x": robot.origin_x,  # type: ignore[attr-defined]
        "origin_y": robot.origin_y,  # type: ignore[attr-defined]
        "x_sign": int(robot.x_sign),  # type: ignore[attr-defined]
        "y_sign": int(robot.y_sign),  # type: ignore[attr-defined]
        "cp_draw": int(robot.cp_draw),  # type: ignore[attr-defined]
    }


def apply_booth(robot: MG400Client, booth: Booth) -> None:
    """Copia la calibración al cliente vivo y suelta el socket para que el próximo enlace la use."""
    robot.host = booth.host
    robot.user = booth.user
    robot.tool = booth.tool
    robot.z_draw = booth.z_draw
    robot.z_travel = booth.z_travel
    robot.r = booth.r
    robot.r_far = booth.r_far
    robot.far_x = booth.far_x
    robot.far_y = booth.far_y
    robot.speed_factor = booth.speed_factor
    robot.speed_travel = min(100, max(1, booth.speed_factor * 2))
    robot.origin_x = booth.origin_x
    robot.origin_y = booth.origin_y
    robot.x_sign = booth.x_sign
    robot.y_sign = booth.y_sign
    robot.dry_run = booth.dry_run
    robot.cp_draw = booth.cp_draw
    robot._drop()


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


def _sign(value: object, label: str) -> int:
    number = _int(value, -1, 1, label)
    if number == 0:
        raise BoothError(f"{label} es 1 o -1")
    return number


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "si", "sí"}
