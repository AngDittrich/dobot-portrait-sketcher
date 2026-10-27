"""Face-parsing -> bordes de regiones (base estilo mariposa). Solo funciones
puras: no necesitan el modelo (el .onnx se prueba en E2E)."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.faceparse import HAIR_GROUP, boundaries, group_classes


def test_group_classes_mapea_pelo_y_ropa():
    clases = np.array([[1, 13], [18, 0]], dtype=np.uint8)
    g = group_classes(clases)
    assert g[0, 0] != g[0, 1]  # piel vs pelo difieren
    assert g[0, 1] == HAIR_GROUP
    assert g[1, 0] != g[1, 1]  # ropa vs fondo difieren


def test_boundaries_marca_solo_el_borde():
    g = np.array(
        [
            [1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1],
            [2, 2, 2, 2, 2],
            [2, 2, 2, 2, 2],
            [2, 2, 2, 2, 2],
        ],
        dtype=np.uint8,
    )
    ink = boundaries(g)
    assert ink.shape == g.shape
    assert ink.dtype == np.uint8
    # Filas 1 y 2 (el borde entre regiones), sin marco de imagen.
    assert set(np.unique(ink[1]).tolist()) == {0, 255}
    assert set(np.unique(ink[2]).tolist()) == {0, 255}
    assert (ink[0] == 255).all()
    assert (ink[4] == 255).all()


def test_boundaries_region_uniforme_no_da_tinta():
    g = np.full((6, 6), 1, dtype=np.uint8)
    assert (boundaries(g) == 255).all()
