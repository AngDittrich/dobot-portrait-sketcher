"""Landmarks faciales con MediaPipe Face Landmarker (478 puntos).

Se usan para reforzar el contorno de la cara (mandíbula, cejas, ojos,
nariz, labios) porque el XDoG solo no encuentra la mandíbula cuando la
barba o el cuello tienen poco contraste.

Las reglas son relativas a la cara (línea de los ojos, boca, barbilla), no a
la imagen: el recorte puede traer pelo por encima y eso no debe cambiar lo
que se dibuja.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# Landmarks de referencia.
CHIN = 152
FOREHEAD = 10
RIGHT_EYE_OUTER = 33
LEFT_EYE_OUTER = 263
UPPER_LIP = 13
LOWER_LIP = 14
RIGHT_IRIS_CENTER = 468
LEFT_IRIS_CENTER = 473

# La nariz se dibuja a mano: el juego de conexiones de MediaPipe cierra un
# aro alrededor de la nariz y eso parece un hocico. Con estos segmentos sale
# la punta, las alas y los dos orificios, como en un boceto a lápiz.
NOSE_SEGMENTS = (
    (98, 97),  # ala derecha
    (97, 2),  # base de la nariz
    (2, 326),  # base de la nariz
    (326, 327),  # ala izquierda
    (4, 1),  # punta -> base
    (1, 19),  # orificio derecho
    (19, 94),
    (327, 294),  # orificio izquierdo
    (294, 278),
)


class FaceLandmarks:
    """Envoltura mínima del Face Landmarker de MediaPipe (tarea .task)."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self._landmarker = None
        self._connections: dict[str, list] = {}

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def _ensure(self):
        if self._landmarker is None:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            base = mp_python.BaseOptions(model_asset_path=str(self.model_path))
            options = vision.FaceLandmarkerOptions(
                base_options=base,
                num_faces=1,
                running_mode=vision.RunningMode.IMAGE,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._landmarker = vision.FaceLandmarker.create_from_options(options)

            connections = vision.FaceLandmarksConnections
            self._connections = {
                "oval": list(connections.FACE_LANDMARKS_FACE_OVAL),
                "brows": list(connections.FACE_LANDMARKS_LEFT_EYEBROW)
                + list(connections.FACE_LANDMARKS_RIGHT_EYEBROW),
                "eyes": list(connections.FACE_LANDMARKS_LEFT_EYE)
                + list(connections.FACE_LANDMARKS_RIGHT_EYE),
                "lips": list(connections.FACE_LANDMARKS_LIPS),
                "nose": list(connections.FACE_LANDMARKS_NOSE),
            }
        return self._landmarker

    def detect(self, image: np.ndarray) -> np.ndarray | None:
        """Devuelve (478, 2) normalizado (0..1) o None si no hay cara."""
        if not self.available:
            return None
        import mediapipe as mp

        landmarker = self._ensure()
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        if not result.face_landmarks:
            return None
        points = result.face_landmarks[0]
        return np.array([(p.x, p.y) for p in points], dtype=np.float32)

    def draw_lines(
        self,
        landmarks: np.ndarray,
        size: tuple[int, int],
        thickness: float = 2.2,
    ) -> np.ndarray:
        """Dibuja los rasgos como mapa de líneas (1.0 = línea, 0.0 = vacío).

        `landmarks` llega ya en píxeles del lienzo `size` (ancho, alto).
        """
        width, height = size
        canvas = np.zeros((height, width), dtype=np.float32)
        if landmarks is None or len(landmarks) == 0:
            return canvas

        def to_px(index: int) -> tuple[int, int]:
            x, y = landmarks[index]
            return int(round(float(x))), int(round(float(y)))

        def line(p1: tuple[int, int], p2: tuple[int, int]) -> None:
            cv2.line(canvas, p1, p2, 1.0, int(round(thickness)), cv2.LINE_AA)

        # Referencia de la cara (todo relativo a ella, no a la imagen).
        eye_y = 0.5 * (float(landmarks[RIGHT_EYE_OUTER][1]) + float(landmarks[LEFT_EYE_OUTER][1]))
        chin_y = float(landmarks[CHIN][1])
        face_height = max(1.0, chin_y - eye_y)

        # Óvalo de la cara: solo la mandíbula (por debajo de la línea de los
        # ojos). Con la frente sale una cabeza de "huevo" calvo.
        for connection in self._connections.get("oval", []):
            start, end = connection.start, connection.end
            if min(float(landmarks[start][1]), float(landmarks[end][1])) < eye_y:
                continue
            line(to_px(start), to_px(end))

        for name in ("brows", "eyes", "lips"):
            for connection in self._connections.get(name, []):
                line(to_px(connection.start), to_px(connection.end))

        for start, end in NOSE_SEGMENTS:
            if start < len(landmarks) and end < len(landmarks):
                line(to_px(start), to_px(end))

        # Iris: círculo alrededor del centro + pupila.
        for center_index in (RIGHT_IRIS_CENTER, LEFT_IRIS_CENTER):
            if center_index >= len(landmarks):
                continue
            ring = landmarks[center_index : center_index + 5]
            if len(ring) < 4:
                continue
            centre = landmarks[center_index]
            radius = float(np.mean(np.hypot(ring[:, 0] - centre[0], ring[:, 1] - centre[1])))
            # Iris un poco menor que el real: con el tamaño completo el ojo
            # queda de "muñeca" y el boceto parece un dibujo animado.
            pixel_radius = max(2, int(round(radius * 0.8)))
            center_px = to_px(center_index)
            cv2.circle(canvas, center_px, pixel_radius, 1.0, int(round(thickness)), cv2.LINE_AA)
            cv2.circle(canvas, center_px, max(1, int(round(pixel_radius * 0.4))), 1.0, -1, cv2.LINE_AA)

        return canvas
