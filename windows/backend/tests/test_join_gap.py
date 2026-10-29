"""El cliente no une trazos por su cuenta.

Unir a ciegas 8 mm convertía las letras y los rasgos cercanos en rayas que no
están en el boceto. Las uniones las decide el planificador, y solo cuando el
conector cae sobre tinta.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import DEFAULT_JOIN_GAP_MM, MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+)")


class EnlaceVivo:
    """Enlace falso donde el brazo sí llega a lo que se le manda."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.pose_fija = (100.0, 100.0, -167.0, 0.0)

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

    def dashboard(self, command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, rate: int) -> None:
        return None

    def sync(self) -> Reply:
        return Reply(code=0, value="")

    def errors(self) -> Reply:
        return Reply(code=0, value="[]")

    def pose(self) -> tuple[float, float, float, float]:
        return self.pose_fija


async def _nada(*_args) -> None:
    return None


def _cliente(enlace: EnlaceVivo) -> MG400Client:
    """Sin tocar join_gap_mm: se prueba el valor que trae por defecto."""
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
    )


def _levanta(enlace: EnlaceVivo) -> int:
    """Cuántas veces subió el lápiz a la altura de traslado."""
    return sum(1 for move in enlace.moves if MOVL.search(move) and ",-160.000," in move)


def _dibujar(segunda: list[list[float]]) -> EnlaceVivo:
    enlace = EnlaceVivo()
    papel = Trajectory(
        segments=[
            Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]]),
            Segment(type="draw", points=segunda),
        ],
        width_mm=140.0,
        height_mm=140.0,
    )
    asyncio.run(_cliente(enlace).draw(papel, _nada))
    return enlace


def test_el_cliente_no_encadena_trazos():
    assert DEFAULT_JOIN_GAP_MM == 0.0


def test_un_hueco_de_siete_milimetros_levanta_el_lapiz():
    enlace = _dibujar([[17.0, 0.0], [30.0, 0.0]])

    assert _levanta(enlace) >= 2
