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

from app.pipeline.vectorize import MEASURED_SPEED_MM_S, estimate_seconds  # noqa: E402


def test_la_velocidad_es_la_medida_en_el_robot() -> None:
    assert MEASURED_SPEED_MM_S == pytest.approx(19.6, abs=0.1)


def test_estimate_seconds_usa_la_velocidad_medida() -> None:
    # 100 px de ancho con dos trazos de 50 px: 140 mm de tinta y 14 mm de
    # traslado entre ellos, que va 1.6 veces mas rapido.
    trazos = [np.array([[0.0, 0.0], [50.0, 0.0]]), np.array([[50.0, 10.0], [100.0, 10.0]])]
    esperado = 140.0 / MEASURED_SPEED_MM_S + 14.0 / (MEASURED_SPEED_MM_S * 1.6)

    assert estimate_seconds(trazos, 100, target_width_mm=140.0) == pytest.approx(esperado, rel=0.02)
