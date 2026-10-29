"""J4, la muñeca del tool, se queda en -50 en todo movimiento y vuelve si algo la giró."""

import asyncio
import math
import re

import pytest

from app.robot.client import J4_FIXED, MG400Client
from app.robot.frame import Corner, Frame
from app.robot.mg400 import Reply


class Enlace:
    def __init__(
        self,
        pose: tuple[float, float, float, float] = (300.0, 0.0, -65.0, -50.0),
        angles: list[float] | None = None,
    ) -> None:
        self.moves: list[str] = []
        self._pose = pose
        self._angles = angles

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        match = re.match(r"MovL\(([^,]+),([^,]+),([^,]+),([^,]+),", command)
        if match:
            x, y, z, r = (float(part) for part in match.groups())
            self._pose = (x, y, z, r)
            if self._angles is not None:
                j1 = math.degrees(math.atan2(y, x))
                self._angles = [j1, self._angles[1], self._angles[2], r - j1]
        return Reply(code=0, value="")

    def dashboard(self, _command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def pose(self) -> tuple[float, float, float, float]:
        return self._pose


class EnlaceConAngulos(Enlace):
    def angles(self) -> list[float]:
        assert self._angles is not None
        return list(self._angles)


def _cliente(enlace: Enlace) -> MG400Client:
    return MG400Client(
        link=enlace,
        z_draw=-65.0,
        z_travel=-57.0,
        frame=Frame.from_corners(
            Corner(340.9, -79.0, -66.8, 0.8),
            Corner(241.9, -72.9, -69.9, -3.0),
            Corner(342.3, 51.9, -67.6, 22.4),
        ),
        pace_lead_s=0.0,
        wait_arrival=False,
        min_step_mm=0.0,
        join_gap_mm=0.0,
        pipeline=1,
    )


def _j4(command: str) -> float:
    x, y, _z, r = (float(part) for part in command[5:].split(",")[:4])
    return r - math.degrees(math.atan2(y, x))


def test_r_deja_j4_en_menos_50_a_ambos_lados_de_la_hoja():
    cliente = _cliente(Enlace())
    for x, y in ((340.9, -79.0), (342.3, 51.9), (243.3, 58.0)):
        assert cliente.r_for(x, y) - math.degrees(math.atan2(y, x)) == pytest.approx(J4_FIXED)


def test_visit_y_marcar_el_area_no_giran_la_muneca():
    enlace = Enlace()
    cliente = _cliente(enlace)
    asyncio.run(cliente.visit(243.3, 58.0, -70.7, 18.7, lift=8.0))
    asyncio.run(cliente.mark_area())
    movl = [orden for orden in enlace.moves if orden.startswith("MovL(")]
    assert len(movl) > 6
    assert all(_j4(orden) == pytest.approx(J4_FIXED, abs=0.01) for orden in movl)


def test_una_j4_girada_vuelve_a_menos_50():
    enlace = EnlaceConAngulos(pose=(300.0, 0.0, -65.0, -20.0), angles=[0.0, 30.0, 20.0, -20.0])
    cliente = _cliente(enlace)
    assert asyncio.run(cliente.ensure_j4()) is True
    assert enlace.moves, "debió mandar la corrección"
    assert _j4(enlace.moves[0]) == pytest.approx(J4_FIXED, abs=0.01)
    # Con lápiz arriba por defecto: sube a la altura de viaje.
    assert float(enlace.moves[0][5:].split(",")[2]) == pytest.approx(cliente.z_travel)


def test_sin_lift_corrige_en_el_sitio():
    enlace = EnlaceConAngulos(pose=(300.0, 0.0, -66.0, -20.0), angles=[0.0, 30.0, 20.0, -20.0])
    cliente = _cliente(enlace)
    assert asyncio.run(cliente.ensure_j4(lift=False)) is True
    assert float(enlace.moves[0][5:].split(",")[2]) == pytest.approx(-66.0)


def test_si_el_movl_no_basta_manda_jointmovj():
    class Terca(EnlaceConAngulos):
        def move(self, command: str) -> Reply:
            self.moves.append(command)
            return Reply(code=0, value="")

    enlace = Terca(pose=(300.0, 0.0, -65.0, -20.0), angles=[1.0, 30.0, 20.0, -20.0])
    cliente = _cliente(enlace)
    asyncio.run(cliente.ensure_j4())
    assert enlace.moves[-1] == "JointMovJ(1.000,30.000,20.000,-50.000)"


def test_j4_en_su_sitio_no_manda_nada():
    enlace = EnlaceConAngulos(angles=[0.0, 30.0, 20.0, -50.3])
    cliente = _cliente(enlace)
    assert asyncio.run(cliente.ensure_j4()) is False
    assert enlace.moves == []


def test_si_r_resulta_ser_j4_r_queda_fija():
    enlace = EnlaceConAngulos(pose=(300.0, 150.0, -65.0, -50.0), angles=[26.6, 30.0, 20.0, -50.0])
    cliente = _cliente(enlace)
    asyncio.run(cliente._measure_r_model())
    assert cliente.r_model == "j4"
    assert cliente.r_for(300.0, 150.0) == pytest.approx(J4_FIXED)


def test_el_modelo_documentado_se_confirma():
    enlace = EnlaceConAngulos(pose=(300.0, 150.0, -65.0, -23.4), angles=[26.6, 30.0, 20.0, -50.0])
    cliente = _cliente(enlace)
    asyncio.run(cliente._measure_r_model())
    assert cliente.r_model == "j1+j4"
