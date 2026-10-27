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
# Párpados para medir el alto del ojo (arriba/abajo de cada lado).
RIGHT_EYE_TOP = 159
RIGHT_EYE_BOTTOM = 145
LEFT_EYE_TOP = 386
LEFT_EYE_BOTTOM = 374
# Ojo chico respecto a la cara: el contorno + iris + pupila se fusionan en
# una mancha. Debajo de esta fracción se dibuja simplificado y simétrico.
# 0.06 cubre ojos de ~9 px en recortes de ~550 px (caso real con lentes).
SMALL_EYE_RATIO = 0.06


def _eye_height(landmarks: np.ndarray, top: int, bottom: int) -> float:
    if max(top, bottom) >= len(landmarks):
        return 0.0
    return abs(float(landmarks[bottom][1]) - float(landmarks[top][1]))


def _small_eyes(landmarks: np.ndarray, face_height: float) -> bool:
    """True si los ojos son chicos para dibujarles iris + pupila."""
    if face_height <= 0 or landmarks is None or len(landmarks) == 0:
        return False
    tallest = max(
        _eye_height(landmarks, RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM),
        _eye_height(landmarks, LEFT_EYE_TOP, LEFT_EYE_BOTTOM),
    )
    return tallest < SMALL_EYE_RATIO * face_height


def _eye_disc_mask(shape: tuple[int, int], landmarks: np.ndarray) -> np.ndarray:
    """Discos sobre cada ojo (1.0 adentro): ahí manda el landmark, no el XDoG."""
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.float32)
    if landmarks is None or len(landmarks) == 0:
        return mask
    for outer, inner in ((RIGHT_EYE_OUTER, 133), (LEFT_EYE_OUTER, 362)):
        if max(outer, inner) >= len(landmarks):
            continue
        cx = float((landmarks[outer][0] + landmarks[inner][0]) / 2.0)
        cy = float((landmarks[outer][1] + landmarks[inner][1]) / 2.0)
        radius = max(2, int(round(0.45 * abs(float(landmarks[inner][0] - landmarks[outer][0])))))
        cv2.circle(mask, (int(round(cx)), int(round(cy))), radius, 1.0, -1, cv2.LINE_AA)
    return mask


def _simple_eyes(canvas: np.ndarray, landmarks: np.ndarray, thickness: float) -> None:
    """Ojo simplificado y simétrico: línea de párpado + punto de pupila."""
    # Mínimo 2 px: la apertura 2x2 del umbral (`_open_mask`) borra las
    # líneas de 1 px, y con el XDoG de cada ojo distinto eso mata un ojo
    # sí y el otro no (el origen real de los ojos "chuecos").
    width = max(2, int(round(thickness)))
    dot = max(1, int(round(thickness / 2)))
    for outer, inner in ((RIGHT_EYE_OUTER, 133), (LEFT_EYE_OUTER, 362)):
        if max(outer, inner) >= len(landmarks):
            continue
        p1 = (int(round(float(landmarks[outer][0]))), int(round(float(landmarks[outer][1]))))
        p2 = (int(round(float(landmarks[inner][0]))), int(round(float(landmarks[inner][1]))))
        cv2.line(canvas, p1, p2, 1.0, int(round(thickness)), cv2.LINE_AA)
        centre = (int(round((p1[0] + p2[0]) / 2)), int(round((p1[1] + p2[1]) / 2)))
        cv2.circle(canvas, centre, dot, 1.0, -1, cv2.LINE_AA)

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

# Abertura de la boca (anillo interior de 20 puntos): la linea donde se
# juntan los labios.
#
# Se usa el anillo INTERIOR y no el exterior (la bermeja) a proposito. El
# exterior de MediaPipe sigue la bermeja real, y con bigote o labios carnos
# esa bermeja es enorme: al dibujarla sale un "pico de pato" muy de
# caricatura. La abertura es siempre el hueco real de la boca, y encima
# encaja con lo que ya dibujo el modelo de line art (que pone el bigote,
# los dientes y el detalle).
LIPS = (
    78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308,
    415, 310, 311, 312, 13, 82, 81, 80, 191,
)

# Borde inferior del labio inferior: la mitad de abajo del anillo exterior.
# Con la abertura de la boca (arriba) y esta curva el boceto lleva las dos
# lineas de una boca a lapiz. Se dibuja abierta, no cerrada: en las bocas
# abiertas (la del modelo de line art ya trae los dientes) cerrarla lo
# convertiria en un aro.
LIPS_LOWER = (61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291)

# Rasgos que se pueden dibujar por separado.
FEATURES = ("jaw", "brows", "eyes", "lips", "nose")


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

    def oval_indices(self) -> list[int]:
        """Índices del anillo del óvalo facial (para la máscara de la cara)."""
        self._ensure()
        seen: dict[int, None] = {}
        for connection in self._connections.get("oval", []):
            seen.setdefault(connection.start)
            seen.setdefault(connection.end)
        return list(seen.keys())

    def draw_lines(
        self,
        landmarks: np.ndarray,
        size: tuple[int, int],
        thickness: float = 2.2,
        features: tuple[str, ...] = FEATURES,
        lips_scale: float = 1.0,
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
        if "jaw" in features:
            for connection in self._connections.get("oval", []):
                start, end = connection.start, connection.end
                if min(float(landmarks[start][1]), float(landmarks[end][1])) < eye_y:
                    continue
                line(to_px(start), to_px(end))

        for name in ("brows", "eyes"):
            if name not in features:
                continue
            if name == "eyes" and _small_eyes(landmarks, face_height):
                continue
            for connection in self._connections.get(name, []):
                line(to_px(connection.start), to_px(connection.end))

        if "nose" in features:
            for start, end in NOSE_SEGMENTS:
                if start < len(landmarks) and end < len(landmarks):
                    line(to_px(start), to_px(end))

        # Labios: la abertura de la boca, como una sola polilínea cerrada.
        if "lips" in features:
            points = np.array(
                [to_px(index) for index in LIPS if index < len(landmarks)],
                dtype=np.float32,
            )
            if len(points) >= 3:
                if lips_scale != 1.0:
                    centre = points.mean(axis=0)
                    points = centre + (points - centre) * lips_scale
                cv2.polylines(
                    canvas,
                    [np.round(points).astype(np.int32)],
                    True,
                    1.0,
                    int(round(thickness)),
                    cv2.LINE_AA,
                )
            # Borde inferior del labio: segunda linea de la boca.
            lower = np.array(
                [to_px(index) for index in LIPS_LOWER if index < len(landmarks)],
                dtype=np.float32,
            )
            if len(lower) >= 2:
                cv2.polylines(
                    canvas,
                    [np.round(lower).astype(np.int32)],
                    False,
                    1.0,
                    int(round(thickness)),
                    cv2.LINE_AA,
                )

        # Iris: círculo alrededor del centro + pupila. Si el centro sale
        # pegado a una esquina del ojo (reflejo del lente, mirada de lado),
        # se omite: el círculo desplazado es lo que deja los ojos "chuecos".
        # Quedan los párpados, que ya se dibujaron arriba.
        if "eyes" in features:
            if _small_eyes(landmarks, face_height):
                _simple_eyes(canvas, landmarks, thickness)
            else:
                for center_index, outer, inner in (
                    (RIGHT_IRIS_CENTER, RIGHT_EYE_OUTER, 133),
                    (LEFT_IRIS_CENTER, LEFT_EYE_OUTER, 362),
                ):
                    if center_index >= len(landmarks):
                        continue
                    ring = landmarks[center_index : center_index + 5]
                    if len(ring) < 4:
                        continue
                    centre = landmarks[center_index]
                    eye_centre = (landmarks[outer] + landmarks[inner]) / 2.0
                    eye_width = float(abs(landmarks[inner][0] - landmarks[outer][0]))
                    if eye_width > 0 and float(np.hypot(*(centre - eye_centre))) > 0.35 * eye_width:
                        continue
                    radius = float(np.mean(np.hypot(ring[:, 0] - centre[0], ring[:, 1] - centre[1])))
                    # Iris un poco menor que el real: con el tamaño completo el ojo
                    # queda de "muñeca" y el boceto parece un dibujo animado.
                    pixel_radius = max(2, int(round(radius * 0.8)))
                    center_px = to_px(center_index)
                    cv2.circle(canvas, center_px, pixel_radius, 1.0, int(round(thickness)), cv2.LINE_AA)
                    cv2.circle(canvas, center_px, max(1, int(round(pixel_radius * 0.4))), 1.0, -1, cv2.LINE_AA)

        return canvas
