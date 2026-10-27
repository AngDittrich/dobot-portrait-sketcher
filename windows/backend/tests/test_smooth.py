"""Modelo de segmentacion por defecto + suavizado de trazos (lineas rectas)."""

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import SketchParams  # noqa: E402
from app.pipeline.portrait import PortraitRenderer  # noqa: E402
from app.pipeline.vectorize import simplify_and_smooth  # noqa: E402

MODELS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")


def test_recto_defaults_reduce_vertices():
    # Lo que calma el tembleque del robot: RDP ancho + 2 pasadas Chaikin.
    assert SketchParams().simplify_px == 2.5
    assert SketchParams().smooth_iters == 2


def test_default_segmentation_is_portrait():
    renderer = PortraitRenderer(Path(MODELS))
    assert renderer.u2net.model_path.name == "u2netp.onnx"


def test_smooth_straightens_zigzag():
    zigzag = np.array([[float(x), 5.0 if x % 20 < 10 else -5.0] for x in range(0, 101, 5)], np.float32)
    out = simplify_and_smooth(zigzag, epsilon_px=1.2, iterations=2)
    assert len(out) < len(zigzag)
    # Extremos intactos: empieza y termina donde mismo.
    assert np.allclose(out[0], zigzag[0])
    assert np.allclose(out[-1], zigzag[-1])


def test_smooth_keeps_colinear():
    line = np.array([[0.0, 0.0], [50.0, 0.0], [100.0, 0.0]], np.float32)
    out = simplify_and_smooth(line, epsilon_px=1.2, iterations=2)
    assert len(out) == 2
    assert np.allclose(out[0], [0.0, 0.0])
    assert np.allclose(out[-1], [100.0, 0.0])


def test_smooth_short_passthrough():
    pts = np.array([[1.0, 2.0]], np.float32)
    out = simplify_and_smooth(pts, epsilon_px=1.2, iterations=2)
    assert np.allclose(out, pts)
