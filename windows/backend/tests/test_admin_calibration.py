"""El panel revisa unas esquinas sin guardarlas y no manda el brazo fuera de alcance."""

import asyncio
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

    async def visit(self, x: float, y: float, z: float, r: float, speed: int | None = None) -> None:
        self.visitas.append((x, y, z, r))


def test_ir_a_la_esquina_calculada_va_con_el_lapiz_arriba(monkeypatch: pytest.MonkeyPatch):
    robot = _Robot()
    monkeypatch.setattr(main, "robot", robot)
    asyncio.run(
        main.admin_goto({"corner": "br", "corners": ESQUINAS, "lift_mm": 8}, x_admin_token=_token())
    )
    assert robot.visitas == [pytest.approx((172.0, -105.0, -57.0, 120.0))]


def test_un_punto_fuera_del_alcance_no_se_visita(monkeypatch: pytest.MonkeyPatch):
    robot = _Robot()
    monkeypatch.setattr(main, "robot", robot)
    with pytest.raises(main.HTTPException) as excinfo:
        asyncio.run(
            main.admin_goto({"point": {"x": 500.0, "y": 0.0, "z": -65.0, "r": 0.0}}, x_admin_token=_token())
        )
    assert excinfo.value.status_code == 409
    assert robot.visitas == []
