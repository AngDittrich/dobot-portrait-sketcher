"""Interfaz comun del quitado de fondo.

Fase 1 usa solo OpenCV (`bg_opencv`). Fase 2 podra anadir `bg_onnx`
con la misma firma sin tocar server ni UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class BgResult:
    mask: np.ndarray  # (H, W) uint8, 255 = persona
    bbox: tuple[int, int, int, int]  # x, y, w, h en pixeles originales
    timings_ms: dict = field(default_factory=dict)
    face_found: bool = False


def largest_component(mask: np.ndarray) -> np.ndarray:
    """Queda el componente del sujeto principal (el que cubre el centro).

    Si el centro es fondo, cae al componente mas grande.
    Asi se elimina gente/objetos en los bordes del encuadre.
    """
    import cv2

    binary = (mask > 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if count <= 1:
        return mask
    h, w = binary.shape
    center_label = int(labels[h // 2, w // 2])
    if center_label > 0:
        keep = center_label
    else:
        keep = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    return (labels == keep).astype(np.uint8) * 255


def bbox_of(mask: np.ndarray) -> tuple[int, int, int, int]:
    import cv2

    ys, xs = np.nonzero(mask > 0)
    if len(xs) == 0:
        h, w = mask.shape[:2]
        return (0, 0, w, h)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)
