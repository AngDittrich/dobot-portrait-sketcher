"""Face-parsing (BiSeNet) -> bordes de regiones.

En una foto no hay lineas, solo gradientes: el XDoG encuentra micro-sombras
(puntitos, dobles contornos). Este modulo segmenta la cara en regiones
(piel, pelo, labios, ropa...) y traza el borde ENTRE regiones: lineas
cerradas y limpias, estilo dibujo vectorial.

Si el modelo falta o falla, el llamador usa la ruta XDoG de siempre.
"""

from pathlib import Path

import cv2
import numpy as np

MODEL_NAME = "faceparser_sim.onnx"

# Clases CelebAMask-HQ del BiSeNet:
# 0 fondo, 1 piel, 2 nariz, 3 lentes, 4/5 ojos, 6/7 cejas, 8/9 orejas,
# 10 boca, 11/12 labios, 13 pelo, 14 gorra, 15 arete, 16 collar, 17 cuello,
# 18 ropa. Se agrupan para que el borde salga donde importa.
GROUP = {
    0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5, 7: 5,
    8: 6, 9: 6, 10: 7, 11: 7, 12: 7, 13: 8, 14: 8,
    15: 0, 16: 0, 17: 9, 18: 10,
}
HAIR_GROUP = 8

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
_INPUT_SIDE = 512


def group_classes(mask: np.ndarray) -> np.ndarray:
    """Clases 0..18 -> grupos. Pura, testeable sin modelo."""
    table = np.zeros(256, dtype=np.uint8)
    for cls, grp in GROUP.items():
        table[cls] = grp
    return table[np.asarray(mask, dtype=np.uint8)]


def boundaries(grouped: np.ndarray) -> np.ndarray:
    """Borde de 1 px donde cambia la region. Fondo 255, tinta 0.

    Pura, testeable sin modelo.
    """
    g = np.asarray(grouped, dtype=np.int32)
    diff = (
        (np.roll(g, 1, 0) != g)
        | (np.roll(g, -1, 0) != g)
        | (np.roll(g, 1, 1) != g)
        | (np.roll(g, -1, 1) != g)
    )
    ink = np.full(g.shape, 255, dtype=np.uint8)
    ink[diff] = 0
    ink[0, :] = ink[-1, :] = 255
    ink[:, 0] = ink[:, -1] = 255
    return ink


class FaceParser:
    """Sesion perezosa del BiSeNet. Igual patron que U2Net/lineart."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self._session = None

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def _ensure(self):
        if self._session is None:
            import onnxruntime as ort

            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
        return self._session

    def parse(self, bgr: np.ndarray) -> np.ndarray | None:
        """Foto BGR -> mascara de grupos al mismo tamano. None si falla."""
        try:
            h, w = bgr.shape[:2]
            scale = _INPUT_SIDE / max(h, w)
            small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))))
            canvas = np.zeros((_INPUT_SIDE, _INPUT_SIDE, 3), dtype=np.uint8)
            canvas[: small.shape[0], : small.shape[1]] = small
            rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            blob = ((rgb - _MEAN) / _STD).transpose(2, 0, 1)[None].astype(np.float32)
            out = self._ensure().run(None, {"input": blob})[0]
            mask = out[0].argmax(0).astype(np.uint8)
            mask = mask[: small.shape[0], : small.shape[1]]
            mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            return group_classes(mask)
        except Exception:
            return None
