"""Detección y segmentación de rostro para el laboratorio."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


class FaceDetector:
    """Detector YuNet de OpenCV (bbox + 5 landmarks)."""

    def __init__(self, model_path: Path) -> None:
        self.model_path = str(model_path)
        self._detector: cv2.FaceDetectorYN | None = None

    @property
    def available(self) -> bool:
        return Path(self.model_path).exists()

    def _ensure(self) -> cv2.FaceDetectorYN:
        if self._detector is None:
            self._detector = cv2.FaceDetectorYN.create(
                self.model_path, "", (320, 320), score_threshold=0.6, nms_threshold=0.3, top_k=5000
            )
        return self._detector

    def detect(self, image: np.ndarray) -> dict | None:
        if not self.available:
            return None
        height, width = image.shape[:2]
        detector = self._ensure()
        detector.setInputSize((width, height))
        _, faces = detector.detect(image)
        if faces is None or len(faces) == 0:
            return None

        face = max(faces, key=lambda item: float(item[2] * item[3]))
        x, y, w, h = (float(v) for v in face[:4])
        landmarks = face[4:14].reshape(5, 2).astype(float)
        return {
            "bbox": [x, y, w, h],
            "score": float(face[14]),
            "landmarks": landmarks.round(1).tolist(),
        }


class FaceParser:
    """BiSeNet face parsing (19 clases de CelebAMask-HQ) en ONNX."""

    # 0 background, 1 skin, 2 l_brow, 3 r_brow, 4 l_eye, 5 r_eye,
    # 6 eye_g, 7 l_ear, 8 r_ear, 9 ear_r, 10 nose, 11 mouth, 12 u_lip,
    # 13 l_lip, 14 neck, 15 neck_l, 16 cloth, 17 hair, 18 hat
    KEEP_CLASSES = {1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 17}

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path)
        self._session: ort.InferenceSession | None = None
        self._input_name = ""
        self._output_names: list[str] = []
        self._mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self._std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def _ensure(self) -> ort.InferenceSession:
        if self._session is None:
            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [output.name for output in self._session.get_outputs()]
        return self._session

    def predict(self, image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        session = self._ensure()
        height, width = image.shape[:2]

        resized = cv2.resize(image, (512, 512), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = ((rgb - self._mean) / self._std).transpose(2, 0, 1)[None].astype(np.float32)
        output = session.run(self._output_names, {self._input_name: tensor})[0]

        parsing = output[0].argmax(0).astype(np.uint8)
        parsing = cv2.resize(parsing, (width, height), interpolation=cv2.INTER_NEAREST)
        mask = np.isin(parsing, list(self.KEEP_CLASSES)).astype(np.uint8) * 255
        return clean_mask(mask), parsing


class Modnet:
    """MODNet photographic portrait matting en ONNX."""

    def __init__(self, model_path: Path, input_size: int = 512) -> None:
        self.model_path = Path(model_path)
        self.input_size = input_size
        self._session: ort.InferenceSession | None = None
        self._input_name = ""
        self._output_names: list[str] = []

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def _ensure(self) -> ort.InferenceSession:
        if self._session is None:
            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
            self._output_names = [output.name for output in self._session.get_outputs()]
        return self._session

    def predict(self, image: np.ndarray) -> np.ndarray:
        session = self._ensure()
        height, width = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        if width >= height:
            new_height = self.input_size
            new_width = int(width / height * self.input_size)
        else:
            new_width = self.input_size
            new_height = int(height / width * self.input_size)
        new_height -= new_height % 32
        new_width -= new_width % 32

        resized = cv2.resize(rgb, (new_width, new_height), interpolation=cv2.INTER_AREA)
        tensor = resized.astype(np.float32) / 255.0
        tensor = ((tensor - 0.5) / 0.5).transpose(2, 0, 1)[None]
        matte = session.run(self._output_names, {self._input_name: tensor})[0][0, 0]
        matte = cv2.resize(matte, (width, height), interpolation=cv2.INTER_AREA)
        return np.clip(matte, 0.0, 1.0)


class U2NetHuman:
    """U2Net human segmentation (baseline de persona completa)."""

    def __init__(self, model_path: Path, input_size: int = 320) -> None:
        self.model_path = Path(model_path)
        self.input_size = input_size
        self._session: ort.InferenceSession | None = None
        self._input_name = ""
        self._mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        self._std = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def _ensure(self) -> ort.InferenceSession:
        if self._session is None:
            self._session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
            self._input_name = self._session.get_inputs()[0].name
        return self._session

    def predict(self, image: np.ndarray) -> np.ndarray:
        session = self._ensure()
        height, width = image.shape[:2]
        resized = cv2.resize(image, (self.input_size, self.input_size), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = ((rgb - self._mean) / self._std).transpose(2, 0, 1)[None].astype(np.float32)
        output = session.run(None, {self._input_name: tensor})[0][0, 0]
        output = output - output.min()
        output = output / (output.max() + 1e-8)
        return cv2.resize(output, (width, height), interpolation=cv2.INTER_LINEAR)


def clean_mask(mask: np.ndarray) -> np.ndarray:
    """Cierra huecos pequeños y conserva el componente principal."""
    kernel = np.ones((5, 5), np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(closed)
    if contours:
        cv2.drawContours(filled, contours, -1, 255, thickness=cv2.FILLED)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(filled, connectivity=8)
    if count <= 1:
        return filled
    largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return np.where(labels == largest, 255, 0).astype(np.uint8)
