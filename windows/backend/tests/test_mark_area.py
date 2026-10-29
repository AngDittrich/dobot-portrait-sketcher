"""Marcar el área de la hoja enseñada: el lápiz nunca baja al recorrer el borde."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client  # noqa: E402
from app.robot.frame import Corner, Frame  # noqa: E402
from app.robot.mg400 import MG400Error, Reply  # noqa: E402


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


def _hoja() -> Frame:
    return Frame.from_corners(
        Corner(320.0, 105.0, -65.0, 120.0),
        Corner(320.0, -105.0, -65.0, 120.0),
        Corner(172.0, 105.0, -65.0, 120.0),
    )


def _cliente(enlace: EnlaceFalso, frame: Frame | None) -> MG400Client:
    return MG400Client(
        link=enlace,
        pace_lead_s=0.0,
        wait_arrival=False,
        min_step_mm=0.0,
        host="192.168.10.55",
        z_draw=-97.0,
        z_travel=-90.0,
        speed_factor=20,
        frame=frame,
        lift_mm=8.0,
    )


def _movl(enlace: EnlaceFalso) -> list[tuple[float, float, float]]:
    puntos = []
    for orden in enlace.moves:
        if orden.startswith("MovL("):
            x, y, z = (float(valor) for valor in orden[5:].split(",")[:3])
            puntos.append((x, y, z))
    return puntos


def test_el_borde_de_la_hoja_se_recorre_con_el_lapiz_arriba():
    enlace = EnlaceFalso()
    asyncio.run(_cliente(enlace, _hoja()).mark_area())

    puntos = _movl(enlace)
    assert len(puntos) == 6  # centro, cuatro esquinas y vuelta al inicio
    assert puntos[0][:2] == pytest.approx((246.0, 0.0), abs=0.01)
    assert all(z == pytest.approx(-57.0) for _, _, z in puntos), "el lápiz va 8 mm arriba de la hoja"
    assert not any("CP=100)" in orden for orden in enlace.moves)
    xs = [x for x, _, _ in puntos]
    ys = [y for _, y, _ in puntos]
    assert min(xs) == pytest.approx(172.0) and max(xs) == pytest.approx(320.0)
    assert min(ys) == pytest.approx(-105.0) and max(ys) == pytest.approx(105.0)


def test_una_hoja_estandar_se_marca_centrada_en_las_esquinas():
    # La hoja enseñada mide 210 × 148. A6 horizontal es 148 × 105 y queda
    # centrada: 148 mm a lo ancho (Y) y 105 mm de fondo (X).
    enlace = EnlaceFalso()
    asyncio.run(_cliente(enlace, _hoja()).mark_area(148.0, 105.0))

    puntos = _movl(enlace)
    assert puntos[0][:2] == pytest.approx((246.0, 0.0), abs=0.01)
    assert all(z == pytest.approx(-57.0) for _, _, z in puntos)
    xs = [x for x, _, _ in puntos]
    ys = [y for _, y, _ in puntos]
    assert min(xs) == pytest.approx(193.5) and max(xs) == pytest.approx(298.5)
    assert min(ys) == pytest.approx(-74.0) and max(ys) == pytest.approx(74.0)


def test_un_marco_mas_grande_que_el_alcance_se_rechaza():
    from app.robot.frame import outline_block

    lejos = Frame.from_corners(
        Corner(430.0, 180.0, -65.0, 90.0),
        Corner(430.0, -180.0, -65.0, 90.0),
        Corner(380.0, 180.0, -65.0, 90.0),
    )
    assert "440" in outline_block(lejos, 297.0, 210.0)
    assert outline_block(_hoja(), 210.0, 148.0) == ""


def test_sin_esquinas_no_se_marca_nada():
    enlace = EnlaceFalso()
    with pytest.raises(MG400Error, match="esquinas"):
        asyncio.run(_cliente(enlace, None).mark_area())
    assert enlace.moves == []
