"""Encuadre: el recorte debe incluir cuello y hombros, no solo la cabeza."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.portrait import head_region


def _scene():
    height, width = 720, 960
    # Rostro al centro: bbox (x, y, w, h).
    face = {"bbox": (380, 120, 200, 260)}
    alpha = np.zeros((height, width), dtype=np.float32)
    alpha[60:700, 300:660] = 1.0  # silueta de persona amplia
    chin_y = 120 + 260  # borde inferior del bbox
    return (height, width), face, alpha, chin_y


def test_box_reaches_shoulders():
    """El borde inferior baja ~1 cara bajo el mentón (cuello + hombros)."""
    shape, face, alpha, chin_y = _scene()
    _, _, _, bottom = head_region(shape, face, alpha, chin_y=chin_y)
    face_h = face["bbox"][3]
    assert bottom >= chin_y + 0.9 * face_h, f"bottom={bottom} no llega a hombros"


def test_box_stays_inside_image():
    """Aunque pida hombros, el recorte no se sale de la foto."""
    shape, face, alpha, chin_y = _scene()
    x0, y0, x1, y1 = head_region(shape, face, alpha, chin_y=chin_y)
    height, width = shape
    assert 0 <= x0 < x1 <= width
    assert 0 <= y0 < y1 <= height
