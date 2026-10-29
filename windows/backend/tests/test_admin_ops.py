"""El panel admin solo arma órdenes conocidas y no mueve el brazo durante un dibujo."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.admin_ops import (  # noqa: E402
    AdminOpError,
    describe_alarms,
    drop_tokens,
    issue_token,
    pin_ok,
    plan,
    rate_for,
    token_ok,
)


def test_el_pin_son_cuatro_digitos():
    assert pin_ok("2026", "2026")
    assert not pin_ok("2025", "2026")
    assert not pin_ok("20261", "2026")
    assert not pin_ok("abcd", "2026")


def test_el_token_no_sale_de_la_nada():
    drop_tokens()
    assert not token_ok("no")
    token = issue_token()
    assert token_ok(token)
    drop_tokens()
    assert not token_ok(token)


def test_la_muneca_no_tiene_jog_ni_paso():
    for axis in ("R+", "R-", "J4+", "J4-"):
        with pytest.raises(AdminOpError):
            plan("jog", {"axis": axis}, busy=False)
        with pytest.raises(AdminOpError):
            plan("step", {"axis": axis, "mm": 1}, busy=False)


def test_el_jog_usa_la_velocidad_del_slider_sin_meterla_en_movejog():
    command, _is_move, prepare = plan("jog", {"axis": "X+", "speed": 80}, busy=False)
    assert command == "MoveJog(X+)"
    assert prepare
    assert rate_for("jog", {"axis": "X+", "speed": 80}) == 80
    with pytest.raises(AdminOpError):
        rate_for("jog", {"axis": "X+", "speed": 101})


def test_un_paso_toma_la_velocidad_del_slider():
    command, _is_move, _prepare = plan("step", {"axis": "X+", "mm": 1, "speed": 80}, busy=False)
    assert command == "RelMovL(1.000,0.000,0.000,0.000,80,80)"


def test_soltar_el_jog_no_prepara_la_cola():
    command, is_move, prepare = plan("jog", {"axis": ""}, busy=False)
    assert command == "MoveJog()"
    assert is_move and not prepare


def test_un_paso_cartesiano_es_relmovl():
    command, is_move, _prepare = plan("step", {"axis": "Z-", "mm": 1}, busy=False)
    assert command == "RelMovL(0.000,0.000,-1.000,0.000,20,20)"
    assert is_move


def test_el_paso_no_pasa_de_20_mm():
    with pytest.raises(AdminOpError):
        plan("step", {"axis": "X+", "mm": 50}, busy=False)


def test_durante_un_dibujo_no_hay_jog_ni_stop_de_movimiento():
    with pytest.raises(AdminOpError):
        plan("jog", {"axis": "X+"}, busy=True)
    with pytest.raises(AdminOpError):
        plan("stop", {}, busy=True)
    command, is_move, _prepare = plan("estop", {}, busy=True)
    assert command == "EmergencyStop()"
    assert not is_move


def test_una_pose_en_cero_no_se_pide_en_cero():
    command, is_move, prepare = plan("movl", {"x": 0, "y": 10, "z": -167, "r": 96}, busy=False)
    assert command.startswith("MovL(0.001,10.000,-167.000,96.000,")
    assert is_move and prepare


def test_la_alarma_17_se_lee_en_claro():
    assert "sin solución" in describe_alarms("[[17],[],[],[],[]]")
