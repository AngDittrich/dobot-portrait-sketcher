"""Compara, sin mover el brazo, la tinta que mandaría el MG400 con la vista previa.

Uso, desde windows/backend:

    .venv\\Scripts\\python.exe tools\\render_robot_path.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline.robot_path import plan_robot_path  # noqa: E402
from app.pipeline.vectorize import strokes_from_centerline  # noqa: E402
from app.robot.client import MG400Client, Segment, Trajectory, _DryLink  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+),")


def sample_portrait() -> tuple[list[np.ndarray], np.ndarray]:
    """Dos ojos y un trazo largo de pelo, para ver la poda y la fidelidad."""
    mask = np.zeros((220, 200), dtype=np.uint8)
    cv2.circle(mask, (70, 90), 14, 255, 2)
    cv2.circle(mask, (130, 90), 14, 255, 2)
    cv2.line(mask, (15, 25), (185, 40), 255, 2)
    strokes = strokes_from_centerline(mask, min_length_px=6, bridge_gap_px=0)
    return strokes, mask


def fidelity(
    strokes: list[np.ndarray],
    width: int,
    height: int,
    target_width_mm: float,
) -> tuple[float, int]:
    """Cobertura de la tinta del robot sobre la vista previa, y píxeles de más."""
    mm_per_px = target_width_mm / max(1, width)
    trajectory = Trajectory(
        segments=[Segment(type="draw", points=stroke.tolist()) for stroke in _to_mm(strokes, mm_per_px)],
        width_mm=target_width_mm,
        height_mm=height * mm_per_px,
    )
    link = _DryLink()
    client = MG400Client(
        link=link,
        z_draw=-10.0,
        z_travel=-2.0,
        origin_x=trajectory.width_mm / 2,
        origin_y=trajectory.height_mm / 2,
        x_sign=1,
        y_sign=1,
        dry_run=True,
        min_step_mm=0.3,
        join_gap_mm=0.0,
        pipeline=1,
    )

    async def _run() -> None:
        async def _progress(_value: float, _segment: Segment) -> None:
            return None

        await client.draw(trajectory, _progress)

    asyncio.run(_run())
    robot = _raster_commands(client.commands, width, height, mm_per_px, -10.0)
    preview = _raster_strokes(strokes, width, height)
    dilated = cv2.dilate(preview, np.ones((3, 3), np.uint8))
    ink = robot > 0
    covered = int(np.count_nonzero(ink & (dilated > 0)))
    total = int(np.count_nonzero(ink))
    outside = int(np.count_nonzero(ink & (dilated == 0)))
    return (covered / total if total else 0.0), outside


def _to_mm(strokes: list[np.ndarray], mm_per_px: float) -> list[np.ndarray]:
    return [np.asarray(stroke, dtype=np.float32) * mm_per_px for stroke in strokes]


def _raster_strokes(strokes: list[np.ndarray], width: int, height: int) -> np.ndarray:
    canvas = np.zeros((height, width), dtype=np.uint8)
    for stroke in strokes:
        if len(stroke) < 2:
            continue
        points = np.round(stroke).astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [points], False, 255, 1, cv2.LINE_8)
    return canvas


def _raster_commands(
    commands: list[str], width: int, height: int, mm_per_px: float, z_draw: float
) -> np.ndarray:
    canvas = np.zeros((height, width), dtype=np.uint8)
    current: tuple[int, int] | None = None
    for command in commands:
        found = MOVL.search(command)
        if found is None or abs(float(found.group(3)) - z_draw) > 0.01:
            current = None
            continue
        point = (
            int(round(float(found.group(1)) / mm_per_px)),
            int(round(float(found.group(2)) / mm_per_px)),
        )
        if current is not None:
            cv2.line(canvas, current, point, 255, 1, cv2.LINE_8)
        current = point
    return canvas


def main() -> None:
    strokes, mask = sample_portrait()
    planned = plan_robot_path(
        strokes,
        mask,
        mask.shape[1],
        mask.shape[0],
        caption_from=len(strokes),
        target_width_mm=40.0,
        max_seconds=240.0,
        face_box=(40.0, 55.0, 120.0, 70.0),
    )
    coverage, outside = fidelity(
        planned["strokes"], mask.shape[1], mask.shape[0], 40.0
    )
    print(f"cobertura {coverage:.1%}, tinta fuera de la vista previa {outside} px")


if __name__ == "__main__":
    main()
