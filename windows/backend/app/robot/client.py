"""Cliente del robot.

`MockRobotClient` reproduce la línea de tiempo del dibujo sin hardware.
`MG400Client` manda la misma trayectoria por el enlace TCP de `mg400.py`
(`MovL` con el lápiz abajo en los trazos y arriba en los viajes).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("robot")

# Una respuesta más lenta que esto suele ser la cola del controlador llena.
SLOW_REPLY_S = 1.0
# Cada cuántas órdenes se imprime el avance en nivel INFO.
LOG_EVERY = 50


@dataclass
class Segment:
    """Un tramo de la trayectoria: `draw` dibuja, `travel` mueve con el lápiz arriba."""

    type: str
    points: list[list[float]] = field(default_factory=list)

    @property
    def length(self) -> float:
        total = 0.0
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:]):
            total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return total


@dataclass
class Trajectory:
    """Trayectoria completa en milímetros."""

    segments: list[Segment] = field(default_factory=list)
    width_mm: float = 0.0
    height_mm: float = 0.0

    @property
    def total_length(self) -> float:
        return sum(segment.length for segment in self.segments)

    @property
    def draw_length(self) -> float:
        return sum(segment.length for segment in self.segments if segment.type == "draw")

    @property
    def travel_length(self) -> float:
        return sum(segment.length for segment in self.segments if segment.type == "travel")


ProgressCallback = Callable[[float, Segment], Awaitable[None]]


class RobotClient:
    """Interfaz común de los clientes de robot."""

    name = "base"

    async def connect(self) -> None:  # pragma: no cover - interfaz
        raise NotImplementedError

    async def draw(self, trajectory: Trajectory, on_progress: ProgressCallback) -> None:
        raise NotImplementedError  # pragma: no cover - interfaz


class MockRobotClient(RobotClient):
    """Simulador: mismo ritmo que el robot, sin hardware."""

    name = "mock"

    def __init__(self, speed_mm_s: float = 80.0, time_scale: float | None = None) -> None:
        self.speed_mm_s = speed_mm_s
        # `time_scale` permite acelerar la demo (0.2 = cinco veces más rápido).
        self.time_scale = (
            time_scale if time_scale is not None else float(os.environ.get("ROBOT_TIME_SCALE", "1.0"))
        )

    async def connect(self) -> None:
        return None

    async def draw(self, trajectory: Trajectory, on_progress: ProgressCallback) -> None:
        total = trajectory.total_length or 1.0
        done = 0.0
        for segment in trajectory.segments:
            length = segment.length
            if segment.type == "draw":
                duration = length / max(1.0, self.speed_mm_s)
            else:
                # Los viajes con el lápiz arriba son más rápidos.
                duration = length / max(1.0, self.speed_mm_s * 1.6)
            if duration > 0:
                await asyncio.sleep(duration * self.time_scale)
            done += length
            await on_progress(min(1.0, done / total), segment)


class _DryLink:
    """Enlace de mentira para el modo seco: acepta órdenes y no abre sockets."""

    def move(self, _command: str) -> object:
        from app.robot.mg400 import Reply

        return Reply(code=0, value="")

    def dashboard(self, _command: str) -> object:
        from app.robot.mg400 import Reply

        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        return None

    def pose(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, 0.0, 0.0)


class MG400Client(RobotClient):
    """Dibuja una trayectoria en el MG400 usando `MG400Link.move`."""

    name = "mg400"

    def __init__(
        self,
        link: object | None = None,
        *,
        host: str = "192.168.10.55",
        user: int = 0,
        tool: int = 0,
        z_draw: float,
        z_travel: float,
        r: float = 0.0,
        speed_factor: int = 20,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        x_sign: int = -1,
        y_sign: int = -1,
        dry_run: bool = False,
        cp_draw: int = 0,
        r_far: float | None = None,
        far_x: float | None = None,
        far_y: float | None = None,
        move_timeout_s: float = 60.0,
    ) -> None:
        self._link = link
        self.move_timeout_s = move_timeout_s
        self._sent = 0
        self._total = 0
        self.host = host
        self.user = user
        self.tool = tool
        self.z_draw = z_draw
        self.z_travel = z_travel
        self.r = r
        self.speed_factor = speed_factor
        self.speed_travel = min(100, max(1, speed_factor * 2))
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.x_sign = _axis_sign(x_sign, "ROBOT_X_SIGN")
        self.y_sign = _axis_sign(y_sign, "ROBOT_Y_SIGN")
        self.dry_run = dry_run
        self.cp_draw = cp_draw
        self.r_far = r_far
        self.far_x = far_x
        self.far_y = far_y
        self.commands: list[str] = []
        self._ready = False

    @classmethod
    def from_env(cls) -> MG400Client:
        """Arma el cliente con la IP del robot y las alturas medidas en la cabina."""
        from app.robot.mg400 import MG400Error

        dry_run = _setting("ROBOT_DRY_RUN").lower() in {"1", "true", "yes"}

        def required(name: str) -> float:
            raw = _setting(name)
            if not raw:
                if dry_run:
                    return 0.0
                raise MG400Error(f"falta {name}")
            return float(raw)

        def optional_int(name: str, default: int) -> int:
            raw = _setting(name)
            return default if not raw else int(raw)

        def optional_float(name: str, default: float) -> float:
            raw = _setting(name)
            return default if not raw else float(raw)

        def optional_float_or_none(name: str) -> float | None:
            raw = _setting(name)
            return None if not raw else float(raw)

        r_far = optional_float_or_none("ROBOT_R_FAR")
        far_x = optional_float_or_none("ROBOT_FAR_X")
        far_y = optional_float_or_none("ROBOT_FAR_Y")
        if len([item for item in (r_far, far_x, far_y) if item is not None]) not in (0, 3):
            raise MG400Error("ROBOT_R_FAR, ROBOT_FAR_X y ROBOT_FAR_Y van juntos")

        return cls(
            host=_setting("ROBOT_HOST", "192.168.10.55"),
            user=optional_int("ROBOT_USER", 0),
            tool=optional_int("ROBOT_TOOL", 0),
            z_draw=required("ROBOT_Z_DRAW"),
            z_travel=required("ROBOT_Z_TRAVEL"),
            r=optional_float("ROBOT_R", 0.0),
            speed_factor=optional_int("ROBOT_SPEED_FACTOR", 20),
            origin_x=optional_float("ROBOT_ORIGIN_X", 0.0),
            origin_y=optional_float("ROBOT_ORIGIN_Y", 0.0),
            x_sign=optional_int("ROBOT_X_SIGN", -1),
            y_sign=optional_int("ROBOT_Y_SIGN", -1),
            dry_run=dry_run,
            cp_draw=optional_int("ROBOT_CP_DRAW", 0),
            r_far=r_far,
            far_x=far_x,
            far_y=far_y,
            move_timeout_s=optional_float("ROBOT_MOVE_TIMEOUT_S", 60.0),
        )

    async def connect(self) -> None:
        if self._ready:
            return
        if self._link is None:
            if self.dry_run:
                logger.info("modo seco: no se abre socket")
                self._link = _DryLink()
            else:
                from app.robot.mg400 import MG400Link

                self._link = await asyncio.to_thread(
                    MG400Link, self.host, move_timeout_s=self.move_timeout_s
                )
        await asyncio.to_thread(self._link.prepare, self.speed_factor)  # type: ignore[attr-defined]
        await self._dashboard(f"User({int(self.user)})")
        await self._dashboard(f"Tool({int(self.tool)})")
        await self._dashboard(f"CP({_blend(self.cp_draw)})")
        self._ready = True

    async def draw(self, trajectory: Trajectory, on_progress: ProgressCallback) -> None:
        self._validate(trajectory)
        await self.connect()
        self._sent = 0
        self._total = sum(len(segment.points) for segment in trajectory.segments)
        logger.info(
            "dibujo: %d segmentos, ~%d puntos, %.0f mm con lapiz abajo",
            len(trajectory.segments),
            self._total,
            trajectory.draw_length,
        )
        total = trajectory.total_length or 1.0
        done = 0.0
        pen_down = False
        held: list[float] | None = None
        last = Segment(type="travel")

        for segment in trajectory.segments:
            points = segment.points
            if not points:
                continue
            last = segment
            if segment.type == "travel":
                pen_down, held = await self._travel(points, held, pen_down)
            else:
                pen_down, held = await self._draw_segment(points, held, pen_down)
            done += segment.length
            await on_progress(min(1.0, done / total), segment)

        if pen_down and held is not None:
            await self._goto(held[0], held[1], self.z_travel,  self.speed_factor, 0)
        await self._sync()
        await on_progress(1.0, last)

    async def _draw_segment(
        self,
        points: list[list[float]],
        held: list[float] | None,
        pen_down: bool,
    ) -> tuple[bool, list[float]]:
        start = points[0]
        if pen_down and held is not None and not _near(held, start):
            await self._goto(held[0], held[1], self.z_travel,  self.speed_factor, 0)
            pen_down = False
        if held is None or not _near(held, start):
            await self._goto(start[0], start[1], self.z_travel,  self.speed_travel, 0)
            held = start
        if not pen_down:
            await self._goto(start[0], start[1], self.z_draw,  self.speed_factor, 0)
            pen_down = True
        for point in points[1:]:
            await self._goto(point[0], point[1], self.z_draw,  self.speed_factor, self.cp_draw)
            held = point
        return pen_down, held if held is not None else start

    async def _travel(
        self,
        points: list[list[float]],
        held: list[float] | None,
        pen_down: bool,
    ) -> tuple[bool, list[float]]:
        if pen_down and held is not None:
            await self._goto(held[0], held[1], self.z_travel,  self.speed_factor, 0)
            pen_down = False
        for point in points:
            if held is not None and _near(held, point):
                continue
            await self._goto(point[0], point[1], self.z_travel,  self.speed_travel, 0)
            held = point
        return pen_down, held if held is not None else points[-1]

    async def _goto(
        self,
        x: float,
        y: float,
        z: float,
        speed: int,
        cp: int,
    ) -> None:
        robot_x = _nonzero(self.origin_x + self.x_sign * x)
        robot_y = _nonzero(self.origin_y + self.y_sign * y)
        rotation = _nonzero(self._rotation(robot_x, robot_y))
        command = (
            f"MovL({robot_x:.3f},{robot_y:.3f},{_nonzero(z):.3f},{rotation:.3f},"
            f"SpeedL={int(speed)},AccL={int(speed)},CP={_blend(cp)})"
        )
        await self._move(command)

    def _rotation(self, robot_x: float, robot_y: float) -> float:
        """Gira entre el R del origen y el de la esquina lejana, si se midió."""
        if self.r_far is None or self.far_x is None or self.far_y is None:
            return self.r
        along_x = self.far_x - self.origin_x
        along_y = self.far_y - self.origin_y
        span = along_x * along_x + along_y * along_y
        if span <= 1e-6:
            return self.r
        offset_x = robot_x - self.origin_x
        offset_y = robot_y - self.origin_y
        traveled = (offset_x * along_x + offset_y * along_y) / span
        traveled = min(1.0, max(0.0, traveled))
        return self.r + traveled * (self.r_far - self.r)

    def _drop(self) -> None:
        """Suelta el socket. Si se reutiliza después de un fallo, el siguiente dibujo no obtiene respuesta."""
        link = self._link
        self._link = None
        self._ready = False
        close = getattr(link, "close", None)
        if close is None:
            return
        try:
            close()
        except OSError:
            return

    async def _move(self, command: str) -> None:
        from app.robot.mg400 import MG400Error

        self.commands.append(command)
        self._sent += 1
        started = time.monotonic()
        try:
            reply = await asyncio.to_thread(self._link.move, command)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("orden %d: %s no se pudo enviar", self._sent, command)
            await self._diagnose()
            self._drop()
            raise
        elapsed = time.monotonic() - started
        code = getattr(reply, "code", "?")
        if getattr(reply, "ok", False):
            if elapsed >= SLOW_REPLY_S:
                logger.warning(
                    "orden %d/%d: el robot tardo %.1f s en aceptar %s (cola llena)",
                    self._sent,
                    self._total,
                    elapsed,
                    command,
                )
            elif self._sent % LOG_EVERY == 0:
                logger.info("orden %d/%d enviada: %s", self._sent, self._total, command)
            else:
                logger.debug("orden %d -> %s (%.3f s): %s", self._sent, code, elapsed, command)
            return
        logger.error(
            "orden %d/%d: %s devolvio %s tras %.1f s, respuesta cruda %r",
            self._sent,
            self._total,
            command,
            code,
            elapsed,
            getattr(self._link, "last_raw", b""),
        )
        await self._diagnose()
        alarm = await self._alarm()
        self._drop()
        detail = " sin respuesta del controlador" if code == -99999 else ""
        if alarm:
            detail += f" alarma {alarm}"
        raise MG400Error(f"{command} devolvio {code}{detail}")

    async def _diagnose(self) -> None:
        """Lee el estado del controlador por el dashboard antes de soltar el socket."""
        dashboard = getattr(self._link, "dashboard", None)
        if dashboard is None:
            return
        for command in ("RobotMode()", "GetErrorID()", "GetPose()"):
            try:
                reply = await asyncio.to_thread(dashboard, command)
            except Exception as exc:  # noqa: BLE001
                logger.error("diagnostico %s: sin respuesta (%s)", command, exc)
                continue
            logger.error(
                "diagnostico %s -> %s {%s} crudo %r",
                command,
                getattr(reply, "code", "?"),
                getattr(reply, "value", ""),
                getattr(self._link, "last_raw", b""),
            )

    async def _alarm(self) -> str:
        errors = getattr(self._link, "errors", None)
        if errors is None:
            return ""
        try:
            return str(await asyncio.to_thread(errors)).strip()
        except Exception:
            return ""

    async def _dashboard(self, command: str) -> None:
        from app.robot.mg400 import MG400Error

        self.commands.append(command)
        try:
            reply = await asyncio.to_thread(self._link.dashboard, command)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("%s no se pudo enviar", command)
            self._drop()
            raise
        logger.info("%s -> %s", command, getattr(reply, "code", "?"))
        if not getattr(reply, "ok", False):
            self._drop()
            raise MG400Error(f"{command} devolvio {getattr(reply, 'code', '?')}")

    async def _sync(self) -> None:
        self.commands.append("Sync()")
        logger.info("%d ordenes enviadas; Sync() espera a que el brazo termine", self._sent)
        started = time.monotonic()
        try:
            await asyncio.to_thread(self._link.sync)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Sync() fallo tras %.1f s", time.monotonic() - started)
            await self._diagnose()
            self._drop()
            raise
        logger.info("Sync() termino en %.1f s", time.monotonic() - started)

    @staticmethod
    def _validate(trajectory: Trajectory) -> None:
        from app.robot.mg400 import MG400Error

        if trajectory.width_mm <= 0 or trajectory.height_mm <= 0:
            raise MG400Error("la trayectoria no trae el tamano del papel")
        tolerance = 0.05
        for segment in trajectory.segments:
            for point in segment.points:
                x, y = point[0], point[1]
                outside = (
                    x < -tolerance
                    or y < -tolerance
                    or x > trajectory.width_mm + tolerance
                    or y > trajectory.height_mm + tolerance
                )
                if outside:
                    raise MG400Error(f"punto fuera del papel: {x:.2f}, {y:.2f}")


def _nonzero(value: float) -> float:
    """El MG400 marca error si una orden le pide llegar exactamente a 0."""
    if abs(value) >= 0.001:
        return value
    return 0.001 if value >= 0 else -0.001


def _blend(value: int) -> int:
    """CP del MG400 va de 1 a 100. 0 es parámetro fuera de rango y corta la cola."""
    return min(100, max(1, int(value)))


def _near(left: list[float], right: list[float], tolerance: float = 0.05) -> bool:
    return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5 <= tolerance


def _axis_sign(value: int, name: str) -> int:
    from app.robot.mg400 import MG400Error

    if value not in (-1, 1):
        raise MG400Error(f"{name} tiene que ser 1 o -1")
    return value


def _dotenv() -> dict[str, str]:
    """Lee `windows/backend/.env` con el mismo formato que el proveedor del boceto."""
    path = Path(__file__).resolve().parents[2] / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name: str, default: str = "") -> str:
    """La variable de entorno gana; si no está, se usa el .env."""
    raw = os.environ.get(name)
    if raw is not None and raw.strip():
        return raw.strip()
    return _dotenv().get(name, default).strip()


def configure_logging() -> None:
    """Saca el logger `robot` a la consola de uvicorn, que solo configura los suyos."""
    level = _setting("ROBOT_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s ROBOT %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)


def robot_from_env() -> RobotClient:
    """`ROBOT_BACKEND=mock` (default) o `mg400`."""
    configure_logging()
    backend = _setting("ROBOT_BACKEND", "mock").lower() or "mock"
    if backend == "mock":
        return MockRobotClient()
    if backend == "mg400":
        return MG400Client.from_env()
    from app.robot.mg400 import MG400Error

    raise MG400Error(f"ROBOT_BACKEND desconocido: {backend}")
