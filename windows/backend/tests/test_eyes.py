"""Ojos: si el iris sale desplazado (reflejo del lente), no se dibuja."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.landmarks import FaceLandmarks  # noqa: E402


def _landmarks(iris_xy):
    lm = np.zeros((478, 2), dtype=np.float32)
    # Ojo derecho: esquinas exterior/interior + iris centrado entre ambas.
    lm[33] = (100.0, 100.0)
    lm[133] = (140.0, 100.0)
    lm[468] = iris_xy
    for i, dx, dy in ((469, -6, 0), (470, 6, 0), (471, 0, -6), (472, 0, 6)):
        lm[i] = (iris_xy[0] + dx, iris_xy[1] + dy)
    # Referencias que usa draw_lines (linea de ojos / barbilla).
    lm[263] = (200.0, 100.0)
    lm[152] = (150.0, 220.0)
    # Parpados abiertos (alto 16 px): estos casos prueban el iris, no el
    # ojo simplificado.
    lm[159] = (120.0, 92.0)
    lm[145] = (120.0, 108.0)
    lm[386] = (220.0, 92.0)
    lm[374] = (220.0, 108.0)
    return lm


def _eye_ink(landmarks):
    drawer = FaceLandmarks.__new__(FaceLandmarks)
    drawer._connections = {}
    canvas = drawer.draw_lines(landmarks, (300, 300), features=("eyes",))
    return canvas[80:121, 80:161]


def test_centered_iris_draws_pupil():
    ink = _eye_ink(_landmarks((120.0, 100.0)))
    assert int((ink > 0.5).sum()) > 20


def test_shifted_iris_skips_pupil():
    """Iris pegado a la esquina (reflejo): solo parpados, sin mancha."""
    ink = _eye_ink(_landmarks((101.0, 100.0)))
    assert int((ink > 0.5).sum()) == 0


def _small_eye_landmarks():
    lm = np.zeros((478, 2), dtype=np.float32)
    # Ojo derecho chico (alto 2 px) y su espejo izquierdo.
    lm[33] = (100.0, 100.0)
    lm[133] = (114.0, 100.0)
    lm[159] = (107.0, 99.0)
    lm[145] = (107.0, 101.0)
    lm[468] = (107.0, 100.0)
    for i, dx, dy in ((469, -6, 0), (470, 6, 0), (471, 0, -6), (472, 0, 6)):
        lm[i] = (107.0 + dx, 100.0 + dy)
    lm[263] = (200.0, 100.0)
    lm[362] = (186.0, 100.0)
    lm[386] = (193.0, 99.0)
    lm[374] = (193.0, 101.0)
    lm[473] = (193.0, 100.0)
    for i, dx, dy in ((474, -6, 0), (475, 6, 0), (476, 0, -6), (477, 0, 6)):
        lm[i] = (193.0 + dx, 100.0 + dy)
    lm[152] = (150.0, 200.0)
    return lm


def test_small_eyes_draw_flat():
    """Ojo chico: nada fuera de la banda del parpado (sin aros de iris)."""
    drawer = FaceLandmarks.__new__(FaceLandmarks)
    drawer._connections = {}
    canvas = drawer.draw_lines(_small_eye_landmarks(), (300, 300), features=("eyes",))
    band = canvas[97:104, 90:211]
    outside = canvas.copy()
    outside[97:104, 90:211] = 0.0
    assert int((band > 0.5).sum()) > 10
    assert int((outside > 0.5).sum()) == 0


def test_small_eye_boundary():
    """El caso real (ojo ~9 px, cara ~172 px) cae en ojo simplificado."""
    from app.pipeline.landmarks import _small_eyes

    assert _small_eyes(_small_eye_landmarks(), 171.8) is True
    big = _small_eye_landmarks()
    big[145][1] = 115.0
    big[374][1] = 115.0
    assert _small_eyes(big, 171.8) is False


def test_eye_discs_cover_iris_zone():
    """Discos centrados en cada ojo, radio ~mitad del ancho."""
    import cv2
    from app.pipeline.landmarks import _eye_disc_mask

    lm = _small_eye_landmarks()
    mask = _eye_disc_mask((300, 300), lm)
    assert mask[100, 107] > 0.5  # centro del ojo derecho
    assert mask[100, 193] > 0.5  # centro del ojo izquierdo
    assert mask[100, 150] < 0.5  # puente de la nariz, fuera
    assert mask[200, 107] < 0.5  # mejilla, fuera


class _StubLandmarker:
    """Dibuja nada: aísla el estampado final de ojos del resto."""

    def draw_lines(self, landmarks, size, thickness=2.2, features=(), **kwargs):
        import numpy as np

        return np.zeros((size[1], size[0]), dtype=np.float32)

    def oval_indices(self):
        return (10, 152, 234, 454)


def test_small_eyes_stamped_symmetric():
    """Ojo chico: la máscara final trae ambos párpados, parejos."""
    import cv2
    import numpy as np

    from app.pipeline.sketch import lab_portrait_lines

    crop = np.full((300, 300, 3), 255, dtype=np.uint8)
    lm = _small_eye_landmarks()
    lm[:, 0] += 0.0
    lines, ink, meta = lab_portrait_lines(crop, lm, _StubLandmarker())
    right = int((ink[93:108, 96:118] == 255).sum())
    left = int((ink[93:108, 182:204] == 255).sum())
    assert right > 10 and left > 10
    assert max(right, left) / max(1, min(right, left)) < 3.0
