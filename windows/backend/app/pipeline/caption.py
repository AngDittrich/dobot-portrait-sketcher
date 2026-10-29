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

def _arc(
    cx: float, cy: float, rx: float, ry: float, start: float, sweep: float, steps: int
) -> list[tuple[float, float]]:
    """Arco con Y hacia abajo. `sweep` positivo gira en sentido horario visual."""
    return [
        (
            cx + rx * math.cos(start + sweep * index / steps),
            cy + ry * math.sin(start + sweep * index / steps),
        )
        for index in range(steps + 1)
    ]


# Trazos en coordenadas de diseño: x a la derecha, y hacia abajo.
_GLYPHS: dict[str, tuple[float, list[list[tuple[float, float]]]]] = {
    "S": (
        _ADVANCE,
        [[
            *_arc(2.05, 1.75, 1.4, 1.15, 0.35, math.pi + 0.9, 14),
            *_arc(2.05, 4.35, 1.4, 1.15, math.pi + 0.55, math.pi + 0.7, 14)[1:],
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
        [_arc(2.05, 3.0, 1.45, 2.45, -0.85, -(2 * math.pi - 1.7), 16)],
    ),
    "O": (
        _ADVANCE,
        [_arc(2.05, 3.0, 1.5, 2.5, -math.pi / 2, 2 * math.pi, 16)],
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
                (0.5, 0.55),
                *_arc(1.7, 1.75, 1.55, 1.2, math.pi, -math.pi, 12)[1:],
                (0.5, 2.95),
            ],
            [(1.55, 2.95), (3.6, 5.55)],
        ],
    ),
    "B": (
        _ADVANCE,
        [
            [
                (0.5, 5.55),
                (0.5, 0.5),
                *_arc(1.55, 1.7, 1.6, 1.2, math.pi, -math.pi, 12)[1:],
            ],
            [
                (0.5, 2.9),
                *_arc(1.55, 4.25, 1.7, 1.3, math.pi, -math.pi, 12)[1:],
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
