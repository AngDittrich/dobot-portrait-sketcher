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
# El 2-opt es O(n^2) por pasada; con muchos trazos se queda colgado.
TWO_OPT_MAX_STROKES = 250


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
    """Intensidad de línea -> máscara binaria con 255 en la línea.

    No se aplica apertura morfológica: con un elemento de 2x2 una línea de
    1 px desaparece (la erosión la borra entera). El ruido se quita
    después con `remove_specks`, que usa el área de cada mancha.
    """
    mask = (np.asarray(lines, dtype=np.float32) >= float(threshold)).astype(np.uint8) * 255
    return mask


def remove_specks(mask: np.ndarray, min_area: int = 12) -> np.ndarray:
    """Quita componentes conectados demasiado pequeños (ruido)."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    cleaned = np.zeros_like(mask)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= min_area:
            cleaned[labels == index] = 255
    return cleaned


def strokes_from_mask(
    mask: np.ndarray,
    min_length_px: float = 10.0,
    close_px: float = 0.0,
) -> list[np.ndarray]:
    """Contorno de cada mancha de tinta, no su esqueleto.

    Adelgazar la máscara convierte un ojo o una ceja en unos píxeles sueltos
    y el filtro de trazos cortos los tira: la cara queda vacía. El contorno
    sigue la forma que ya se ve en el boceto (párpado, nariz, labios, pelo).

    El cierre (`close_px`) une el doble contorno del XDoG (dos paralelas
    con hueco) en una sola mancha antes de buscar contornos.
    """
    binary = (mask > 0).astype(np.uint8)
    if not binary.any():
        return []
    k = int(round(close_px))
    if k > 1:
        kernel = np.ones((k, k), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    strokes: list[np.ndarray] = []
    for contour in contours:
        points = contour.reshape(-1, 2).astype(np.float32)
        if len(points) < 3:
            continue
        if float(np.hypot(*(points[0] - points[-1]))) > 1.5:
            points = np.vstack((points, points[:1]))
        if _polyline_length(points) < min_length_px:
            continue
        strokes.append(points)
    return strokes


def trim_to_ink(mask: np.ndarray, margin_ratio: float = 0.05) -> np.ndarray:
    """Recorta el papel sobrante alrededor de la tinta.

    La IA devuelve un lienzo 3:4 con aire arriba y abajo. Si eso se manda tal
    cual al robot, media hoja queda en blanco y la cara sale chica: el ancho se
    escala a 140 mm, así que el aire se come el dibujo. Se recorta al
    rectángulo de la tinta dejando un margen proporcional a su lado mayor.
    """
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return mask
    height, width = mask.shape[:2]
    top, bottom = int(ys.min()), int(ys.max()) + 1
    left, right = int(xs.min()), int(xs.max()) + 1
    margin = int(round(max(bottom - top, right - left) * max(0.0, margin_ratio)))
    return mask[
        max(0, top - margin) : min(height, bottom + margin),
        max(0, left - margin) : min(width, right + margin),
    ]


def skeletonize(mask: np.ndarray) -> np.ndarray:
    """Adelgaza la máscara de líneas a un esqueleto de 1 px.

    Usa ``cv2.ximgproc.thinning`` (opencv-contrib, ya instalado). Si no
    estuviera disponible cae a un esqueleto por erosión iterativa, que es
    peor (rompe las curvas) pero evita el crash.
    """
    binary = (mask > 0).astype(np.uint8) * 255
    if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning"):
        return cv2.ximgproc.thinning(binary, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    skeleton = np.zeros_like(binary)
    eroded = binary.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while cv2.countNonZero(eroded) > 0:
        opened = cv2.dilate(cv2.erode(eroded, kernel), kernel)
        skeleton = cv2.bitwise_or(skeleton, cv2.subtract(eroded, opened))
        eroded = cv2.erode(eroded, kernel)
    return skeleton


# ---------------------------------------------------------------------------
# 2. Grafo del esqueleto y extracción de polilíneas
# ---------------------------------------------------------------------------


def _cover_piece(pixels: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Recorre todos los píxeles de un tramo con caminos simples.

    Primero se camina desde los extremos (grado 1) y después desde cualquier
    píxel que quede sin visitar, así no se pierde ninguna rama del tramo.
    """
    members = set(pixels)
    visited: set[tuple[int, int]] = set()

    def neighbours(p: tuple[int, int]) -> list[tuple[int, int]]:
        y, x = p
        return [(y + dy, x + dx) for dy, dx in NEIGHBORS_8 if (y + dy, x + dx) in members]

    endpoints = [p for p in pixels if len(neighbours(p)) == 1]
    paths: list[list[tuple[int, int]]] = []
    for start in endpoints + pixels:
        if start in visited:
            continue
        path = [start]
        visited.add(start)
        current = start
        while True:
            following = [q for q in neighbours(current) if q not in visited]
            if not following:
                break
            current = following[0]
            visited.add(current)
            path.append(current)
        paths.append(path)
    return paths


_NEIGHBOUR_KERNEL = np.ones((3, 3), np.float32)
_NEIGHBOUR_KERNEL[1, 1] = 0


def _neighbour_count(binary: np.ndarray) -> np.ndarray:
    return cv2.filter2D(binary.astype(np.float32), -1, _NEIGHBOUR_KERNEL, borderType=cv2.BORDER_CONSTANT)


_RING_8 = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))


def _crossing_number(binary: np.ndarray) -> np.ndarray:
    """Transiciones 0->1 alrededor de cada píxel (>=3 indica bifurcación real).

    A diferencia de contar vecinos, ignora los escalones y esquinas del
    esqueleto de 8 conexiones, que de otro modo parecen bifurcaciones.
    """
    height, width = binary.shape
    padded = np.pad(binary, 1)
    ring = [padded[1 + dy : 1 + dy + height, 1 + dx : 1 + dx + width] for dy, dx in _RING_8]
    transitions = np.zeros((height, width), np.int32)
    for index in range(8):
        transitions += ((ring[index] == 0) & (ring[(index + 1) % 8] == 1)).astype(np.int32)
    return transitions


def _prune_spurs(binary: np.ndarray, spur_length_px: int) -> np.ndarray:
    """Quita las ramas cortas (peldaños del adelgazado) sin tocar el trazo principal.

    Se erosionan los extremos ``spur_length_px`` veces y luego se regeneran
    desde los extremos que quedan, limitado al esqueleto original. Las ramas
    cortas que cuelgan de una bifurcación desaparecen; los arcos largos
    recuperan su longitud.
    """
    if spur_length_px <= 0:
        return binary
    pruned = binary.copy()
    for _ in range(spur_length_px):
        endpoints = (pruned > 0) & (_neighbour_count(pruned) == 1)
        pruned[endpoints] = 0
    for _ in range(spur_length_px):
        endpoints = ((pruned > 0) & (_neighbour_count(pruned) == 1)).astype(np.uint8)
        grow = cv2.dilate(endpoints, np.ones((3, 3), np.uint8)) & binary
        pruned = pruned | grow
    return pruned


def extract_strokes(
    skeleton: np.ndarray,
    min_length_px: float = 6.0,
    spur_length_px: int = 6,
) -> list[np.ndarray]:
    """Convierte el esqueleto en polilíneas (trazos continuos).

    Se podan las ramas cortas, se quitan los píxeles de bifurcación (3 o más
    vecinos), se etiquetan los tramos con ``connectedComponents`` (en C) y cada
    tramo se recorre con ``_cover_piece``. Es lineal en el número de píxeles:
    el grafo anterior en Python tardaba minutos con máscaras densas.
    """
    binary = (skeleton > 0).astype(np.uint8)
    if not binary.any():
        return []

    binary = _prune_spurs(binary, spur_length_px)
    junctions = (binary > 0) & (_crossing_number(binary) >= 3)
    pieces = ((binary > 0) & ~junctions).astype(np.uint8)

    _, labels = cv2.connectedComponents(pieces, connectivity=8)
    ys, xs = np.nonzero(pieces)
    if len(ys) == 0:
        return []
    piece_ids = labels[ys, xs]
    order = np.argsort(piece_ids, kind="stable")
    ys, xs, piece_ids = ys[order], xs[order], piece_ids[order]
    bounds = np.flatnonzero(np.diff(piece_ids)) + 1

    strokes: list[np.ndarray] = []
    for chunk_ys, chunk_xs in zip(np.split(ys, bounds), np.split(xs, bounds)):
        pixels = list(zip(chunk_ys.tolist(), chunk_xs.tolist()))
        for path in _cover_piece(pixels):
            if len(path) < 2:
                continue
            points = np.array([(x, y) for y, x in path], dtype=np.float32)
            if _polyline_length(points) < min_length_px:
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
    approx = cv2.approxPolyDP(contour, float(epsilon_px), False)
    return approx.reshape(-1, 2).astype(np.float32)


def simplify_and_smooth(
    points: np.ndarray, epsilon_px: float = 1.2, iterations: int = 1
) -> np.ndarray:
    """Chaikin primero, RDP despues (el orden importa).

    Chaikin corta la escalera de pixel y deja curva suave; RDP la vuelve
    a rectas largas. Al reves (RDP primero) el temblor sobrevive porque
    RDP conserva los picos del zigzag.
    """
    if iterations <= 0:
        return simplify_stroke(points, epsilon_px)
    return simplify_stroke(smooth_stroke(points, iterations), epsilon_px)


def smooth_stroke(points: np.ndarray, iterations: int = 2) -> np.ndarray:
    """Suaviza la polilínea con Chaikin (corta las esquinas, conserva los extremos)."""
    smoothed = np.asarray(points, dtype=np.float32)
    for _ in range(iterations):
        if len(smoothed) < 3:
            break
        first = 0.75 * smoothed[:-1] + 0.25 * smoothed[1:]
        second = 0.25 * smoothed[:-1] + 0.75 * smoothed[1:]
        middle = np.empty((len(first) * 2, 2), dtype=np.float32)
        middle[0::2] = first
        middle[1::2] = second
        smoothed = np.vstack((smoothed[:1], middle, smoothed[-1:]))
    return smoothed


def bridge_aligned_strokes(
    strokes: list[np.ndarray],
    max_gap_px: float = 12.0,
    max_angle_deg: float = 40.0,
) -> list[np.ndarray]:
    """Une trazos cuyos extremos están cerca **y** en la misma dirección.

    Pegar cualquier par de extremos cercanos (sin mirar la dirección) unía
    el contorno de la cabeza con el cuello y salían arcos raros cruzando la
    cara. Aquí solo se une cuando la línea sigue recta: el ángulo entre la
    dirección de salida del primer trazo y la de entrada del segundo tiene
    que caber en `max_angle_deg`.
    """
    pieces = [np.asarray(s, dtype=np.float32) for s in strokes]
    if max_gap_px <= 0 or len(pieces) < 2:
        return pieces

    limit = math.cos(math.radians(max(0.0, min(180.0, max_angle_deg))))

    def endpoints(points: np.ndarray):
        return ((0, points[0]), (1, points[-1]))

    while len(pieces) > 1:
        # Rejilla con celdas del tamaño del hueco máximo: solo se miran los
        # endpoints vecinos, no todos contra todos.
        grid: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for index, points in enumerate(pieces):
            for end, position in endpoints(points):
                key = (
                    int(math.floor(float(position[0]) / max_gap_px)),
                    int(math.floor(float(position[1]) / max_gap_px)),
                )
                grid.setdefault(key, []).append((index, end))

        candidates: list[tuple[float, int, int, int, int]] = []
        for index, points in enumerate(pieces):
            for end, position in endpoints(points):
                cell_x = int(math.floor(float(position[0]) / max_gap_px))
                cell_y = int(math.floor(float(position[1]) / max_gap_px))
                for offset_x in (-1, 0, 1):
                    for offset_y in (-1, 0, 1):
                        for other_index, other_end in grid.get(
                            (cell_x + offset_x, cell_y + offset_y), ()
                        ):
                            if other_index == index:
                                continue
                            other = pieces[other_index]
                            other_position = other[0] if other_end == 0 else other[-1]
                            distance = float(np.hypot(*(position - other_position)))
                            if distance <= max_gap_px:
                                candidates.append(
                                    (distance, index, end, other_index, other_end)
                                )

        if not candidates:
            break
        candidates.sort(key=lambda item: item[0])

        merged = None
        for _, index, end, other_index, other_end in candidates:
            first = pieces[index]
            second = pieces[other_index]
            if len(first) < 2 or len(second) < 2:
                continue
            # `first` tiene que terminar en `end` y `second` empezar en `other_end`.
            first_oriented = first if end == 1 else first[::-1]
            second_oriented = second if other_end == 0 else second[::-1]
            incoming = first_oriented[-1] - first_oriented[-2]
            outgoing = second_oriented[1] - second_oriented[0]
            norm_in = float(np.linalg.norm(incoming))
            norm_out = float(np.linalg.norm(outgoing))
            if norm_in < 1e-6 or norm_out < 1e-6:
                continue
            cosine = float(np.dot(incoming, outgoing)) / (norm_in * norm_out)
            if cosine >= limit:
                merged = (index, first_oriented, other_index, second_oriented)
                break

        if merged is None:
            break
        index, first_oriented, other_index, second_oriented = merged
        joined = np.vstack((first_oriented, second_oriented))
        pieces = [p for k, p in enumerate(pieces) if k not in (index, other_index)] + [joined]

    return pieces


def strokes_from_skeleton(
    mask: np.ndarray,
    min_length_px: float = 6.0,
    spur_length_px: int = 4,
    bridge_gap_px: float = 12.0,
    bridge_angle_deg: float = 40.0,
) -> list[np.ndarray]:
    """Máscara de tinta -> polilíneas recorriendo el esqueleto una sola vez.

    Es el trazador que necesita una salida de IA. Con `strokes_from_mask` una
    línea de 1 px se recorre como contorno: un solo trazo que sube por un borde
    y vuelve por el otro, o sea una doble línea sobre el papel. El esqueleto la
    deja en un píxel de ancho y se recorre una vez.

    `min_length_px` conviene más bajo que en el contorno: aquí un tramo corto
    suele ser el iris, la comisura o una ceja, no ruido.
    """
    binary = mask if mask.dtype == np.uint8 else np.asarray(mask, dtype=np.uint8)
    if binary.size == 0:
        return []
    if binary.max() <= 1:
        binary = binary * 255

    skeleton = skeletonize(binary)
    if not np.any(skeleton):
        return []

    strokes = extract_strokes(
        skeleton, min_length_px=min_length_px, spur_length_px=spur_length_px
    )
    if not strokes:
        return []
    if bridge_gap_px <= 0 or len(strokes) < 2:
        return strokes
    return bridge_aligned_strokes(
        strokes, max_gap_px=bridge_gap_px, max_angle_deg=bridge_angle_deg
    )


def estimate_seconds(
    strokes: list[np.ndarray],
    width: int,
    target_width_mm: float = 140.0,
    speed_mm_s: float = 80.0,
) -> float:
    """Segundos que tardará el robot (sin rehacer la trayectoria completa)."""
    if not strokes:
        return 0.0
    mm_per_px = float(target_width_mm) / max(1, width)
    draw_mm = sum(_polyline_length(s) for s in strokes) * mm_per_px
    travel_mm = 0.0
    for previous, current in zip(strokes, strokes[1:]):
        travel_mm += float(np.hypot(*(current[0] - previous[-1]))) * mm_per_px
    return draw_mm / max(1.0, speed_mm_s) + travel_mm / max(1.0, speed_mm_s * 1.6)


def prune_to_budget(
    strokes: list[np.ndarray],
    width: int,
    max_seconds: float,
    target_width_mm: float = 140.0,
    speed_mm_s: float = 80.0,
    min_strokes: int = 12,
) -> list[np.ndarray]:
    """Quita los trazos más cortos hasta que el dibujo quepa en el tiempo.

    Es la red de seguridad de la expo: si una foto concreta sale muy
    larga, se recorta el detalle fino antes de dejar al robot dibujando
    dos minutos. Los trazos que se van son los más cortos, que suelen ser
    textura (pelo, barba), no los contornos principales.
    """
    current = list(strokes)
    if max_seconds <= 0 or not current:
        return current
    seconds = estimate_seconds(current, width, target_width_mm, speed_mm_s)
    while seconds > max_seconds and len(current) > min_strokes:
        lengths = sorted(_polyline_length(s) for s in current)
        cutoff = lengths[0]
        kept = [s for s in current if _polyline_length(s) > cutoff]
        if not kept or len(kept) == len(current):
            break
        current = kept
        seconds = estimate_seconds(current, width, target_width_mm, speed_mm_s)
    return current


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

    if len(ordered) <= TWO_OPT_MAX_STROKES:
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


def render_black_strokes(
    strokes: list[np.ndarray],
    width: int,
    height: int,
    thickness: int = 2,
) -> np.ndarray:
    """Dibuja los trazos en negro sobre blanco (tal como saldrán en el papel).

    La vista previa usa esto en vez de la máscara binaria: así se ve el
    dibujo de líneas fino que realmente dibuja el robot, y no los manchas
    gruesas que produce el XDoG antes de adelgazar.
    """
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    for points in strokes:
        if len(points) < 2:
            continue
        polyline = np.round(points).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [polyline], False, (17, 24, 39), int(thickness), cv2.LINE_AA)
    return canvas


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
