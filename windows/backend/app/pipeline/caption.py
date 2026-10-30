"""Rótulo que el robot escribe debajo del retrato.

No lo pide el modelo de imagen: una letra mal escrita en el papel no se puede
negociar. Cada signo es un trazo simple, el mismo tipo de línea central que
ya recorre el robot, y se añade después de podar para que el tiempo no se lo
coma.
"""

from __future__ import annotations

import math

import numpy as np

CAPTION_TEXT = "SYSCOM ROBOTICS"

# Alto de diseño de cada letra. El avance incluye el aire hasta la siguiente.
_CAP = 6.0
_ADVANCE = 5.15
_SPACE = 2.5
_I_ADVANCE = 3.2

# Trazos en coordenadas de diseño: x a la derecha, y hacia abajo.
_GLYPHS: dict[str, tuple[float, list[list[tuple[float, float]]]]] = {
    "S": (
        _ADVANCE,
        [[
            (3.45, 1.05),
            (2.15, 0.35),
            (0.7, 1.05),
            (0.55, 2.15),
            (1.45, 2.9),
            (2.7, 3.2),
            (3.5, 4.05),
            (3.35, 5.15),
            (2.05, 5.7),
            (0.6, 5.15),
        ]],
    ),
    "Y": (
        _ADVANCE,
        [
            [(0.4, 0.45), (2.05, 2.75), (3.7, 0.45)],
            [(2.05, 2.75), (2.05, 5.55)],
        ],
    ),
    "C": (
        _ADVANCE,
        [[
            (3.4, 1.15),
            (2.05, 0.4),
            (0.75, 1.2),
            (0.45, 3.0),
            (0.75, 4.85),
            (2.05, 5.6),
            (3.4, 4.85),
        ]],
    ),
    "O": (
        _ADVANCE,
        [[
            (2.05, 0.4),
            (3.35, 1.15),
            (3.6, 3.0),
            (3.35, 4.9),
            (2.05, 5.6),
            (0.75, 4.9),
            (0.45, 3.0),
            (0.75, 1.15),
            (2.05, 0.4),
        ]],
    ),
    "M": (
        _ADVANCE,
        [[(0.4, 5.55), (0.4, 0.5), (2.05, 3.35), (3.7, 0.5), (3.7, 5.55)]],
    ),
    "R": (
        _ADVANCE,
        [
            [
                (0.5, 5.55),
                (0.5, 0.5),
                (2.35, 0.5),
                (3.4, 1.3),
                (3.4, 2.25),
                (2.3, 3.05),
                (0.5, 3.05),
            ],
            [(1.75, 3.05), (3.6, 5.55)],
        ],
    ),
    "B": (
        _ADVANCE,
        [
            [
                (0.5, 5.55),
                (0.5, 0.5),
                (2.25, 0.5),
                (3.35, 1.25),
                (3.3, 2.15),
                (2.2, 2.9),
                (0.5, 2.9),
            ],
            [
                (0.5, 2.9),
                (2.4, 2.9),
                (3.5, 3.75),
                (3.45, 4.75),
                (2.25, 5.55),
                (0.5, 5.55),
            ],
        ],
    ),
    "T": (
        _ADVANCE,
        [
            [(0.3, 0.7), (3.8, 0.7)],
            [(2.05, 0.7), (2.05, 5.55)],
        ],
    ),
    "I": (
        _I_ADVANCE,
        [
            [(0.55, 0.55), (2.45, 0.55)],
            [(1.5, 0.55), (1.5, 5.5)],
            [(0.55, 5.5), (2.45, 5.5)],
        ],
    ),
    " ": (_SPACE, []),
}


def _portrait_bottom(strokes: list[np.ndarray], height: int) -> float:
    bottoms = [float(np.max(stroke[:, 1])) for stroke in strokes if len(stroke)]
    if not bottoms:
        return float(max(0, height - 1))
    return max(bottoms)


def _layout(text: str) -> tuple[float, list[tuple[float, list[list[tuple[float, float]]]]]]:
    """Devuelve el ancho de diseño y cada letra con su x de origen."""
    cursor = 0.0
    placed: list[tuple[float, list[list[tuple[float, float]]]]] = []
    for char in text:
        glyph = _GLYPHS.get(char)
        if glyph is None:
            continue
        advance, strokes = glyph
        if strokes:
            placed.append((cursor, strokes))
        cursor += advance
    return cursor, placed


def append_caption(
    strokes: list[np.ndarray],
    width: int,
    height: int,
    text: str = CAPTION_TEXT,
) -> tuple[list[np.ndarray], int]:
    """Añade el rótulo centrado, debajo de la tinta, y alarga el lienzo.

    El ancho no cambia: la cara sigue llenando los 140 mm y las letras
    ocupan una franja nueva bajo los hombros.
    """
    if width <= 0 or height <= 0 or not text:
        return list(strokes), height

    design_width, placed = _layout(text)
    if design_width <= 0 or not placed:
        return list(strokes), height

    scale = (float(width) * 0.88) / design_width
    cap = _CAP * scale
    gap = max(12.0, cap * 0.62)
    pad = cap * 0.42
    top = _portrait_bottom(strokes, height) + gap
    origin_x = (float(width) - design_width * scale) / 2.0

    caption: list[np.ndarray] = []
    for cursor, glyph_strokes in placed:
        for stroke in glyph_strokes:
            points = np.array(
                [
                    (origin_x + (cursor + x) * scale, top + y * scale)
                    for x, y in stroke
                ],
                dtype=np.float32,
            )
            if len(points) >= 2:
                caption.append(points)

    if not caption:
        return list(strokes), height

    bottom = max(float(np.max(stroke[:, 1])) for stroke in caption)
    new_height = max(height, int(math.ceil(bottom + pad)))
    return [*strokes, *caption], new_height
