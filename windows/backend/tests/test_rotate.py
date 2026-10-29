"""El retrato va acostado: la hoja se pone horizontal y el dibujo gira 90 grados."""

from __future__ import annotations

import numpy as np

from app.pipeline import vectorize as vectorize_ops


def _trazo(*puntos: tuple[float, float]) -> np.ndarray:
    return np.array(puntos, dtype=np.float64)


def _trazo_recto(puntos: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Junta los puntos de todos los segmentos de dibujo, en orden."""
    salida: list[tuple[float, float]] = []
    for segment in puntos:
        salida.extend(segment)
    return salida


def _segmentos(resultado) -> list[list[tuple[float, float]]]:
    return [
        [tuple(punto) for punto in segment["points"]]
        for segment in resultado.segments
        if segment["type"] == "draw"
    ]


def test_girado_el_lado_largo_va_de_frente_al_fondo():
    # Lienzo de 100 x 150 px a 1 mm/px: 100 mm de ancho y 150 de alto.
    resultado = vectorize_ops.build_trajectory(
        [_trazo((0.0, 0.0), (0.0, 150.0))],
        width=100,
        height=150,
        target_width_mm=100.0,
        rotate=True,
    )

    assert resultado.stats["target_width_mm"] == 150.0
    assert resultado.stats["height_mm"] == 100.0


def test_girado_mueve_los_puntos_para_que_el_retrato_quede_acostado():
    resultado = vectorize_ops.build_trajectory(
        [_trazo((0.0, 0.0), (0.0, 150.0))],
        width=100,
        height=150,
        target_width_mm=100.0,
        rotate=True,
    )

    puntos = _trazo_recto(_segmentos(resultado))

    # La esquina de arriba a la izquierda pasa a la de arriba a la derecha y
    # el trazo que bajaba ahora cruza de derecha a izquierda.
    assert puntos[0] == (150.0, 0.0)
    assert puntos[-1] == (0.0, 0.0)


def test_sin_giro_todo_queda_como_estaba():
    resultado = vectorize_ops.build_trajectory(
        [_trazo((0.0, 0.0), (0.0, 150.0))],
        width=100,
        height=150,
        target_width_mm=100.0,
    )

    puntos = _trazo_recto(_segmentos(resultado))

    assert resultado.stats["target_width_mm"] == 100.0
    assert resultado.stats["height_mm"] == 150.0
    assert puntos[0] == (0.0, 0.0)
    assert puntos[-1] == (0.0, 150.0)
