"""Utilidades de imagen: data URLs, decodificación y límites de tamaño."""

from __future__ import annotations

import base64
import re

import cv2
import numpy as np

MAX_SIDE = 1600
_DATA_URL = re.compile(r"^data:(?P<mime>[\w/+.-]+);base64,(?P<payload>.+)$", re.DOTALL)


def decode_data_url(data_url: str) -> np.ndarray:
    """Convierte un data URL (base64) en imagen BGR."""
    match = _DATA_URL.match(data_url.strip())
    payload = match.group("payload") if match else data_url.strip()
    try:
        raw = base64.b64decode(payload, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("El data URL no contiene base64 válido") from exc

    buffer = np.frombuffer(raw, np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("No se pudo decodificar la imagen")
    return image


def encode_data_url(image: np.ndarray, extension: str = ".png") -> str:
    """Codifica una imagen como data URL."""
    params = [cv2.IMWRITE_JPEG_QUALITY, 90] if extension.lower() in {".jpg", ".jpeg"} else []
    ok, buffer = cv2.imencode(extension, image, params)
    if not ok:
        raise ValueError("No se pudo codificar la imagen")
    mime = "image/jpeg" if extension.lower() in {".jpg", ".jpeg"} else "image/png"
    return f"data:{mime};base64,{base64.b64encode(buffer).decode('ascii')}"


def fit_max_side(image: np.ndarray, max_side: int = MAX_SIDE) -> np.ndarray:
    """Reduce la imagen para que su lado mayor no pase de `max_side`."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return image
    scale = max_side / longest
    return cv2.resize(
        image, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
    )
