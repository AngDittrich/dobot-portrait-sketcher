"""Cliente del robot.

`MockRobotClient` reproduce la línea de tiempo del dibujo sin hardware.
`MG400Client` manda la misma trayectoria por el enlace TCP de `mg400.py`
(`MovL` con el lápiz abajo en los trazos y arriba en los viajes).
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.robot import frame as frame_ops
from app.robot.frame import Frame

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
DEFAULT_MIN_STEP_MM = 8.0

# Si el final de un trazo queda a menos de esto del inicio del siguiente, el
# lápiz no se levanta: se une con un conector corto. Cada cambio de altura
# obliga a vaciar la cola del MG400 y cuesta ~3 s, así que encadenar es lo que
# baja el retrato de 365 s.
DEFAULT_JOIN_GAP_MM = 6.0
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
        join_gap_mm: float = DEFAULT_JOIN_GAP_MM,
        wait_arrival: bool = True,
        arrival_tolerance_mm: float = ARRIVAL_TOLERANCE_MM,
        arrival_poll_s: float = ARRIVAL_POLL_S,
        arrival_extra_s: float = ARRIVAL_EXTRA_S,
        reconnects: int = 30,
        pipeline: int = DEFAULT_PIPELINE,
        unstick_resets: int = 3,
        unstick_sleep_s: float = 6.0,
        connect_retries: int = 3,
        connect_retry_s: float = 0.6,
        frame: Frame | None = None,
        lift_mm: float = frame_ops.DEFAULT_LIFT_MM,
        margin_mm: float = frame_ops.DEFAULT_MARGIN_MM,
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
        self.join_gap_mm = max(0.0, float(join_gap_mm))
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
        self.connect_retries = max(1, int(connect_retries))
        self.connect_retry_s = float(connect_retry_s)
        self._resets_left = self.unstick_resets
        self._last_point: tuple[float, float, float] | None = None
        # Radio (mm al eje) del punto que no cupo. Más adentro no se vuelve a intentar.
        self._radio_minimo: float | None = None
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
        # El origen es el centro del papel: la altura del recorte cambia con
        # cada foto y la esquina obligaría a recalcularla en cada retrato.
        self._paper_w = 0.0
        self._paper_h = 0.0
        self.x_sign = _axis_sign(x_sign, "ROBOT_X_SIGN")
        self.y_sign = _axis_sign(y_sign, "ROBOT_Y_SIGN")
        self.dry_run = dry_run
        self.cp_draw = cp_draw
        self.r_far = r_far
        self.far_x = far_x
        self.far_y = far_y
        # Hoja enseñada con tres esquinas. Sin ella se usa el centro y los
        # signos del `.env` (primer arranque, antes de calibrar).
        self.frame: Frame | None = None
        self.lift_mm = float(lift_mm)
        self.margin_mm = float(margin_mm)
        # (escala, u0, v0) del dibujo en curso dentro de la hoja.
        self._fit = (1.0, 0.0, 0.0)
        if frame is not None:
            self.set_frame(frame, lift_mm, margin_mm)
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
            join_gap_mm=optional_float("ROBOT_JOIN_MM", DEFAULT_JOIN_GAP_MM),
            r_far=r_far,
            far_x=far_x,
            far_y=far_y,
            move_timeout_s=optional_float("ROBOT_MOVE_TIMEOUT_S", 60.0),
        )

    def set_frame(self, frame: Frame | None, lift_mm: float, margin_mm: float) -> None:
        """Cambia la hoja enseñada. Z de dibujo y de viaje pasan a salir del plano de la hoja."""
        self.frame = frame
        self.lift_mm = float(lift_mm)
        self.margin_mm = float(margin_mm)
        if frame is not None:
            # Con hoja, z_draw y z_travel solo distinguen lápiz abajo de lápiz
            # arriba; la altura real de cada punto sale de `_map`.
            self.z_draw = frame.tl.z
            self.z_travel = frame.tl.z + self.lift_mm
            self.r = frame.tl.r

    async def ensure(self) -> None:
        """Deja un socket abierto para leer el estado, sin reconfigurar el robot.

        El sondeo del panel pasa por aquí. `connect` limpia alarmas y fija la
        velocidad, y hacerlo en cada reconexión del sondeo es lo que tumba el
        enlace cada pocos segundos.
        """
        if self._link is not None:
            return
        async with self._io:
            if self._link is None:
                await self._open_socket()

    async def connect(self) -> None:
        if self._ready and self._link is not None:
            return
        async with self._io:
            if self._ready and self._link is not None:
                return
            for intento in range(1, self.connect_retries + 1):
                try:
                    await self._abrir()
                    return
                except Exception as exc:
                    # El controlador cierra los sockets que pasan un rato sin
                    # uso: entre la foto y el boceto hay diez o quince segundos
                    # y el primer comando llega a un socket muerto. Se abre
                    # otro en vez de dar el trabajo por perdido.
                    self._close_link()
                    if intento >= self.connect_retries:
                        raise
                    logger.warning(
                        "la conexion no contesto (%s); abro otra (%d/%d)",
                        exc,
                        intento,
                        self.connect_retries,
                    )
                    await self._sleep(self.connect_retry_s)

    async def _open_socket(self) -> None:
        if self._link is not None:
            return
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

    async def _abrir(self) -> None:
        await self._open_socket()
        await asyncio.to_thread(self._link.prepare, self.speed_factor)  # type: ignore[attr-defined]
        await self._dashboard(f"User({int(self.user)})")
        await self._dashboard(f"Tool({int(self.tool)})")
        await self._dashboard(f"CP({_blend(self.cp_draw)})")
        self._ready = True

    async def mark_area(self) -> None:
        """Recorre el borde de la hoja enseñada con el lápiz arriba.

        No dibuja nada: sirve para comprobar que las esquinas caen sobre el
        papel antes de que llegue el visitante.
        """
        from app.robot.mg400 import MG400Error

        if self.frame is None:
            raise MG400Error("primero enseña las tres esquinas de la hoja")
        width_mm, height_mm = self.frame.width, self.frame.height
        await self.connect()
        self._sent = 0
        self._pace_due = None
        self._pace_target = None
        self._last_point = None
        self._radio_minimo = None
        self._pending = []
        self._reconnects_left = self.reconnects
        self._fit = (1.0, 0.0, 0.0)
        corners = [
            (0.0, 0.0),
            (width_mm, 0.0),
            (width_mm, height_mm),
            (0.0, height_mm),
            (0.0, 0.0),
        ]
        logger.info("marco el area de la hoja: %.0f x %.0f mm", width_mm, height_mm)
        for x, y in corners:
            await self._goto(x, y, self.z_travel, self.speed_travel, 0)
        await self._drain()

    async def draw(self, trajectory: Trajectory, on_progress: ProgressCallback) -> None:
        self._validate(trajectory)
        await self.connect()
        self._sent = 0
        self._pace_due = None
        self._pace_target = None
        self._resets_left = self.unstick_resets
        self._last_point = None
        self._radio_minimo = None
        self._pending = []
        self._paper_w = trajectory.width_mm
        self._paper_h = trajectory.height_mm
        if self.frame is not None:
            self._fit = frame_ops.fit(
                self.frame, trajectory.width_mm, trajectory.height_mm, self.margin_mm
            )
            logger.info(
                "retrato %.0f x %.0f mm en hoja %.0f x %.0f (escala %.2f)",
                trajectory.width_mm * self._fit[0],
                trajectory.height_mm * self._fit[0],
                self.frame.width,
                self.frame.height,
                self._fit[0],
            )
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
        cerca = (
            pen_down
            and held is not None
            and self.join_gap_mm > 0
            and _distance(held, start) <= self.join_gap_mm
            and not _near(held, start)
        )
        if cerca:
            # El conector se dibuja: cuesta ~0.5 s y ahorra los ~3 s de subir,
            # trasladar y volver a bajar el lápiz.
            if await self._goto(start[0], start[1], self.z_draw,  self.speed_factor, self.cp_draw):
                held = start
        else:
            if pen_down and held is not None and not _near(held, start):
                if await self._goto(held[0], held[1], self.z_travel,  self.speed_factor, 0):
                    pen_down = False
            if held is None or not _near(held, start):
                if await self._goto(start[0], start[1], self.z_travel,  self.speed_travel, 0):
                    held = start
            if not pen_down:
                if await self._goto(start[0], start[1], self.z_draw,  self.speed_factor, 0):
                    pen_down = True
                    held = start
        for point in points[1:]:
            # Paso mínimo: 1706 comandos de 1.18 mm matan la conexión del
            # MG400. Con 6 mm quedan ~1/5 de las órdenes y el brazo alcanza
            # a acelerar (10 mm/s medidos contra 2.4 mm/s con pasos cortos).
            if held is not None and _distance(held, point) < self.min_step_mm and point is not points[-1]:
                continue
            if await self._goto(point[0], point[1], self.z_draw,  self.speed_factor, self.cp_draw):
                held = point
        if held is not None and _distance(held, points[-1]) > 1e-6:
            if await self._goto(points[-1][0], points[-1][1], self.z_draw,  self.speed_factor, self.cp_draw):
                held = points[-1]
        return pen_down, held if held is not None else start

    async def _travel(
        self,
        points: list[list[float]],
        held: list[float] | None,
        pen_down: bool,
    ) -> tuple[bool, list[float]]:
        if pen_down and held is not None:
            corto = (
                self.join_gap_mm > 0
                and bool(points)
                and _distance(held, points[-1]) <= self.join_gap_mm
            )
            if corto:
                # El trazo siguiente empieza pegado: se dibuja el conector en
                # vez de subir el lápiz y vaciar la cola (~3 s por cambio).
                for point in points:
                    if held is not None and _near(held, point):
                        continue
                    if await self._goto(point[0], point[1], self.z_draw,  self.speed_factor, self.cp_draw):
                        held = point
                return pen_down, held if held is not None else points[-1]
            if await self._goto(held[0], held[1], self.z_travel,  self.speed_factor, 0):
                pen_down = False
        for point in points:
            if held is not None and _near(held, point):
                continue
            if await self._goto(point[0], point[1], self.z_travel,  self.speed_travel, 0):
                held = point
        return pen_down, held if held is not None else points[-1]

    async def _goto(
        self,
        x: float,
        y: float,
        z: float,
        speed: int,
        cp: int,
    ) -> bool:
        """Manda el punto. False si quedó fuera del brazo y se saltó para seguir dibujando."""
        robot_x, robot_y, real_z, rotation = self._map(x, y, z)
        if self._mas_adentro(robot_x, robot_y):
            logger.warning(
                "salto %.1f,%.1f: queda mas cerca del brazo que un punto que no cupo",
                robot_x,
                robot_y,
            )
            return False
        command = self._movl(robot_x, robot_y, real_z, rotation, speed, cp)
        target = (robot_x, robot_y, real_z)
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
            estado = await self._wait_arrival(robot_x, robot_y, distance, speed)
            if estado == "short":
                # Se movió, pero no llegó: está entrando a la zona pegada al eje.
                # El siguiente punto, más adentro, no se manda.
                self._marcar_borde(robot_x, robot_y)
                limite = await self._en_limite()
                if limite:
                    logger.warning(
                        "el punto %.1f,%.1f queda en el limite del brazo (%s); lo salto y sigo",
                        robot_x,
                        robot_y,
                        limite,
                    )
                    await self._soltar_limite()
                else:
                    logger.warning(
                        "el punto %.1f,%.1f no cupo junto al brazo; no sigo mas adentro",
                        robot_x,
                        robot_y,
                    )
                return False
            if estado == "stuck":
                limite = await self._en_limite()
                if limite:
                    self._marcar_borde(robot_x, robot_y)
                    logger.warning(
                        "el punto %.1f,%.1f queda en el limite del brazo (%s); lo salto y sigo",
                        robot_x,
                        robot_y,
                        limite,
                    )
                    await self._soltar_limite()
                    return False
                if self._resets_left > 0:
                    await self._unstick()
                    await self._move(command)
                    await self._wait_arrival(robot_x, robot_y, distance, speed)
        self._last_point = target
        return True

    async def _drain(self) -> None:
        """Espera a que se ejecute todo lo que quedó en vuelo."""
        while self._pending:
            await self._wait_pending()

    async def _wait_pending(self) -> None:
        robot_x, robot_y, distance, speed = self._pending.pop(0)
        if await self._wait_arrival(robot_x, robot_y, distance, speed) == "short":
            self._marcar_borde(robot_x, robot_y)

    async def _wait_arrival(
        self,
        robot_x: float,
        robot_y: float,
        distance_mm: float,
        speed: int,
    ) -> str:
        """Espera a que el brazo llegue antes de mandar la siguiente orden.

        Medido: con flujo continuo de MovL el controlador cierra el socket a
        los 2-3 s. Una orden a la vez, confirmando la pose, aguantó 40/40.

        `ok` si llegó o ya pasó el punto. `stuck` si no se acercó nada: la
        cola aceptó la orden y no la ejecutó. `short` si se movió pero el
        plazo se acabó lejos del punto, junto al brazo.
        """
        if not self.wait_arrival:
            return "ok"
        link = self._link
        pose = getattr(link, "pose", None)
        if pose is None:
            return "ok"
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
                return "ok"
            distancia = (
                (float(actual[0]) - robot_x) ** 2 + (float(actual[1]) - robot_y) ** 2
            ) ** 0.5
            if inicial is None:
                inicial = distancia
            if distancia <= self.arrival_tolerance_mm:
                return "ok"
            if ya_paso(mejor, distancia, self.arrival_tolerance_mm):
                return "ok"
            mejor = min(mejor, distancia)
            await asyncio.sleep(self.arrival_poll_s)
        lejos = mejor if mejor < float("inf") else -1.0
        logger.warning(
            "el brazo no llego a %.1f,%.1f en %.1f s; sigue a %.1f mm",
            robot_x,
            robot_y,
            presupuesto,
            lejos,
        )
        # Se movió menos de medio milímetro: la orden nunca llegó a ejecutarse.
        if inicial is not None and inicial - mejor < 0.5:
            return "stuck"
        if mejor > self.arrival_tolerance_mm:
            return "short"
        return "ok"

    def _radio(self, x: float, y: float) -> float:
        return (x * x + y * y) ** 0.5

    def _mas_adentro(self, x: float, y: float) -> bool:
        if self._radio_minimo is None:
            return False
        return self._radio(x, y) < self._radio_minimo

    def _marcar_borde(self, x: float, y: float) -> None:
        radio = self._radio(x, y)
        if self._radio_minimo is None or radio < self._radio_minimo:
            self._radio_minimo = radio

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

    async def _en_limite(self) -> str:
        """Texto de alarma si el controlador está en error. Vacío si solo no se movió."""
        link = self._link
        mode_fn = getattr(link, "mode", None)
        if mode_fn is None:
            return ""
        try:
            mode = await asyncio.to_thread(mode_fn)
        except Exception:  # noqa: BLE001
            return ""
        if mode not in (9, 11):
            return ""
        detail = f"modo {mode}"
        errors_fn = getattr(link, "errors", None)
        if errors_fn is None:
            return detail
        try:
            raw = str(await asyncio.to_thread(errors_fn)).strip()
        except Exception:  # noqa: BLE001
            return detail
        return f"{detail} {raw}".strip()

    async def _soltar_limite(self) -> None:
        """Quita la alarma sin reiniciar el controlador ni repetir el punto ilegal."""
        dashboard = getattr(self._link, "dashboard", None)
        if dashboard is None:
            return
        for command in ("ClearError()", "EnableRobot()", "Continue()"):
            try:
                reply = await asyncio.to_thread(dashboard, command)
            except Exception:  # noqa: BLE001
                logger.exception("%s no respondio tras el limite", command)
                return
            code = int(getattr(reply, "code", -1))
            if code != 0:
                logger.warning("%s devolvio %s tras el limite", command, code)

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

    def _map(self, x: float, y: float, z: float) -> tuple[float, float, float, float]:
        """Punto del dibujo (mm) → X, Y, Z, R del robot.

        `z` llega como `z_draw` o `z_travel`: lápiz abajo o arriba. Con hoja
        enseñada, la altura real sale del plano de las esquinas en ese punto.
        """
        if self.frame is not None:
            scale, u0, v0 = self._fit
            robot_x, robot_y, plane_z, rotation = self.frame.to_robot(u0 + scale * x, v0 + scale * y)
            real_z = plane_z if z == self.z_draw else plane_z + self.lift_mm
            return _nonzero(robot_x), _nonzero(robot_y), _nonzero(real_z), _nonzero(rotation)
        robot_x = _nonzero(self.origin_x + self.x_sign * (x - self._paper_w / 2))
        robot_y = _nonzero(self.origin_y + self.y_sign * (y - self._paper_h / 2))
        return robot_x, robot_y, _nonzero(float(z)), _nonzero(self._rotation(robot_x, robot_y))

    def _movl(self, x: float, y: float, z: float, r: float, speed: int, cp: int) -> str:
        return (
            f"MovL({x:.3f},{y:.3f},{z:.3f},{r:.3f},"
            f"SpeedL={int(speed)},AccL={int(self.acc_mm_s2)},CP={_blend(cp)})"
        )

    async def visit(self, x: float, y: float, z: float, r: float, speed: int | None = None) -> None:
        """Lleva el brazo a un punto del robot sin arrastrar el lápiz: primero sube, luego viaja."""
        await self.connect()
        rate = self.speed_travel if speed is None else int(speed)
        await self.prepare_motion(rate)
        self._pending = []
        pose_fn = getattr(self._link, "pose", None)
        here: tuple[float, float, float, float] | None = None
        if pose_fn is not None:
            try:
                here = tuple(float(value) for value in await asyncio.to_thread(pose_fn))[:4]  # type: ignore[assignment]
            except Exception:  # noqa: BLE001 - sin pose se viaja directo
                here = None
        if here is not None and here[2] < z - 0.5:
            await self._move(self._movl(here[0], here[1], z, here[3], rate, 0))
            await self._wait_arrival(here[0], here[1], 0.0, rate)
        distance = 0.0 if here is None else math.hypot(x - here[0], y - here[1])
        await self._move(self._movl(_nonzero(x), _nonzero(y), _nonzero(z), _nonzero(r), rate, 0))
        await self._wait_arrival(x, y, distance, rate)

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
        await self.ensure()
        link = self._link
        method = link.move if move else link.dashboard  # type: ignore[attr-defined]
        try:
            reply = await asyncio.to_thread(method, command)
        except OSError as exc:
            # El controlador cerró el socket. Una línea basta: el siguiente
            # sondeo abre otro, y el traceback de 10053 no aporta.
            logger.warning("consola: %s se cortó (%s)", command, exc)
            async with self._io:
                if self._link is link:
                    self._close_link()
            raise
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
