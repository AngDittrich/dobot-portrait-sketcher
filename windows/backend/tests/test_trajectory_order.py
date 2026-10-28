"""El viaje con el lápiz arriba va antes del trazo que empieza, no después."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.vectorize import build_trajectory  # noqa: E402


def test_el_viaje_precede_al_trazo_siguiente():
    primero = np.array([[0.0, 0.0], [10.0, 0.0]], dtype=np.float32)
    segundo = np.array([[0.0, 20.0], [10.0, 20.0]], dtype=np.float32)
    result = build_trajectory(
        [primero, segundo],
        width=100,
        height=100,
        target_width_mm=100.0,
        spacing_mm=10.0,
    )

    tipos = [segmento["type"] for segmento in result.segments]
    assert tipos == ["draw", "travel", "draw"]

    dibujo, viaje, siguiente = result.segments
    assert viaje["points"][0] == dibujo["points"][-1]
    assert viaje["points"][-1] == siguiente["points"][0]
    assert result.stats["height_mm"] == 100.0


def test_un_solo_trazo_no_tiene_viaje():
    linea = np.array([[0.0, 0.0], [10.0, 0.0]], dtype=np.float32)
    result = build_trajectory([linea], width=100, height=40, target_width_mm=100.0, spacing_mm=10.0)
    assert [segmento["type"] for segmento in result.segments] == ["draw"]
