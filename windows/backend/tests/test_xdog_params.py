"""La ruta lab debe obedecer sigma/phi/umbrales (punto 4: cablear params)."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import SketchParams  # noqa: E402
from app.pipeline import sketch as sketch_ops  # noqa: E402


def _stripes(width=200, height=200, period=8, ramp=False):
    """Barras finas verticales: sigma chico las ve, sigma grande las borra."""
    xs = np.arange(width, dtype=np.float32)
    amp = 5.0 + 95.0 * (xs / max(1, width - 1)) if ramp else 100.0
    gray = (128.0 + amp * np.sin(2.0 * np.pi * xs / period)).astype(np.uint8)
    gray = np.tile(gray, (height, 1))
    return np.dstack([gray, gray, gray])


def _ink(crop, **kwargs):
    _, ink, _ = sketch_ops.lab_portrait_lines(crop, None, None, **kwargs)
    return ink


def test_sigma_param_changes_output():
    """sigma=0.8 ve las barras finas, sigma=2.5 las funde: distinta tinta."""
    crop = _stripes()
    fine = _ink(crop, sigma=0.8)
    coarse = _ink(crop, sigma=2.5)
    assert fine.shape == coarse.shape
    assert not np.array_equal(fine, coarse)
    assert int((fine == 255).sum()) > int((coarse == 255).sum())


def test_flat_threshold_param_changes_output():
    """Sin landmarks manda flat_thresh: 0.05 deja casi todo, 0.5 casi nada.

    Con phi bajo la respuesta es gradual (no todo satura a 1) y la rampa
    de contraste deja líneas débiles a la izquierda que solo el umbral
    flojo conserva.
    """
    crop = _stripes(period=16, ramp=True)
    loose = _ink(crop, phi=4.0, flat_thresh=0.05)
    strict = _ink(crop, phi=4.0, flat_thresh=0.5)
    assert int((loose == 255).sum()) > int((strict == 255).sum())


def test_sketch_params_carry_lab_defaults():
    """La API refleja lo que la cabina usa de verdad (no 0.9/32 heredados)."""
    params = SketchParams()
    assert params.sigma == 1.2
    assert params.phi == 40.0
    assert params.threshold == 0.12
    assert params.bg_threshold == 0.28
