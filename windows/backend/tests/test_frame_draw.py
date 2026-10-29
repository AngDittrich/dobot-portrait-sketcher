"""El retrato cae dentro de la hoja enseñada y "Ir aquí" no arrastra el lápiz."""

import asyncio
import re

import pytest

from app.robot.client import MG400Client, Segment, Trajectory
from app.robot.frame import Corner, Frame
from app.robot.mg400 import Reply


class Enlace:
    def __init__(self, pose: tuple[float, float, float, float] = (250.0, 0.0, -65.0, 120.0)) -> None:
        self.moves: list[str] = []
        self._pose = pose

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, _command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def pose(self) -> tuple[float, float, float, float]:
        return self._pose


def _hoja() -> Frame:
    return Frame.from_corners(
        Corner(320.0, 105.0, -65.0, 120.0),
        Corner(320.0, -105.0, -65.0, 120.0),
        Corner(172.0, 105.0, -65.0, 120.0),
    )


def _cliente(enlace: Enlace) -> MG400Client:
    return MG400Client(
        link=enlace,
        z_draw=0.0,
        z_travel=1.0,
        frame=_hoja(),
        lift_mm=8.0,
        margin_mm=8.0,
        pace_lead_s=0.0,
        wait_arrival=False,
        min_step_mm=0.0,
        join_gap_mm=0.0,
        pipeline=1,
    )


def _puntos(enlace: Enlace) -> list[tuple[float, float, float]]:
    salida = []
    for orden in enlace.moves:
        match = re.match(r"MovL\((-?[\d.]+),(-?[\d.]+),(-?[\d.]+),", orden)
        if match:
            salida.append(tuple(float(match.group(i)) for i in (1, 2, 3)))
    return salida


def test_el_retrato_se_queda_dentro_de_la_hoja_con_margen():
    enlace = Enlace()
    trayectoria = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [140.0, 0.0], [140.0, 200.0], [0.0, 200.0]])],
        width_mm=140.0,
        height_mm=200.0,
    )

    async def progreso(_valor: float, _segmento: Segment) -> None:
        return None

    asyncio.run(_cliente(enlace).draw(trayectoria, progreso))

    abajo = [p for p in _puntos(enlace) if p[2] == pytest.approx(-65.0)]
    assert abajo, "algo se tuvo que dibujar"
    xs = [x for x, _, _ in abajo]
    ys = [y for _, y, _ in abajo]
    # 148 de alto menos 8 por lado: el dibujo de 200 se achica a 132 mm.
    assert max(xs) == pytest.approx(320.0 - 8.0)
    assert min(xs) == pytest.approx(172.0 + 8.0)
    assert max(ys) < 105.0 - 8.0 + 1e-6
    assert min(ys) > -105.0 + 8.0 - 1e-6
    arriba = [p for p in _puntos(enlace) if p[2] != pytest.approx(-65.0)]
    assert all(z == pytest.approx(-57.0) for _, _, z in arriba)


def test_ir_a_una_esquina_sube_el_lapiz_antes_de_viajar():
    enlace = Enlace(pose=(250.0, 0.0, -65.0, 120.0))
    cliente = _cliente(enlace)
    x, y, z, r = cliente.frame.named("tr")  # type: ignore[union-attr]

    asyncio.run(cliente.visit(x, y, z + 8.0, r))

    puntos = _puntos(enlace)
    assert puntos[0] == pytest.approx((250.0, 0.0, -57.0))
    assert puntos[-1] == pytest.approx((320.0, -105.0, -57.0))
