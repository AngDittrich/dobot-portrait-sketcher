"""Ritmo de envío: no se debe llenar la cola del controlador.

El MG400 rechaza con -30000 cuando su cola está llena, y varios rechazos
seguidos le tumban el servicio TCP (hay que reiniciar el equipo). La cura no
es reintentar más rápido sino no llegar nunca al tope: mandar un poco más
lento de lo que el brazo consume, dejando un colchón de órdenes.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import (  # noqa: E402
    MG400Client,
    Segment,
    Trajectory,
    effective_speed_mm_s,
    pace_gap_s,
)
from app.robot.mg400 import Reply  # noqa: E402


def test_el_hueco_usa_la_velocidad_efectiva_medida():
    """17.3 mm a 20 mm/s es ~1 s de verdad: el firmware no llega a 20."""
    assert pace_gap_s(17.3, 20) == pytest.approx(1.0, abs=0.02)
    assert pace_gap_s(0.0, 20) == 0.0


def test_el_paso_corto_no_alcanza_la_velocidad_pedida():
    """Con pasos chicos manda la aceleración: v = sqrt(acc × paso).

    Medido en el MG400: AccL=100 y paso 1.5 mm dan ~12 mm/s, no los 20 que
    pide SpeedL. El ritmo tiene que usar esa velocidad real.
    """
    assert effective_speed_mm_s(1.5, 20, acc_mm_s2=100) == pytest.approx(12.25, abs=0.05)
    # En un paso largo sí cabe la rampa y manda SpeedL.
    assert effective_speed_mm_s(40.0, 20, acc_mm_s2=100) == pytest.approx(20.0, abs=0.05)
    # Un paso de 1.5 mm tarda lo que dice la física: ~0.14 s.
    assert pace_gap_s(1.5, 20, acc_mm_s2=100) == pytest.approx(0.1417, abs=0.002)


class Reloj:
    """Reloj y sleep falsos: el test no espera de verdad."""

    def __init__(self) -> None:
        self.now = 100.0
        self.dormido: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.dormido.append(seconds)
        self.now += seconds


class Enlace:
    def __init__(self) -> None:
        self.moves: list[str] = []

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        self.moves.append("Sync()")

    def errors(self) -> str:
        return ""


def test_el_envio_espera_para_no_pasar_el_colchon():
    reloj = Reloj()
    enlace = Enlace()
    cliente = MG400Client(
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
        queue_retry_s=0.0,
        pace_lead_s=1.0,
        clock=reloj,
        sleep=reloj.sleep,
    )
    # Movimiento virtual con la física real: bajar el lápiz 7 mm a 17.3 mm/s
    # (0.40 s) + 19 pasos de 1.7 mm a 11.3 mm/s (0.15 s cada uno = 2.86 s) +
    # subir el lápiz 7 mm (0.40 s) = 3.67 s. Con colchón de 1 s, la espera
    # total es ~2.67 s.
    puntos = [[i * 1.7, 0.0] for i in range(20)]
    papel = Trajectory(
        segments=[Segment(type="draw", points=puntos)],
        width_mm=40.0,
        height_mm=40.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())

    assert sum(reloj.dormido) == pytest.approx(2.67, abs=0.06)
    assert not any("Sync()" in move for move in enlace.moves)
