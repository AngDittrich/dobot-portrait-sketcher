"""El tiempo que anuncia la cabina tiene que ser el que de verdad tarda el brazo.

Medido con la tuberia de 3 ordenes en vuelo: 174 mm en 8.9 s = 19.6 mm/s. Con
una sola orden en vuelo baja a 7.5 mm/s. El codigo estimaba a 80 mm/s, asi que
prometia 25 s para un retrato que tarda mas de dos minutos y el recorte de
presupuesto (150 s) se hacia con un numero cuatro veces menor que el real.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.caption import append_caption  # noqa: E402
from app.pipeline.vectorize import (  # noqa: E402
    MEASURED_SPEED_MM_S,
    MIN_COMMAND_S,
    PEN_LIFT_S,
    estimate_seconds,
    prune_to_budget,
)
from app.robot.client import MockRobotClient  # noqa: E402
from app.main import remaining_eta_seconds  # noqa: E402


def test_la_velocidad_es_la_medida_en_el_robot() -> None:
    assert MEASURED_SPEED_MM_S == pytest.approx(19.6, abs=0.1)


def test_estimate_seconds_usa_la_velocidad_medida() -> None:
    # 100 px de ancho con dos trazos de 50 px: 140 mm de tinta y 14 mm de
    # traslado entre ellos, que va 1.6 veces mas rapido.
    trazos = [np.array([[0.0, 0.0], [50.0, 0.0]]), np.array([[50.0, 10.0], [100.0, 10.0]])]
    esperado = (
        2 * max(70.0 / MEASURED_SPEED_MM_S, MIN_COMMAND_S)
        + 2 * MIN_COMMAND_S
        + max(14.0 / (MEASURED_SPEED_MM_S * 1.6), MIN_COMMAND_S)
        + PEN_LIFT_S
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
