"""Una sola trayectoria para la vista previa, la animación y el robot.

El cliente del MG400 ya no recorta ni une trazos. Aquí se simplifica por
desviación en milímetros y se unen huecos solo cuando el conector cae sobre
tinta. Si el retrato no cabe en el tope de tiempo, se dibuja entero: borrar
el trazo corto partía el pelo y el cuello y el aviso seguía por encima del tope.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.pipeline import vectorize as vectorize_ops

TOLERANCES_MM = (0.15, 0.25, 0.35)
JOIN_MAX_MM = 8.0
# El rótulo ya viene en trazos separados a propósito (las dos panzas de la B,
# la pierna de la R). Unirlos dibuja una raya que la letra no tiene.
CAPTION_JOIN_MAX_MM = 0.0
INK_SAMPLE_PX = 0.5
INK_COVERAGE = 0.9
DILATE_PX = 2


def plan_robot_path(
    strokes: list[np.ndarray],
    mask: np.ndarray,
    width: int,
    height: int,
    *,
    caption_from: int,
    target_width_mm: float,
    max_seconds: float,
    face_box: tuple[float, float, float, float] | None = None,
    rotate: bool = False,
) -> dict:
    """Devuelve los trazos finales, la trayectoria y los segundos estimados.

    `face_box` se conserva en la firma porque la cabina ya lo manda. No recorta:
    la cara que dibuja el modelo no cae en el rectángulo de la foto, y tirar
    lo que queda afuera abre huecos. El tope solo elige una tolerancia más gruesa.
    """
    del face_box
    portrait = [np.asarray(stroke, dtype=np.float32) for stroke in strokes[:caption_from]]
    caption = [np.asarray(stroke, dtype=np.float32) for stroke in strokes[caption_from:]]
    mm_per_px = float(target_width_mm) / max(1, width)
    ink = _ink(mask, height, width)

    kept = list(portrait)
    chosen = _compose(kept, caption, ink, mm_per_px, TOLERANCES_MM[0])
    for tolerance in TOLERANCES_MM:
        chosen = _compose(kept, caption, ink, mm_per_px, tolerance)
        seconds = vectorize_ops.estimate_seconds(
            chosen, width, target_width_mm=target_width_mm
        )
        if seconds <= max_seconds:
            break

    trajectory = vectorize_ops.build_trajectory(
        chosen,
        width,
        height,
        target_width_mm=target_width_mm,
        rotate=rotate,
    )
    lifts = sum(1 for segment in trajectory.segments if segment["type"] == "travel")
    orders = sum(
        max(0, len(segment["points"]) - 1)
        for segment in trajectory.segments
        if segment["type"] == "draw"
    )
    return {
        "strokes": chosen,
        "segments": trajectory.segments,
        "stats": {
            **trajectory.stats,
            "orders": orders,
            "lifts": lifts,
        },
    }


def connector_on_ink(
    start: np.ndarray,
    end: np.ndarray,
    mask: np.ndarray,
    *,
    max_mm: float,
    mm_per_px: float,
) -> bool:
    """El hueco cabe en `max_mm` y casi todo el conector pisa tinta."""
    gap_mm = float(np.hypot(*(end - start))) * mm_per_px
    if gap_mm > max_mm:
        return False
    return _coverage(start, end, _ink(mask, mask.shape[0], mask.shape[1])) >= INK_COVERAGE


def _compose(
    portrait: list[np.ndarray],
    caption: list[np.ndarray],
    ink: np.ndarray,
    mm_per_px: float,
    tolerance_mm: float,
) -> list[np.ndarray]:
    simplified = [_simplify(stroke, tolerance_mm, mm_per_px) for stroke in portrait]
    letters = [_simplify(stroke, TOLERANCES_MM[0], mm_per_px) for stroke in caption]
    return [
        *_join(simplified, ink, mm_per_px, JOIN_MAX_MM, require_ink=True),
        *_join(letters, ink, mm_per_px, CAPTION_JOIN_MAX_MM, require_ink=False),
    ]


def _simplify(points: np.ndarray, tolerance_mm: float, mm_per_px: float) -> np.ndarray:
    epsilon = float(tolerance_mm) / max(mm_per_px, 1e-6)
    source = np.asarray(points, dtype=np.float32)
    closed = len(source) >= 3 and float(np.hypot(*(source[0] - source[-1]))) <= 1.5
    smoothed = vectorize_ops.smooth_stroke(source, iterations=2)
    simplified = vectorize_ops.simplify_stroke(smoothed, epsilon)
    if len(simplified) < 2:
        simplified = source
    if closed and float(np.hypot(*(simplified[0] - simplified[-1]))) > 0.5:
        simplified = np.vstack((simplified, simplified[:1]))
    return simplified


def _join(
    strokes: list[np.ndarray],
    ink: np.ndarray,
    mm_per_px: float,
    max_mm: float,
    *,
    require_ink: bool,
) -> list[np.ndarray]:
    usable = [stroke for stroke in strokes if len(stroke) >= 2]
    if not usable:
        return []
    joined = [usable.pop(0)]
    while usable:
        previous = joined[-1]
        best_index = 0
        best_stroke = usable[0]
        best_gap = float("inf")
        for index, stroke in enumerate(usable):
            forward = float(np.hypot(*(stroke[0] - previous[-1]))) * mm_per_px
            backward = float(np.hypot(*(stroke[-1] - previous[-1]))) * mm_per_px
            gap, oriented = (forward, stroke) if forward <= backward else (backward, stroke[::-1])
            if gap < best_gap:
                best_index, best_stroke, best_gap = index, oriented, gap

        usable.pop(best_index)
        covered = (not require_ink) or _coverage(previous[-1], best_stroke[0], ink) >= INK_COVERAGE
        if best_gap <= max_mm and covered:
            joined[-1] = np.vstack((previous, best_stroke))
        else:
            joined.append(best_stroke)
    return joined


def _ink(mask: np.ndarray, height: int, width: int) -> np.ndarray:
    canvas = np.zeros((max(height, mask.shape[0]), max(width, mask.shape[1])), dtype=np.uint8)
    canvas[: mask.shape[0], : mask.shape[1]] = (mask > 0).astype(np.uint8) * 255
    if DILATE_PX > 0:
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (DILATE_PX * 2 + 1, DILATE_PX * 2 + 1)
        )
        canvas = cv2.dilate(canvas, kernel)
    return canvas


def _coverage(start: np.ndarray, end: np.ndarray, ink: np.ndarray) -> float:
    distance = float(np.hypot(*(end - start)))
    steps = max(1, int(distance / INK_SAMPLE_PX))
    height, width = ink.shape[:2]
    hits = 0
    for index in range(steps + 1):
        weight = index / steps
        x = int(round(float(start[0] + (end[0] - start[0]) * weight)))
        y = int(round(float(start[1] + (end[1] - start[1]) * weight)))
        if 0 <= x < width and 0 <= y < height and ink[y, x] > 0:
            hits += 1
    return hits / (steps + 1)


