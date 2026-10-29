"""El panel revisa unas esquinas sin guardarlas y no manda el brazo fuera de alcance."""

import asyncio
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main  # noqa: E402
from app.admin_ops import drop_tokens, issue_token  # noqa: E402

ESQUINAS = {
    "tl": {"x": 320.0, "y": 105.0, "z": -65.0, "r": 120.0},
    "tr": {"x": 320.0, "y": -105.0, "z": -65.0, "r": 120.0},
    "bl": {"x": 172.0, "y": 105.0, "z": -65.0, "r": 120.0},
}


def _token() -> str:
    drop_tokens()
    return issue_token()


def test_la_calibracion_mide_la_hoja_sin_guardarla():
    datos = main.admin_calibration({"corners": ESQUINAS, "margin_mm": 8}, x_admin_token=_token())
    assert datos["width_mm"] == pytest.approx(210.0)
    assert datos["orientation"] == "horizontal"
    assert datos["paper"]["label"] == "A5"


def test_unas_esquinas_chuecas_se_explican():
    chuecas = {**ESQUINAS, "bl": {"x": 172.0, "y": 160.0, "z": -65.0, "r": 0.0}}
    with pytest.raises(main.HTTPException) as excinfo:
        main.admin_calibration({"corners": chuecas}, x_admin_token=_token())
    assert excinfo.value.status_code == 409
    assert "ángulo" in excinfo.value.detail


class _Robot:
    name = "mg400"
    lift_mm = 8.0

    def __init__(self) -> None:
        self.visitas: list[tuple[float, float, float, float]] = []
        self.lift = 0.0

    def r_for(self, x: float, y: float) -> float:
        return math.degrees(math.atan2(y, x)) - 50.0

    async def visit(
        self,
        x: float,
        y: float,
        z: float,
        r: float,
        speed: int | None = None,
        *,
        lift: float = 0.0,
    ) -> None:
        self.visitas.append((x, y, z, r))
        self.lift = lift


def test_ir_a_la_esquina_calculada_baja_al_plano_de_las_otras(monkeypatch: pytest.MonkeyPatch):
    robot = _Robot()
    monkeypatch.setattr(main, "robot", robot)
    asyncio.run(
        main.admin_goto({"corner": "br", "corners": ESQUINAS, "lift_mm": 8}, x_admin_token=_token())
    )
    # El viaje usa los 8 mm, pero el punto de llegada es el plano (Z -65), no -57.
    # R no es la enseñada (120): es la que deja J4 en -50 en ese punto.
    r = math.degrees(math.atan2(-105.0, 172.0)) - 50.0
    assert robot.visitas == [pytest.approx((172.0, -105.0, -65.0, r))]
    assert robot.lift == pytest.approx(8.0)


def test_un_punto_fuera_del_alcance_no_se_visita(monkeypatch: pytest.MonkeyPatch):
    robot = _Robot()
    monkeypatch.setattr(main, "robot", robot)
    with pytest.raises(main.HTTPException) as excinfo:
        asyncio.run(
            main.admin_goto({"point": {"x": 500.0, "y": 0.0, "z": -65.0, "r": 0.0}}, x_admin_token=_token())
        )
    assert excinfo.value.status_code == 409
    assert robot.visitas == []
