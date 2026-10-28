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
    parse_booth,
    write_booth,
)
from app.robot.client import MG400Client  # noqa: E402


def _cabina(**overrides: object) -> dict:
    base = {
        "backend": "mg400",
        "host": "192.168.10.55",
        "dry_run": False,
        "user": 0,
        "tool": 0,
        "z_draw": -167,
        "z_travel": -160,
        "r": 145,
        "r_far": 96,
        "far_x": 218,
        "far_y": -145,
        "speed_factor": 20,
        "origin_x": 360,
        "origin_y": 92,
        "x_sign": -1,
        "y_sign": -1,
        "cp_draw": 0,
    }
    base.update(overrides)
    return base


def test_el_viaje_tiene_que_quedar_arriba_del_dibujo():
    with pytest.raises(BoothError, match="por encima"):
        parse_booth(_cabina(z_draw=-160, z_travel=-167))


def test_guardar_cambia_el_origen_y_suelta_el_socket(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.robot.booth.PATH", tmp_path / "robot.json")
    booth = parse_booth(_cabina(origin_x=300, origin_y=80, host="192.168.10.40"))
    client = MG400Client(host="192.168.10.55", z_draw=-167, z_travel=-160, r=145, origin_x=360, origin_y=92)
    client._link = object()
    client._ready = True

    apply_booth(client, booth)
    write_booth(booth)

    assert client.origin_x == 300
    assert client.origin_y == 80
    assert client.host == "192.168.10.40"
    assert client._link is None
    assert client._ready is False
    saved = json.loads((tmp_path / "robot.json").read_text(encoding="utf-8"))
    assert saved["origin_x"] == 300
    assert PATH != tmp_path / "robot.json"
