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
# El firmware no llega a la velocidad pedida: con SpeedL=20 se midieron
# 17.3 mm/s en tramos de 30 mm. Sirve para calcular cuánto tarda cada orden.
PACE_EFFICIENCY = 0.865
# Colchón de órdenes encoladas. Suficiente para que el brazo no se pare entre
# puntos, y muy por debajo de las ~44-48 que caben antes del -30000.
DEFAULT_PACE_LEAD_S = 1.0
# Aceleración de la pluma. El cliente mandaba AccL = SpeedL (=20 mm/s²), tan
# bajo que en pasos de 1.5 mm el brazo no pasaba de 4 mm/s. El techo del
# firmware es 100: por encima responde -40005 (fuera de rango).
DEFAULT_ACC_MM_S2 = 100.0
MAX_ACC_MM_S2 = 100.0
MIN_ACC_MM_S2 = 1.0
# Paso mínimo entre órdenes. Con 1.18 mm hacían falta 1706 MovL y el
# controlador cerraba el socket a los 2-3 s; con 6 mm quedan ~1/5 y el brazo
# acelera (10.2 mm/s medidos contra 2.4 mm/s con pasos cortos).
DEFAULT_MIN_STEP_MM = 6.0
# Confirmación de llegada: se lee la pose hasta que el brazo está a 0.5 mm.
ARRIVAL_TOLERANCE_MM = 0.5
ARRIVAL_POLL_S = 0.1
ARRIVAL_EXTRA_S = 6.0
# Órdenes de dibujo en vuelo. Cada MovL cuesta ~0.51 s: esperar la llegada de
# una antes de mandar la siguiente deja el brazo parado medio segundo por punto.
# Con 3 en vuelo se solapa el envío con el movimiento. Nunca más: con flujo
# continuo (decenas de órdenes por segundo) el controlador cierra el socket.
DEFAULT_PIPELINE = 3


def effective_speed_mm_s(
    distance_mm: float,
    speed_mm_s: float,
    acc_mm_s2: float = DEFAULT_ACC_MM_S2,
) -> float:
    """Velocidad media real de una orden corta.

    En un tramo corto el brazo no llega a la velocidad pedida: apenas acelera
    y frena, así que manda la aceleración. El modelo v = sqrt(acc × paso)
    cuadra con lo medido en el MG400 (AccL=100 y paso 1.5 mm ≈ 12 mm/s).
    """
    if speed_mm_s <= 0:
        return 0.0
    distance = max(0.0, float(distance_mm))
    acc = max(MIN_ACC_MM_S2, float(acc_mm_s2))
    return max(0.001, min(float(speed_mm_s), (acc * distance) ** 0.5))


def pace_gap_s(
    distance_mm: float,
    speed_mm_s: float,
    acc_mm_s2: float = DEFAULT_ACC_MM_S2,
) -> float:
    """Segundos que el brazo tarda en recorrer una orden."""
    if speed_mm_s <= 0:
        return 0.0
    speed = effective_speed_mm_s(distance_mm, speed_mm_s, acc_mm_s2) * PACE_EFFICIENCY
    return max(0.0, float(distance_mm)) / speed


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

    def __init__(self) -> None:
        self._target: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def move(self, command: str) -> object:
        from app.robot.mg400 import Reply

        parts = command[command.find("(") + 1 : command.find(")")].split(",")
        try:
            self._target = (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
        except (IndexError, ValueError):
            pass
        return Reply(code=0, value="")

    def dashboard(self, _command: str) -> object:
        from app.robot.mg400 import Reply

        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        return None

    def pose(self) -> tuple[float, float, float, float]:
        """En modo seco no hay brazo que esperar: la pose es el último destino."""
        return self._target


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
        cp_draw: int = 100,
        r_far: float | None = None,
        far_x: float | None = None,
        far_y: float | None = None,
        move_timeout_s: float = 60.0,
        queue_retry_s: float = 0.2,
        queue_retries: int = 200,
        acc_mm_s2: float = DEFAULT_ACC_MM_S2,
        pace_lead_s: float = DEFAULT_PACE_LEAD_S,
        min_step_mm: float = DEFAULT_MIN_STEP_MM,
        wait_arrival: bool = True,
        arrival_tolerance_mm: float = ARRIVAL_TOLERANCE_MM,
        arrival_poll_s: float = ARRIVAL_POLL_S,
        arrival_extra_s: float = ARRIVAL_EXTRA_S,
        reconnects: int = 30,
        pipeline: int = DEFAULT_PIPELINE,
        unstick_resets: int = 3,
        unstick_sleep_s: float = 6.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._link = link
        self._stage_link = link
        self.move_timeout_s = move_timeout_s
        self.queue_retry_s = queue_retry_s
        self.queue_retries = queue_retries
        self.acc_mm_s2 = min(MAX_ACC_MM_S2, max(MIN_ACC_MM_S2, float(acc_mm_s2)))
        self.pace_lead_s = pace_lead_s
        self.min_step_mm = max(0.0, float(min_step_mm))
        self.wait_arrival = wait_arrival
        self.pipeline = max(1, int(pipeline))
        self._pending: list[tuple[float, float, float, int]] = []
        self.arrival_tolerance_mm = arrival_tolerance_mm
        self.arrival_poll_s = arrival_poll_s
        self.arrival_extra_s = arrival_extra_s
        self.reconnects = int(reconnects)
        self._reconnects_left = self.reconnects
        self.unstick_resets = max(0, int(unstick_resets))
        self.unstick_sleep_s = float(unstick_sleep_s)
        self._resets_left = self.unstick_resets
        self._last_point: tuple[float, float, float] | None = None
        self._clock = clock
        self._sleep = sleep
        self._pace_due: float | None = None
        self._pace_target: tuple[float, float, float] | None = None
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
        # El MG400 acepta un solo cliente. Dos consultas a la vez no pueden abrir dos sockets.
        self._io = asyncio.Lock()

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
            cp_draw=optional_int("ROBOT_CP_DRAW", 100),
            acc_mm_s2=optional_float("ROBOT_ACC_MM_S2", DEFAULT_ACC_MM_S2),
            pipeline=optional_int("ROBOT_PIPELINE", DEFAULT_PIPELINE),
            min_step_mm=optional_float("ROBOT_STEP_MM", DEFAULT_MIN_STEP_MM),
            r_far=r_far,
            far_x=far_x,
            far_y=far_y,
            move_timeout_s=optional_float("ROBOT_MOVE_TIMEOUT_S", 60.0),
        )

    async def connect(self) -> None:
        if self._ready and self._link is not None:
            return
        async with self._io:
            if self._ready and self._link is not None:
                return
            try:
                if self._link is None:
                    if self._stage_link is not None:
                        self._link = self._stage_link
                    elif self.dry_run:
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
            except Exception:
                self._close_link()
                raise

    async def draw(self, trajectory: Trajectory, on_progress: ProgressCallback) -> None:
        self._validate(trajectory)
        await self.connect()
        self._sent = 0
        self._pace_due = None
        self._pace_target = None
        self._resets_left = self.unstick_resets
        self._last_point = None
        self._pending = []
        self._reconnects_left = self.reconnects
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
        await self._drain()
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
            # Paso mínimo: 1706 comandos de 1.18 mm matan la conexión del
            # MG400. Con 6 mm quedan ~1/5 de las órdenes y el brazo alcanza
            # a acelerar (10 mm/s medidos contra 2.4 mm/s con pasos cortos).
            if _distance(held, point) < self.min_step_mm and point is not points[-1]:
                continue
            await self._goto(point[0], point[1], self.z_draw,  self.speed_factor, self.cp_draw)
            held = point
        if held is not None and _distance(held, points[-1]) > 1e-6:
            await self._goto(points[-1][0], points[-1][1], self.z_draw,  self.speed_factor, self.cp_draw)
            held = points[-1]
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
            f"SpeedL={int(speed)},AccL={int(self.acc_mm_s2)},CP={_blend(cp)})"
        )
        target = (robot_x, robot_y, float(z))
        distance = 0.0
        if self._last_point is not None:
            distance = (
                (target[0] - self._last_point[0]) ** 2
                + (target[1] - self._last_point[1]) ** 2
                + (target[2] - self._last_point[2]) ** 2
            ) ** 0.5
        en_vuelo = self.pipeline > 1 and cp == self.cp_draw and z == self.z_draw
        if not en_vuelo:
            # Cambiar de altura o pasear con órdenes pendientes dejaría el
            # lápiz abajo mientras el brazo todavía va en camino.
            await self._drain()
        await self._pace(target, speed)
        await self._move(command)
        if en_vuelo:
            self._pending.append((robot_x, robot_y, distance, speed))
            while len(self._pending) >= self.pipeline:
                await self._wait_pending()
        else:
            trabado = await self._wait_arrival(robot_x, robot_y, distance, speed)
            if trabado and self._resets_left > 0:
                await self._unstick()
                await self._move(command)
                await self._wait_arrival(robot_x, robot_y, distance, speed)
        self._last_point = target

    async def _drain(self) -> None:
        """Espera a que se ejecute todo lo que quedó en vuelo."""
        while self._pending:
            await self._wait_pending()

    async def _wait_pending(self) -> None:
        robot_x, robot_y, distance, speed = self._pending.pop(0)
        await self._wait_arrival(robot_x, robot_y, distance, speed)

    async def _wait_arrival(
        self,
        robot_x: float,
        robot_y: float,
        distance_mm: float,
        speed: int,
    ) -> bool:
        """Espera a que el brazo llegue antes de mandar la siguiente orden.

        Medido: con flujo continuo de MovL el controlador cierra el socket a
        los 2-3 s. Una orden a la vez, confirmando la pose, aguantó 40/40.

        Devuelve True solo si el brazo no se acercó nada: la orden se aceptó
        pero la cola del controlador quedó trabada.
        """
        if not self.wait_arrival:
            return False
        link = self._link
        pose = getattr(link, "pose", None)
        if pose is None:
            return False
        presupuesto = distance_mm / effective_speed_mm_s(
            distance_mm, speed, self.acc_mm_s2
        ) + self.arrival_extra_s
        limite = time.monotonic() + presupuesto
        mejor = float("inf")
        inicial: float | None = None
        while time.monotonic() < limite:
            try:
                actual = await asyncio.to_thread(pose)
            except Exception:  # noqa: BLE001 - sin lectura seguimos dibujando
                return False
            distancia = (
                (float(actual[0]) - robot_x) ** 2 + (float(actual[1]) - robot_y) ** 2
            ) ** 0.5
            if inicial is None:
                inicial = distancia
            if distancia <= self.arrival_tolerance_mm:
                return False
            if ya_paso(mejor, distancia, self.arrival_tolerance_mm):
                return False
            mejor = min(mejor, distancia)
            await asyncio.sleep(self.arrival_poll_s)
        logger.warning(
            "el brazo no llego a %.1f,%.1f en %.1f s (sigo)", robot_x, robot_y, presupuesto
        )
        # Se movió menos de medio milímetro: la orden nunca llegó a ejecutarse.
        return inicial is not None and inicial - mejor < 0.5

    async def _unstick(self) -> None:
        """Destraba la cola del controlador sin ir al robot.

        Medido tras una alarma: el MG400 acepta MovL con código 0 y el brazo no
        se mueve. Stop() devuelve -10000, ClearError() responde 0 pero no basta
        y ResetRobot() sí. Después de eso hay que soltar el socket y volver a
        conectar, porque el controlador cierra la conexión vieja.
        """
        self._resets_left -= 1
        logger.warning(
            "el brazo no se movio: reinicio la cola del controlador (quedan %d)",
            self._resets_left,
        )
        dashboard = getattr(self._link, "dashboard", None)
        if dashboard is not None:
            try:
                await asyncio.to_thread(dashboard, "ResetRobot()")
            except Exception:  # noqa: BLE001 - si no contesta, se reconecta igual
                logger.exception("ResetRobot() no respondio")
        await asyncio.sleep(self.unstick_sleep_s)
        self._drop()
        await self.connect()

    async def _pace(self, target: tuple[float, float, float], speed: int) -> None:
        """Deja pasar el tiempo justo para no llenar la cola del controlador.

        La cola llena es lo que provoca el -30000, y varios -30000 seguidos
        tumban el servicio TCP del robot. Se mantiene un colchón: se envía
        adelantado, pero nunca más de `pace_lead_s` segundos de movimiento.
        """
        if self.pace_lead_s <= 0 or self.wait_arrival:
            return
        now = self._clock()
        previous = self._pace_target
        if previous is None:
            self._pace_due = now
        else:
            distancia = (
                (target[0] - previous[0]) ** 2
                + (target[1] - previous[1]) ** 2
                + (target[2] - previous[2]) ** 2
            ) ** 0.5
            self._pace_due = max(self._pace_due or now, now) + pace_gap_s(
                distancia, speed, self.acc_mm_s2
            )
            espera = self._pace_due - now - self.pace_lead_s
            if espera > 0:
                await self._sleep(espera)
        self._pace_target = target

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

    def _close_link(self) -> None:
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

    def _drop(self) -> None:
        """Suelta el socket. Si se reutiliza después de un fallo, el siguiente dibujo no obtiene respuesta."""
        self._close_link()

    async def ask(self, command: str, *, move: bool = False) -> tuple[int, str]:
        """Manda una orden ya armada y devuelve el código y el valor, sin cerrar el socket si el robot la rechaza."""
        await self.connect()
        link = self._link
        method = link.move if move else link.dashboard  # type: ignore[attr-defined]
        try:
            reply = await asyncio.to_thread(method, command)
        except Exception:
            logger.exception("consola: %s no se pudo enviar", command)
            async with self._io:
                if self._link is link:
                    self._close_link()
            raise
        code = int(getattr(reply, "code", -99999))
        logger.info("consola %s -> %s", command, code)
        return code, str(getattr(reply, "value", ""))

    async def prepare_motion(self, percent: int | None = None) -> None:
        """Reanuda la cola antes de un jog o un paso. Sin esto el brazo acepta la orden y no se mueve.

        El porcentaje, si llega, es el del joystick. Si no, se queda el del dibujo.
        No se guarda en el cliente: el siguiente retrato vuelve a su propia velocidad.
        """
        await self.connect()
        rate = self.speed_factor if percent is None else int(percent)
        await asyncio.to_thread(self._link.prepare, rate)  # type: ignore[attr-defined]

    async def _move(self, command: str) -> None:
        from app.robot.mg400 import MG400Error, QUEUE_FULL_CODE

        self.commands.append(command)
        self._sent += 1
        started = time.monotonic()
        retries = 0
        while True:
            try:
                reply = await asyncio.to_thread(self._link.move, command)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("orden %d: %s no se pudo enviar", self._sent, command)
                await self._diagnose()
                self._drop()
                raise
            # Cola llena: el brazo está dibujando y no admite más órdenes por
            # ahora. Se reenvía; cortar aquí dejaba el dibujo a medias con el
            # robot todavía moviéndose.
            if getattr(reply, "code", None) != QUEUE_FULL_CODE:
                break
            retries += 1
            if retries > self.queue_retries:
                logger.error("orden %d: la cola no se liberó en %d reintentos", self._sent, retries)
                await self._diagnose()
                self._drop()
                raise MG400Error(f"{command} rechazada: cola llena tras {retries} reintentos")
            if retries == 1 or retries % 50 == 0:
                logger.warning(
                    "orden %d/%d: cola llena, esperando (reintento %d)",
                    self._sent,
                    self._total,
                    retries,
                )
            # Espera creciente: reenviar cada 50 ms mantenía la cola clavada en
            # el límite y el controlador terminaba cerrando el puerto TCP.
            await asyncio.sleep(min(self.queue_retry_s * retries, 1.0))
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
        # Conexión caída (respuesta vacía). Medido: el controlador queda sano,
        # así que se reconecta y se reenvía la misma orden en vez de abortar el
        # dibujo a medias (pasó al 56.8 % tras 515 órdenes).
        while code == -99999 and self._reconnects_left > 0:
            self._reconnects_left -= 1
            logger.warning(
                "orden %d/%d: conexion cortada, reconectando (quedan %d)",
                self._sent,
                self._total,
                self._reconnects_left,
            )
            self._drop()
            try:
                await self.connect()
                reply = await asyncio.to_thread(self._link.move, command)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - se reintenta el reenvío
                logger.exception("orden %d: no se pudo reconectar", self._sent)
                continue
            code = getattr(reply, "code", "?")
            if getattr(reply, "ok", False):
                return
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


def _distance(left: list[float] | None, right: list[float]) -> float:
    """Distancia en el plano entre dos puntos del dibujo (mm)."""
    if left is None:
        return float("inf")
    return ((left[0] - right[0]) ** 2 + (left[1] - right[1]) ** 2) ** 0.5


def ya_paso(mejor_mm: float, actual_mm: float, tolerancia_mm: float) -> bool:
    """¿El brazo ya dejó atrás el punto?

    Con varias órdenes en vuelo, el punto que se espera puede haber quedado
    atrás antes de la primera lectura. Si la distancia vuelve a crecer después
    de haberse acercado, seguir esperando la llegada exacta es tiempo perdido.
    """
    if mejor_mm == float("inf"):
        return False
    return actual_mm > mejor_mm + 2.0 * tolerancia_mm


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
