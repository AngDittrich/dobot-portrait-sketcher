"""El robot escribe SYSCOM ROBOTICS debajo del retrato, sin encimar la cara."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.caption import CAPTION_TEXT, append_caption  # noqa: E402


def test_el_rotulo_queda_debajo_y_centrado():
    portrait = [np.array([[40, 30], [80, 120], [20, 90]], dtype=np.float32)]
    strokes, height = append_caption(portrait, 400, 160)

    assert strokes[0] is portrait[0]
    caption = strokes[1:]
    assert len(caption) >= 16
    ink_top = min(float(np.min(stroke[:, 1])) for stroke in caption)
    assert ink_top > 120
    assert height > 160
    xs = np.concatenate([stroke[:, 0] for stroke in caption])
    ys = np.concatenate([stroke[:, 1] for stroke in caption])
    assert xs.min() > 0
    assert xs.max() < 400
    assert ys.max() < height
    assert abs(float((xs.min() + xs.max()) / 2) - 200) < 8


def test_una_letra_desconocida_no_rompe_la_linea():
    strokes, _height = append_caption([], 300, 80, text=CAPTION_TEXT + " ¿?")
    assert strokes
    xs = np.concatenate([stroke[:, 0] for stroke in strokes])
    assert xs.min() > 0
    assert xs.max() < 300
