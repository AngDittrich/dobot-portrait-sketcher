"""La trayectoria final conserva la cara y coincide con lo que ejecuta el robot."""

import importlib.util
import os
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.caption import _GLYPHS, append_caption  # noqa: E402
from app.pipeline.robot_path import connector_on_ink, plan_robot_path  # noqa: E402
from app.pipeline.vectorize import strokes_from_centerline  # noqa: E402

_TOOL = Path(__file__).parents[1] / "tools" / "render_robot_path.py"
_SPEC = importlib.util.spec_from_file_location("render_robot_path", _TOOL)
assert _SPEC is not None and _SPEC.loader is not None
_RENDER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RENDER)


def test_un_retrato_que_no_cabe_se_conserva() -> None:
    """Ocho segundos no alcanzan. Antes se tiraba el pelo y el aviso seguía alto."""
    mask = np.zeros((220, 200), dtype=np.uint8)
    cv2.circle(mask, (70, 90), 14, 255, 2)
    cv2.circle(mask, (130, 90), 14, 255, 2)
    cv2.line(mask, (10, 20), (190, 30), 255, 3)
    strokes = strokes_from_centerline(mask, min_length_px=6, bridge_gap_px=0)

    planned = plan_robot_path(
        strokes,
        mask,
        200,
        220,
        caption_from=len(strokes),
        target_width_mm=40.0,
        max_seconds=8.0,
        face_box=(40.0, 55.0, 120.0, 70.0),
    )

    centers = [stroke.mean(axis=0) for stroke in planned["strokes"]]
    assert any(center[0] < 100 and 60 < center[1] < 120 for center in centers)
    assert any(center[0] > 100 and 60 < center[1] < 120 for center in centers)
    assert any(center[1] < 45 for center in centers)


def test_la_poda_no_borra_la_mejilla_fuera_de_la_caja() -> None:
    """La caja sale de la foto y el modelo no dibuja la cara en el mismo sitio.

    Una mejilla a la derecha del rectángulo está a la altura de los ojos.
    Borrarla deja el retrato partido, que es lo que se vio en la cabina.
    """
    mask = np.zeros((220, 280), dtype=np.uint8)
    cv2.circle(mask, (100, 100), 14, 255, 2)
    cv2.line(mask, (210, 70), (230, 150), 255, 3)
    cv2.line(mask, (10, 20), (260, 24), 255, 3)
    strokes = strokes_from_centerline(mask, min_length_px=6, bridge_gap_px=0)

    planned = plan_robot_path(
        strokes,
        mask,
        280,
        220,
        caption_from=len(strokes),
        target_width_mm=40.0,
        max_seconds=8.0,
        face_box=(40.0, 55.0, 120.0, 70.0),
    )

    centers = [stroke.mean(axis=0) for stroke in planned["strokes"]]
    assert any(center[0] > 190 for center in centers)
    assert any(center[1] < 45 for center in centers)


def test_el_conector_solo_se_aprueba_sobre_tinta() -> None:
    mask = np.zeros((40, 90), dtype=np.uint8)
    cv2.line(mask, (2, 20), (88, 20), 255, 3)
    start = np.array([20.0, 20.0], dtype=np.float32)
    over_ink = np.array([40.0, 20.0], dtype=np.float32)
    over_paper = np.array([40.0, 5.0], dtype=np.float32)

    assert connector_on_ink(start, over_ink, mask, max_mm=8.0, mm_per_px=0.2)
    assert not connector_on_ink(start, over_paper, mask, max_mm=8.0, mm_per_px=0.2)


def test_reordena_trazos_para_unir_extremos_que_pisan_tinta() -> None:
    """El vecino que viene en la lista puede estar lejos; no debe forzar una levantada."""
    mask = np.zeros((30, 100), dtype=np.uint8)
    cv2.line(mask, (0, 10), (40, 10), 255, 2)
    cv2.line(mask, (80, 10), (95, 10), 255, 2)
    strokes = [
        np.array([[0.0, 10.0], [20.0, 10.0]]),
        np.array([[80.0, 10.0], [95.0, 10.0]]),
        np.array([[20.0, 10.0], [40.0, 10.0]]),
    ]

    planned = plan_robot_path(
        strokes,
        mask,
        100,
        30,
        caption_from=3,
        target_width_mm=100.0,
        max_seconds=150.0,
    )

    assert len(planned["strokes"]) == 2
    assert any(stroke[:, 0].min() == 0 and stroke[:, 0].max() >= 40 for stroke in planned["strokes"])


def test_el_rotulo_conserva_sus_curvas_y_no_se_une() -> None:
    assert _GLYPHS["O"][1][0][0] == _GLYPHS["O"][1][0][-1]

    strokes, height = append_caption([], 900, 1200)
    assert len(strokes) == 20
    # La B comparte el vértice entre sus dos panzas: unirlas no agrega línea.
    planned = plan_robot_path(
        strokes,
        np.zeros((height, 900), dtype=np.uint8),
        900,
        height,
        caption_from=0,
        target_width_mm=90.0,
        max_seconds=150.0,
    )

    assert len(planned["strokes"]) == 19
    closed = [
        stroke
        for stroke in planned["strokes"]
        if np.hypot(*(stroke[0] - stroke[-1])) < 1.5 and len(stroke) >= 12
    ]
    assert closed


def test_lo_que_manda_el_robot_cubre_la_vista_previa() -> None:
    strokes, mask = _RENDER.sample_portrait()
    planned = plan_robot_path(
        strokes,
        mask,
        mask.shape[1],
        mask.shape[0],
        caption_from=len(strokes),
        target_width_mm=40.0,
        max_seconds=150.0,
        face_box=(40.0, 55.0, 120.0, 70.0),
    )
    coverage, outside = _RENDER.fidelity(
        planned["strokes"], mask.shape[1], mask.shape[0], 40.0
    )

    assert coverage >= 0.97
    assert outside == 0
