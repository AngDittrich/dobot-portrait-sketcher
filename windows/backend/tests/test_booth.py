"""La calibración de la cabina se guarda fuera del .env y pasa al cliente vivo."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.booth import (  # noqa: E402
    PATH,
    BoothError,
    apply_booth,
    client_from_booth,
    parse_booth,
    write_booth,
)
from app.robot.client import MG400Client  # noqa: E402

ESQUINAS = {
    "tl": {"x": 320.0, "y": 105.0, "z": -65.0, "r": 120.0},
    "tr": {"x": 320.0, "y": -105.0, "z": -65.0, "r": 120.0},
    "bl": {"x": 172.0, "y": 105.0, "z": -65.0, "r": 120.0},
}


def _cabina(**overrides: object) -> dict:
    base = {
        "backend": "mg400",
        "host": "192.168.10.55",
        "dry_run": False,
        "user": 0,
        "tool": 0,
        "speed_factor": 20,
        "cp_draw": 0,
        "corners": ESQUINAS,
        "lift_mm": 8,
        "margin_mm": 8,
    }
    base.update(overrides)
    return base


def test_levantar_el_lapiz_tiene_un_minimo():
    with pytest.raises(BoothError, match="levantar"):
        parse_booth(_cabina(lift_mm=0.5))


def test_una_esquina_fuera_del_alcance_no_se_guarda():
    lejos = {key: {**value, "x": value["x"] + 200} for key, value in ESQUINAS.items()}
    with pytest.raises(BoothError, match="440"):
        parse_booth(_cabina(corners=lejos))


def test_las_esquinas_mandan_en_la_z_de_dibujo_y_de_viaje():
    cliente = client_from_booth(_cabina(lift_mm=10))
    assert isinstance(cliente, MG400Client)
    assert cliente.frame is not None
    assert cliente.frame.width == pytest.approx(210.0)
    assert cliente.z_draw == pytest.approx(-65.0)
    assert cliente.z_travel == pytest.approx(-55.0)


def test_guardar_cambia_la_hoja_y_suelta_el_socket(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.robot.booth.PATH", tmp_path / "robot.json")
    booth = parse_booth(_cabina(host="192.168.10.40"))
    client = MG400Client(host="192.168.10.55", z_draw=-167, z_travel=-160, r=145, origin_x=360, origin_y=92)
    client._link = object()
    client._ready = True

    apply_booth(client, booth)
    write_booth(booth)

    assert client.frame is not None
    assert client.frame.tl.x == pytest.approx(320.0)
    assert client.host == "192.168.10.40"
    assert client._link is None
    assert client._ready is False
    saved = json.loads((tmp_path / "robot.json").read_text(encoding="utf-8"))
    assert saved["corners"]["tr"]["y"] == -105.0
    assert "origin_x" not in saved
    assert PATH != tmp_path / "robot.json"


def test_sin_esquinas_se_puede_guardar_la_conexion():
    booth = parse_booth(_cabina(corners=None))
    assert booth.corners is None
    assert booth.frame is None
