"""Trazos cercanos se dibujan sin levantar el lápiz.

Medido en el aire: cada cambio de lápiz obliga a vaciar la cola del MG400, así
que el retrato de 110 trazos tarda 365 s aunque la tubería de órdenes vaya bien
dentro de cada trazo. Uniendo los trazos que quedan a menos de 2 mm se dibuja
un camino largo, la tubería sirve de verdad y desaparece el sobrecosto.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+)")


class EnlaceVivo:
    """Enlace falso donde el brazo sí llega a lo que se le manda."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.pose_fija = (100.0, 100.0, -160.0, 0.0)

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        found = MOVL.search(command)
        if found:
            self.pose_fija = (
                float(found.group(1)),
                float(found.group(2)),
                float(found.group(3)),
                0.0,
            )
        return Reply(code=0, value="")

    def dashboard(self, _command: str) -> Reply:
        return Reply(code=0, value="5")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        self.moves.append("Sync()")

    def errors(self) -> str:
        return ""

    def pose(self) -> tuple[float, float, float, float]:
        return self.pose_fija


async def _nada(_valor: float, _segmento: Segment) -> None:
    return None


def _cliente(enlace: EnlaceVivo) -> MG400Client:
    return MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=100.0,
        origin_y=100.0,
        pipeline=1,
        wait_arrival=True,
        arrival_extra_s=0.02,
        arrival_poll_s=0.005,
        min_step_mm=0.0,
        join_gap_mm=2.0,
    )


def _subidas(enlace: EnlaceVivo) -> int:
    """Cuántas veces se fue el lápiz a la altura de traslado."""
    return sum(1 for move in enlace.moves if MOVL.search(move) and ",-160.000," in move)


def _dibujar(segunda: list[list[float]]) -> EnlaceVivo:
    enlace = EnlaceVivo()
    client = _cliente(enlace)
    papel = Trajectory(
        segments=[
            Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]]),
            Segment(type="draw", points=segunda),
        ],
        width_mm=140.0,
        height_mm=140.0,
    )
    asyncio.run(client.draw(papel, _nada))
    return enlace


def test_dos_trazos_cercanos_no_levantan_el_lapiz() -> None:
    unidos = _dibujar([[10.5, 0.0], [20.0, 0.0]])
    separados = _dibujar([[15.0, 0.0], [25.0, 0.0]])

    assert _subidas(unidos) < _subidas(separados), (
        f"unidos={_subidas(unidos)} separados={_subidas(separados)}"
    )


def test_un_trazo_lejano_si_levanta_el_lapiz() -> None:
    enlace = _dibujar([[15.0, 0.0], [25.0, 0.0]])

    # Baja al primer trazo, sube, viaja y vuelve a bajar: al menos dos subidas.
    assert _subidas(enlace) >= 2


def _dibujar_con_traslado(destino: float) -> EnlaceVivo:
    """La trayectoria real trae un segmento de traslado entre trazos."""
    enlace = EnlaceVivo()
    client = _cliente(enlace)
    papel = Trajectory(
        segments=[
            Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]]),
            Segment(type="travel", points=[[destino, 0.0]]),
            Segment(type="draw", points=[[destino, 0.0], [20.0, 0.0]]),
        ],
        width_mm=140.0,
        height_mm=140.0,
    )
    asyncio.run(client.draw(papel, _nada))
    return enlace


def test_el_traslado_corto_no_levanta_el_lapiz() -> None:
    corto = _dibujar_con_traslado(11.0)
    largo = _dibujar_con_traslado(16.0)

    assert _subidas(corto) < _subidas(largo), (
        f"corto={_subidas(corto)} largo={_subidas(largo)}"
    )
