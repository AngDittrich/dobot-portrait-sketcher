"""Conversión de imagen a líneas (XDoG) y utilidades de composición."""

from __future__ import annotations

import cv2
import numpy as np


def composite_on_white(image: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Compone BGR + alpha (0..1) sobre fondo blanco."""
    alpha_3 = np.clip(alpha, 0.0, 1.0)[..., None]
    return np.clip(image.astype(np.float32) * alpha_3 + 255.0 * (1.0 - alpha_3), 0, 255).astype(np.uint8)


def to_gray(image: np.ndarray, contrast: float = 0.4) -> np.ndarray:
    """Gris suavizado con contraste local opcional (CLAHE).

    El CLAHE recupera ojos, labios y barba en fotos de webcam con luz plana.
    Se mezcla con el gris original para no amplificar el ruido del fondo.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Suaviza textura de piel sin borrar rasgos.
    gray = cv2.bilateralFilter(gray, d=7, sigmaColor=35, sigmaSpace=7)

    contrast = float(np.clip(contrast, 0.0, 1.0))
    if contrast > 0:
        equalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        gray = cv2.addWeighted(gray, 1.0 - contrast, equalized, contrast, 0)

    return gray.astype(np.float32) / 255.0


def xdog(
    gray: np.ndarray,
    sigma: float = 1.2,
    k: float = 1.6,
    tau: float = 0.98,
    epsilon: float = 0.0,
    phi: float = 40.0,
) -> np.ndarray:
    """Devuelve intensidad de línea en 0..1 (0 = sin línea)."""
    sigma = max(0.1, float(sigma))
    g1 = cv2.GaussianBlur(gray, (0, 0), sigma)
    g2 = cv2.GaussianBlur(gray, (0, 0), sigma * max(1.01, float(k)))
    dog = g1 - float(tau) * g2

    # Normalizar el DoG: sin esto, las zonas planas quedan grises y el
    # resultado parece una foto con sombras en vez de un dibujo de líneas.
    peak = float(np.abs(dog).max())
    if peak > 1e-6:
        dog = dog / peak

    out = 1.0 + np.tanh(float(phi) * (dog - float(epsilon)))
    out = np.clip(out, 0.0, 1.0)
    lines = np.clip(1.0 - out, 0.0, 1.0)
    return lines


def render_lines(lines: np.ndarray) -> np.ndarray:
    """Líneas -> imagen gris con fondo blanco."""
    image = np.clip(255.0 * (1.0 - lines), 0, 255).astype(np.uint8)
    return cv2.medianBlur(image, 3)


def binarize(lines: np.ndarray, threshold: float = 0.20) -> np.ndarray:
    """Líneas -> blanco/negro listo para mostrar (fondo blanco, línea negra).

    Para vectorizar, invertir con ``255 - binarize(...)`` y así obtener la
    máscara con 255 en las líneas.
    """
    mask = (lines >= threshold).astype(np.uint8) * 255
    # Elimina motas de 1-2 px.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return 255 - mask


def pencil_sketch(image: np.ndarray) -> np.ndarray:
    """Fallback clásico de OpenCV, para comparar con XDoG."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, sketch = cv2.pencilSketch(image, sigma_s=50, sigma_r=0.07, shade_factor=0.05)
    return sketch
