"""Vectorización del boceto: esqueleto -> polilíneas -> SVG -> trayectoria en mm.

La idea central: el robot NO puede trazar contornos (eso produce doble línea),
necesita el **centro** de cada línea. Por eso el camino es:

    líneas (XDoG) -> binario -> adelgazar (thinning) -> esqueleto de 1 px
        -> polilíneas -> simplificación RDP -> orden de dibujo -> mm

El SVG es solo una vista previa: la fuente de verdad para el robot son los
puntos en milímetros.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np

NEIGHBORS_8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass
class Stroke:
    """Un trazo continuo del dibujo (polilínea en píxeles de la imagen)."""

    points: np.ndarray  # (N, 2) float32 -> (x, y)
    length_px: float = 0.0
    order: int = 0

    @property
    def start(self) -> np.ndarray:
        return self.points[0]

    @property
    def end(self) -> np.ndarray:
        return self.points[-1]


@dataclass
class VectorResult:
    """Resultado completo de la vectorización."""

    strokes: list[Stroke] = field(default_factory=list)
    width: int = 0
    height: int = 0
    mm_per_px: float = 0.0
    stats: dict = field(default_factory=dict)
    segments: list[dict] = field(default_factory=list)

    @property
    def total_length_px(self) -> float:
        return sum(stroke.length_px for stroke in self.strokes)


# ---------------------------------------------------------------------------
# 1. Máscara de líneas y esqueleto
# ---------------------------------------------------------------------------


def lines_to_mask(lines: np.ndarray, threshold: float = 0.20) -> np.ndarray:
    """Intensidad de línea -> máscara binaria con 255 en la línea."""
    mask = (np.asarray(lines, dtype=np.float32) >= float(threshold)).astype(np.uint8) * 255
    # Motas de 1-2 px: se limpian con apertura, pero cuidado de no borrar
    # rasgos pequeños (ojos). Se usa una apertura laxa de 2x2.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return mask


def remove_specks(mask: np.ndarray, min_area: int = 12) -> np.ndarray:
    """Quita componentes conectados demasiado pequeños (ruido)."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    cleaned = np.zeros_like(mask)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= min_area:
            cleaned[labels == index] = 255
    return cleaned


def skeletonize(mask: np.ndarray) -> np.ndarray:
    """Adelgaza la máscara de líneas a un esqueleto de 1 px.

    Usa ``cv2.ximgproc.thinning`` (opencv-contrib, ya instalado). Si no
    estuviera disponible cae a un esqueleto por erosión iterativa, que es
    peor (rompe las curvas) pero evita el crash.
    """
    binary = (mask > 0).astype(np.uint8) * 255
    if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning"):
        return cv2.ximgproc.thinning(binary, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = binary.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while True:
        eroded = cv2.erode(skeleton, kernel)
        temp = cv2.dilate(eroded, kernel)
        opened = skeleton - temp
        skeleton = cv2.subtract(skeleton, opened)
        if cv2.countNonZero(skeleton) == 0:
            break
    return skeleton


# ---------------------------------------------------------------------------
# 2. Grafo del esqueleto y extracción de polilíneas
# ---------------------------------------------------------------------------


def _build_adjacency(skeleton: np.ndarray) -> dict[tuple[int, int], set[tuple[int, int]]]:
    ys, xs = np.nonzero(skeleton)
    pixels = set(zip(ys.tolist(), xs.tolist()))
    adjacency: dict[tuple[int, int], set[tuple[int, int]]] = {}
    for y, x in pixels:
        neighbours = set()
        for dy, dx in NEIGHBORS_8:
            candidate = (y + dy, x + dx)
            if candidate in pixels:
                neighbours.add(candidate)
        adjacency[(y, x)] = neighbours
    return adjacency


def _edge(a: tuple[int, int], b: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    return (a, b) if a <= b else (b, a)


def _walk(adjacency, used, nodes, start, first):
    """Camina desde `start` por `first` hasta llegar a otro nodo o al final."""
    path = [start]
    previous, current = start, first
    while True:
        edge = _edge(previous, current)
        if edge in used:
            break
        used.add(edge)
        path.append(current)
        if current in nodes:
            break
        candidates = [n for n in adjacency[current] if _edge(current, n) not in used]
        if not candidates:
            break
        previous, current = current, candidates[0]
    return path


def extract_strokes(
    skeleton: np.ndarray,
    min_length_px: float = 6.0,
    spur_length_px: float = 14.0,
) -> list[np.ndarray]:
    """Convierte el esqueleto en polilíneas (ramas entre nodos).

    Los nodos son los extremos (grado 1) y las bifurcaciones (grado >= 3).
    Las ramas muy cortas que cuelgan de una bifurcación se podan porque
    son ruido del adelgazado.
    """
    adjacency = _build_adjacency(skeleton)
    if not adjacency:
        return []

    nodes = {pixel for pixel, neighbours in adjacency.items() if len(neighbours) != 2}
    used: set = set()
    paths: list[list[tuple[int, int]]] = []

    # Desde cada nodo hacia cada vecino todavía sin usar.
    for node in nodes:
        for neighbour in adjacency[node]:
            if _edge(node, neighbour) in used:
                continue
            path = _walk(adjacency, used, nodes, node, neighbour)
            if len(path) > 1:
                paths.append(path)

    # Bucles cerrados sin nodos (grado 2 en todo el contorno).
    for pixel in adjacency:
        if all(_edge(pixel, n) in used for n in adjacency[pixel]):
            continue
        path = _walk(adjacency, used, nodes, pixel, next(iter(adjacency[pixel])))
        if len(path) > 1:
            paths.append(path)

    strokes: list[np.ndarray] = []
    for path in paths:
        points = np.array([(x, y) for y, x in path], dtype=np.float32)
        length = _polyline_length(points)
        if length < min_length_px:
            continue
        strokes.append(points)
    return strokes


def _polyline_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    deltas = np.diff(points, axis=0)
    return float(np.sum(np.hypot(deltas[:, 0], deltas[:, 1])))


# ---------------------------------------------------------------------------
# 3. Simplificación (RDP) y orden de dibujo
# ---------------------------------------------------------------------------


def simplify_stroke(points: np.ndarray, epsilon_px: float = 0.8) -> np.ndarray:
    """Simplifica la polilínea con Ramer-Douglas-Peucker (OpenCV)."""
    if len(points) < 3 or epsilon_px <= 0:
        return points
    contour = points.reshape(-1, 1, 2).astype(np.float32)
    approx = cv2.approxPolyDP(contour, float(epsilon_px), True)
    return approx.reshape(-1, 2).astype(np.float32)


def order_strokes(strokes: list[np.ndarray], start: tuple[float, float] | None = None):
    """Ordena los trazos minimizando los viajes con el lápiz levantado.

    Vecino más cercano (eligiendo orientación) + mejora 2-opt. Al invertir
    un tramo del tour se invierte también cada trazo, de modo que las
    conexiones internas conservan su longitud y solo cambian los dos bordes.
    """
    if not strokes:
        return []

    remaining = list(range(len(strokes)))
    current = np.array(start, dtype=np.float32) if start is not None else strokes[0][0]
    ordered: list[tuple[int, bool]] = []  # (índice, invertido)

    while remaining:
        best_index = 0
        best_reverse = False
        best_distance = math.inf
        for position, index in enumerate(remaining):
            points = strokes[index]
            d_forward = float(np.hypot(*(points[0] - current)))
            d_backward = float(np.hypot(*(points[-1] - current)))
            if d_forward <= d_backward:
                distance, reverse = d_forward, False
            else:
                distance, reverse = d_backward, True
            if distance < best_distance:
                best_distance = distance
                best_index = position
                best_reverse = reverse
        index = remaining.pop(best_index)
        ordered.append((index, best_reverse))
        points = strokes[index]
        current = points[-1] if best_reverse else points[0]

    ordered = _two_opt(ordered, strokes)
    return [(strokes[index][::-1] if reverse else strokes[index], index) for index, reverse in ordered]


def _two_opt(ordered, strokes, max_passes: int = 12):
    """2-opt con inversión: revierte un tramo del tour y sus trazos."""
    if len(ordered) < 4:
        return ordered

    def entry(item):
        index, reverse = item
        points = strokes[index]
        return points[-1] if reverse else points[0]

    def exit_(item):
        index, reverse = item
        points = strokes[index]
        return points[0] if reverse else points[-1]

    def distance(a, b) -> float:
        return float(np.hypot(*(np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32))))

    tour = list(ordered)
    n = len(tour)
    for _ in range(max_passes):
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                previous = tour[i - 1] if i > 0 else None
                following = tour[j + 1] if j < n - 1 else None

                delta = 0.0
                if previous is not None:
                    # Tras invertir, el primero del tramo es tour[j] invertido.
                    delta += distance(exit_(previous), exit_(tour[j]))
                    delta -= distance(exit_(previous), entry(tour[i]))
                if following is not None:
                    # El último del tramo invertido es tour[i] invertido.
                    delta += distance(entry(tour[i]), entry(following))
                    delta -= distance(exit_(tour[j]), entry(following))
                if delta < -1e-6:
                    segment = [(index, not reverse) for index, reverse in reversed(tour[i : j + 1])]
                    tour[i : j + 1] = segment
                    improved = True
        if not improved:
            break
    return tour


# ---------------------------------------------------------------------------
# 4. SVG y trayectoria en milímetros
# ---------------------------------------------------------------------------


def strokes_to_svg(
    strokes: list[np.ndarray],
    width: int,
    height: int,
    ordered_colors: bool = False,
    stroke_width: float = 1.2,
) -> str:
    """Genera el SVG del dibujo (vista previa)."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    total = max(1, len(strokes))
    for index, points in enumerate(strokes):
        coordinates = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        if ordered_colors:
            hue = (index / total) * 300
            color = f"hsl({hue:.0f} 85% 35%)"
            parts.append(
                f'<polyline points="{coordinates}" fill="none" stroke="{color}" '
                f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        else:
            parts.append(
                f'<polyline points="{coordinates}" fill="none" stroke="#111827" '
                f'stroke-width="{stroke_width}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


def to_mm(points: np.ndarray, mm_per_px: float) -> np.ndarray:
    """Píxeles -> milímetros (origen arriba-izquierda, Y hacia abajo)."""
    return np.asarray(points, dtype=np.float32) * float(mm_per_px)


def resample_polyline(points: np.ndarray, spacing: float) -> np.ndarray:
    """Re-muestrea la polilínea con paso constante (en la misma unidad)."""
    if len(points) < 2 or spacing <= 0:
        return points
    deltas = np.diff(points, axis=0)
    lengths = np.hypot(deltas[:, 0], deltas[:, 1])
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    total = float(cumulative[-1])
    if total <= 0:
        return points
    count = max(1, int(round(total / spacing)))
    targets = np.linspace(0.0, total, count + 1)
    xs = np.interp(targets, cumulative, points[:, 0])
    ys = np.interp(targets, cumulative, points[:, 1])
    return np.stack((xs, ys), axis=1).astype(np.float32)


def build_trajectory(
    strokes: list[np.ndarray],
    width: int,
    height: int,
    target_width_mm: float = 140.0,
    spacing_mm: float = 1.5,
    speed_mm_s: float = 80.0,
) -> VectorResult:
    """Convierte los trazos ordenados en una trayectoria en milímetros.

    Devuelve los trazos en mm, los segmentos (dibujar / viajar) y métricas
    de tiempo estimado para el robot.
    """
    mm_per_px = float(target_width_mm) / max(1, width)
    result = VectorResult(width=width, height=height, mm_per_px=mm_per_px)

    for order, points in enumerate(strokes):
        result.strokes.append(
            Stroke(points=points, length_px=_polyline_length(points), order=order)
        )

    draw_length_mm = 0.0
    travel_length_mm = 0.0
    segments: list[dict] = []
    current: np.ndarray | None = None

    for stroke in result.strokes:
        mm_points = to_mm(stroke.points, mm_per_px)
        path = resample_polyline(mm_points, spacing_mm)
        length_mm = _polyline_length(mm_points)
        draw_length_mm += length_mm
        segments.append({"type": "draw", "points": path.tolist()})
        if current is not None:
            travel = float(np.hypot(*(mm_points[0] - current)))
            travel_length_mm += travel
            segments.append(
                {
                    "type": "travel",
                    "points": [current.tolist(), mm_points[0].tolist()],
                }
            )
        current = mm_points[-1]

    draw_seconds = draw_length_mm / max(1.0, speed_mm_s)
    travel_seconds = travel_length_mm / max(1.0, speed_mm_s * 1.6)
    result.stats = {
        "strokes": len(result.strokes),
        "draw_length_mm": round(draw_length_mm, 1),
        "travel_length_mm": round(travel_length_mm, 1),
        "total_length_mm": round(draw_length_mm + travel_length_mm, 1),
        "mm_per_px": round(mm_per_px, 4),
        "target_width_mm": target_width_mm,
        "speed_mm_s": speed_mm_s,
        "est_draw_seconds": round(draw_seconds, 1),
        "est_total_seconds": round(draw_seconds + travel_seconds, 1),
    }
    result.segments = segments
    return result


# ---------------------------------------------------------------------------
# 5. Render para verificación visual
# ---------------------------------------------------------------------------


def render_strokes(
    strokes: list[np.ndarray],
    width: int,
    height: int,
    labels: bool = True,
) -> np.ndarray:
    """Dibuja los trazos con color por orden (verificación visual)."""
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    total = max(1, len(strokes))
    for index, points in enumerate(strokes):
        hue = int((index / total) * 179)
        color = cv2.cvtColor(np.uint8([[[hue, 255, 190]]]), cv2.COLOR_HSV2BGR)[0][0].tolist()
        polyline = np.round(points).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [polyline], False, color, 1, cv2.LINE_AA)
        if labels and len(points):
            origin = tuple(np.round(points[0]).astype(int))
            cv2.putText(
                canvas, str(index + 1), origin, cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA
            )
    return canvas
