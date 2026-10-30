"""El tiempo que anuncia la cabina tiene que ser el que de verdad tarda el brazo.

La cabina dibuja a SpeedL=50 con AccL=100. En un paso corto manda la
aceleración, no los 19.6 mm/s medidos cuando SpeedL era 20, ni 3 s fijos
cada vez que sube la pluma.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.caption import append_caption  # noqa: E402
from app.pipeline.vectorize import (  # noqa: E402
    BOOTH_ACC_MM_S2,
    BOOTH_DRAW_SPEED_MM_S,
    BOOTH_LIFT_MM,
    BOOTH_TRAVEL_SPEED_MM_S,
    MEASURED_SPEED_MM_S,
    estimate_seconds,
    prune_to_budget,
)
from app.robot.client import MockRobotClient, PACE_EFFICIENCY, effective_speed_mm_s  # noqa: E402
from app.main import remaining_eta_seconds  # noqa: E402


def _seg(distance_mm: float, speed_mm_s: float) -> float:
    rate = effective_speed_mm_s(distance_mm, speed_mm_s, BOOTH_ACC_MM_S2) * PACE_EFFICIENCY
    return distance_mm / rate


def test_la_velocidad_es_la_medida_en_el_robot() -> None:
    assert MEASURED_SPEED_MM_S == pytest.approx(19.6, abs=0.1)
    assert BOOTH_DRAW_SPEED_MM_S == 50.0


def test_estimate_seconds_usa_la_fisica_de_la_cabina() -> None:
    # 100 px de ancho, dos trazos de 50 px: 70 mm de tinta cada uno y 14 mm
    # de viaje. La pluma sube y baja 8 mm a la velocidad de traslado.
    trazos = [np.array([[0.0, 0.0], [50.0, 0.0]]), np.array([[50.0, 10.0], [100.0, 10.0]])]
    esperado = (
        2 * _seg(70.0, BOOTH_DRAW_SPEED_MM_S)
        + _seg(14.0, BOOTH_TRAVEL_SPEED_MM_S)
        + 2 * _seg(BOOTH_LIFT_MM, BOOTH_TRAVEL_SPEED_MM_S)
    )

    assert estimate_seconds(trazos, 100, target_width_mm=140.0) == pytest.approx(esperado, rel=0.02)


def test_el_simulador_usa_la_velocidad_medida_del_robot() -> None:
    assert MockRobotClient().speed_mm_s == MEASURED_SPEED_MM_S


def test_el_rotulo_no_agota_el_presupuesto_del_retrato() -> None:
    """SYSCOM ROBOTICS deja tiempo para los rasgos del retrato."""
    caption, _ = append_caption([], width=900, height=1200)

    segundos = estimate_seconds(caption, 900, target_width_mm=90.0)
    assert segundos < 150.0


def test_la_eta_resta_el_tiempo_transcurrido_real() -> None:
    # Los costes de levantadas y órdenes no se reparten por distancia: la ETA
    # debe descontar el reloj real y no multiplicar el progreso geométrico.
    assert remaining_eta_seconds(120.0, started_at=10.0, now=35.0) == 95.0


def test_un_presupuesto_imposible_no_excede_su_tope() -> None:
    strokes = [np.array([[0.0, 0.0], [10.0, 0.0]])]

    assert prune_to_budget(strokes, 10, max_seconds=0.0, min_strokes=0) == []
