"""El trazador de esqueleto es el que necesita la salida de la IA.

Una línea de 1 px no tiene interior: el trazador de contornos la ve como una
mancha y devuelve sus dos bordes (doble línea). El esqueleto devuelve una sola
polilínea, que es lo que el MG400 puede dibujar con un solo trazo.
"""

import numpy as np

from app.pipeline import vectorize as vz


def _thin_line_mask() -> np.ndarray:
    mask = np.zeros((40, 80), np.uint8)
    mask[20, 10:70] = 255
    return mask


def test_skeleton_traces_a_thin_line_once():
    strokes = vz.strokes_from_skeleton(_thin_line_mask(), min_length_px=6)

    assert len(strokes) == 1
    assert abs(vz._polyline_length(strokes[0]) - 60.0) < 8.0


def test_contour_tracer_walks_the_line_twice():
    strokes = vz.strokes_from_mask(_thin_line_mask(), min_length_px=6)

    # El contorno sube por un borde de la línea y baja por el otro: el robot
    # dibujaría el doble de tinta de la que hay.
    total = sum(vz._polyline_length(stroke) for stroke in strokes)
    assert total > 100.0


def test_skeleton_of_a_thick_band_is_one_line():
    mask = np.zeros((40, 80), np.uint8)
    mask[15:25, 10:70] = 255

    strokes = vz.strokes_from_skeleton(mask, min_length_px=6)

    assert len(strokes) == 1
    assert abs(vz._polyline_length(strokes[0]) - 60.0) < 12.0


def test_skeleton_keeps_separate_shapes_separate():
    mask = np.zeros((60, 80), np.uint8)
    mask[10, 10:40] = 255
    mask[45, 10:40] = 255

    strokes = vz.strokes_from_skeleton(mask, min_length_px=6)

    assert len(strokes) == 2
