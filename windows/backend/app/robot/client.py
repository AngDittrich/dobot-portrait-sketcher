"""Cliente del robot.

Hoy solo existe el simulador, que reproduce la misma línea de tiempo que
usa el robot real (misma velocidad, mismos viajes con el lápiz levantado).
Cuando llegue el MG400 se añade `MG400Client` con el SDK TCP/IP oficial
(Dobot-Arm/TCP-IP-4Axis-Python) sin tocar el resto de la API.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


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
