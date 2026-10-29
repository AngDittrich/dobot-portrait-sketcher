"""Marcar el área de la hoja: el lápiz nunca baja al recorrer el borde."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402


class EnlaceFalso:
    def __init__(self) -> None:
        self.moves: list[str] = []

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, percent: int = 20) -> None:
        return None

    def pose(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, 0.0, 0.0)


def _cliente(enlace: EnlaceFalso) -> MG400Client:
    return MG400Client(
        link=enlace,
        pace_lead_s=0.0,
        wait_arrival=False,
        min_step_mm=0.0,
        host="192.168.10.55",
        z_draw=-97.0,
        z_travel=-90.0,
        r=120.57,
        speed_factor=20,
        origin_x=279.24,
        origin_y=-27.2,
        x_sign=-1,
        y_sign=-1,
    )


def test_el_borde_de_la_hoja_se_recorre_con_el_lapiz_arriba():
    enlace = EnlaceFalso()
    cliente = _cliente(enlace)

    asyncio.run(cliente.mark_area(148.0, 210.0))

    movl = [orden for orden in enlace.moves if orden.startswith("MovL(")]
    assert len(movl) == 5  # cuatro esquinas y vuelta al inicio
    assert all(",-90.000," in orden for orden in movl), "ninguna orden puede ir a Z de dibujo"
    assert not any("CP=100)" in orden for orden in movl)
    # La hoja se centra en el origen y el signo de X la refleja (brazo montado al revés):
    # A5 de 148 mm va de 205.24 a 353.24 con este centro.
    xs = [float(orden.split("(")[1].split(",")[0]) for orden in movl]
    assert abs(min(xs) - (279.24 - 148 / 2)) < 0.01
    assert abs(max(xs) - (279.24 + 148 / 2)) < 0.01
