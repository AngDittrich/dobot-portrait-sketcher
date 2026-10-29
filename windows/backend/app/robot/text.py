"""La palabra SYSCOM, en trazos de una sola pasada, para probar la hoja.

No es un retrato: son las letras en el centro de la hoja enseñada, para ver
si el lápiz cae donde se calibró antes de gastar una foto.
"""

from __future__ import annotations

from app.robot.client import Segment, Trajectory

# Cada letra: ancho en unidades de su alto, y polilíneas con Y hacia abajo.
# El origen de cada letra es su esquina superior izquierda.
_GAP = 0.22
_LETTERS: list[tuple[float, list[list[tuple[float, float]]]]] = [
    # S
    (0.72, [[(0.66, 0.08), (0.10, 0.08), (0.10, 0.46), (0.62, 0.46), (0.62, 0.92), (0.06, 0.92)]]),
    # Y
    (0.70, [[(0.08, 0.04), (0.35, 0.42)], [(0.62, 0.04), (0.35, 0.42), (0.35, 0.96)]]),
    # S
    (0.72, [[(0.66, 0.08), (0.10, 0.08), (0.10, 0.46), (0.62, 0.46), (0.62, 0.92), (0.06, 0.92)]]),
    # C
    (0.66, [[(0.58, 0.14), (0.18, 0.10), (0.08, 0.28), (0.08, 0.72), (0.18, 0.90), (0.58, 0.86)]]),
    # O
    (
        0.70,
        [[
            (0.16, 0.08),
            (0.54, 0.08),
            (0.64, 0.24),
            (0.64, 0.76),
            (0.54, 0.92),
            (0.16, 0.92),
            (0.06, 0.76),
            (0.06, 0.24),
            (0.16, 0.08),
        ]],
    ),
    # M
    (0.86, [[(0.06, 0.96), (0.06, 0.06), (0.43, 0.55), (0.80, 0.06), (0.80, 0.96)]]),
]


def _unit_width() -> float:
    return sum(width for width, _ in _LETTERS) + _GAP * (len(_LETTERS) - 1)


def syscom_trajectory(width_mm: float, height_mm: float, margin_mm: float = 8.0) -> Trajectory:
    """SYSCOM centrado en la hoja, en milímetros desde la esquina superior izquierda."""
    usable_w = width_mm - 2 * margin_mm
    usable_h = height_mm - 2 * margin_mm
    if usable_w < 20 or usable_h < 12:
        raise ValueError("la hoja no deja sitio para escribir SYSCOM")
    units = _unit_width()
    text_h = min(usable_h * 0.55, usable_w / units)
    text_w = text_h * units
    origin_u = (width_mm - text_w) / 2
    origin_v = (height_mm - text_h) / 2

    segments: list[Segment] = []
    cursor = 0.0
    for width, strokes in _LETTERS:
        for stroke in strokes:
            points = [
                [origin_u + (cursor + x) * text_h, origin_v + y * text_h]
                for x, y in stroke
            ]
            segments.append(Segment(type="draw", points=points))
        cursor += width + _GAP

    return Trajectory(segments=segments, width_mm=width_mm, height_mm=height_mm)
