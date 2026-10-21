"""Landmarks faciales con MediaPipe Face Landmarker (478 puntos).

Se usan para reforzar el contorno de la cara (mandíbula, cejas, ojos,
nariz, labios) porque el XDoG solo no encuentra la mandíbula cuando la
barba o el cuello tienen poco contraste.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

# Reglas validadas a ojo con la foto real del usuario:
# - el óvalo de la cara solo se dibuja por debajo de la frente (y > 0.29),
#   así aparece la mandíbula y no un arco de frente que no existe;
# - la nariz solo desde la punta (y > 0.33), sin el puente.
FACE_OVAL_MIN_Y = 0.29
NOSE_MIN_Y = 0.33
RIGHT_IRIS_CENTER = 468
LEFT_IRIS_CENTER = 473


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

        def draw_set(name: str, min_y: float | None = None) -> None:
            for connection in self._connections.get(name, []):
                start, end = connection.start, connection.end
                if min_y is not None:
                    # La regla está en coordenadas normalizadas (0..1).
                    if landmarks[start][1] / height < min_y or landmarks[end][1] / height < min_y:
                        continue
                p1 = to_px(start)
                p2 = to_px(end)
                cv2.line(canvas, p1, p2, 1.0, int(round(thickness)), cv2.LINE_AA)

        draw_set("oval", FACE_OVAL_MIN_Y)
        draw_set("brows")
        draw_set("eyes")
        draw_set("lips")
        draw_set("nose", NOSE_MIN_Y)

        # Iris: círculo alrededor del centro + pupila.
        for center_index in (RIGHT_IRIS_CENTER, LEFT_IRIS_CENTER):
            if center_index >= len(landmarks):
                continue
            ring = landmarks[center_index : center_index + 5]
            if len(ring) < 4:
                continue
            centre = landmarks[center_index]
            radius = float(np.mean(np.hypot(ring[:, 0] - centre[0], ring[:, 1] - centre[1])))
            pixel_radius = max(2, int(round(radius)))
            center_px = to_px(center_index)
            cv2.circle(canvas, center_px, pixel_radius, 1.0, int(round(thickness)), cv2.LINE_AA)
            cv2.circle(canvas, center_px, max(1, pixel_radius // 3), 1.0, -1, cv2.LINE_AA)

        return canvas
