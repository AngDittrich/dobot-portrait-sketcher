"""Motor de boceto con modelo de line art (ONNX).

El XDoG solo (que usabamos antes) convierte la foto en un "dibujo de
niño": pierde el pelo, la barba y el volumen de las formas. Un modelo de
line art entrenado para drawings resuelve eso: devuelve directamente un
dibujo a lapiz con el pelo, la textura de la camisa y las lineas finas
del marco de las gafas.

Modelo: `line-drawings.onnx` (Paint2Sketch / LineRelifer, Apache-2.0),
17 MB, corre en CPU con onnxruntime (~1.7 s en 900x813).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MODEL_NAME = "line-drawings.onnx"
# Umbral por defecto: el modelo devuelve un gris continuo (1 = blanco,
# 0 = linea). Con 0.88 se quedan las lineas finas de la textura.
DEFAULT_THRESHOLD = 0.88
# El modelo exige lados multiplos de 4: si no, rellena por dentro y la
# salida sale con otra altura (813 -> 816). El relleno se hace aqui, con
# repeticion del borde, para que el dibujo quede exacto sobre el recorte.
SIZE_MULTIPLE = 4


class LineArtModel:
    """Wrapper del modelo de line art (una sola sesion de onnxruntime)."""

    def __init__(self, models_dir: Path | str):
        self.models_dir = Path(models_dir)
        self.path = self.models_dir / MODEL_NAME
        self._session: ort.InferenceSession | None = None

    @property
    def available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def _load(self) -> ort.InferenceSession:
        if self._session is None:
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(1, (cv2.getNumberOfCPUs() or 4) - 1)
            self._session = ort.InferenceSession(
                str(self.path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        return self._session

    def art(self, image: np.ndarray) -> np.ndarray:
        """Foto (BGR) -> dibujo en gris (1.0 = blanco de papel, 0 = linea).

        La salida tiene exactamente las medidas de la entrada: el modelo
        redondea hacia arriba a multiplos de 4, asi que aqui se rellena la
        entrada (repitiendo el borde) y se recorta la salida. Sin esto el
        dibujo queda desplazado unos pixeles respecto a la foto.
        """
        session = self._load()
        height, width = image.shape[:2]
        pad_h = (-height) % SIZE_MULTIPLE
        pad_w = (-width) % SIZE_MULTIPLE
        padded = cv2.copyMakeBorder(
            image, 0, pad_h, 0, pad_w, cv2.BORDER_REPLICATE
        )
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB) / 255.0
        tensor = rgb.transpose(2, 0, 1).astype(np.float32)[None]
        output = session.run(None, {"input": tensor})[0]
        art = np.clip(output[0, 0], 0.0, 1.0).astype(np.float32)
        return art[:height, :width]

    def lines(self, image: np.ndarray, threshold: float = DEFAULT_THRESHOLD) -> np.ndarray:
        """Dibujo -> mapa de lineas (1.0 = linea, 0.0 = papel)."""
        art = self.art(image)
        return np.clip((threshold - art) / max(1e-6, threshold), 0.0, 1.0)

    def hysteresis(self, art: np.ndarray, strong: float, weak: float) -> np.ndarray:
        """Umbral de dos niveles -> mascara binaria de lineas (0/255).

        "fuerte" = tinta segura (siempre se queda). "debil" = trazos tenues
        (pelo, barba) que solo se conservan si tocan a una linea fuerte: asi
        desaparece el ruido suelto sin borrar la textura del dibujo.
        """
        strong_mask = (art <= float(strong))
        weak_mask = (art <= float(weak)).astype(np.uint8)
        count, labels = cv2.connectedComponents(weak_mask, connectivity=8)
        if count <= 1:
            return strong_mask.astype(np.uint8) * 255
        keep = np.zeros(count, dtype=bool)
        touching = np.unique(labels[strong_mask])
        keep[touching[touching != 0]] = True
        keep[0] = False
        return (keep[labels] * 255).astype(np.uint8)
