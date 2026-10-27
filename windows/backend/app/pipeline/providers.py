"""Proveedor de líneas del boceto.

El boceto ya no se extrae de los gradientes de la foto: lo genera un modelo de
imagen que entiende qué es una cara. Este módulo es la única puerta de entrada
y devuelve siempre lo mismo, una **máscara de tinta** (255 = línea), para que
el trazador y el robot no sepan de dónde vino.

Proveedores:

- ``openrouter``: modelo remoto de edición de imagen (funciona hoy).
- ``local``: modelo en la PC de la cabina. Todavía no hay uno instalado: los
  que respetan la cara piden 16 GB de VRAM y esta laptop tiene 4.

``SKETCH_PROVIDER`` elige: ``openrouter``, ``local`` o ``auto`` (prueba local y
cae al remoto). Si ninguno responde, ``main.build_sketch`` cae al boceto XDoG
congelado, que no necesita red.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
API_URL = "https://openrouter.ai/api/v1/images"
DEFAULT_TIMEOUT_S = 25.0
# Fracción de píxeles que se quedan como tinta. El modelo devuelve línea negra
# sobre blanco: fijar la cantidad de tinta conserva el trazo fino, mientras que
# un umbral de Otsu se come el pelo y las zonas claras.
INK_FRACTION = 0.05
OUTPUT_WIDTH = 768
OUTPUT_HEIGHT = 1024

# Prompt validado contra la API: con estas reglas el modelo deja de inventar
# barba, respeta el peinado y no dibuja el texto de la camiseta (que llenaba el
# dibujo de trazos basura). Ver spike_gpu/prompt_v2.txt.
PROMPT = """Redraw this photograph as a minimal black ink line drawing on plain white paper,
in the style of a confident pen portrait by a fashion illustrator.

FIDELITY RULES, most important:
- The drawing must be recognizable as the exact same person in the photo.
- Copy their real face: same face shape, same jaw, same eye size and spacing,
  same eyebrows, same nose, same lips.
- Same age, same hairstyle and same hair length as in the photo. Do not restyle,
  lengthen, curl or thicken the hair.
- Draw ONLY the facial hair that is actually visible in the photo. If the person
  has light stubble or no beard, do not add a beard, mustache or goatee.
  Never invent facial hair.
- Do not beautify, slim, age or idealize the face.

DRAWING RULES:
- Single-weight pure black lines on pure white paper. No gray, no gradient,
  no color.
- NO hatching, NO cross-hatching, NO stippling, NO dots, NO tone, NO shading of
  any kind. Fewer lines is better.
- Draw hair and facial hair with a handful of long confident strokes, not
  hundreds of short ones.
- Do not draw anything on the clothing: no text, no letters, no logos, no prints,
  no graphics. Keep the shirt blank.
- Plain white background, nothing else in the frame.
- The whole head and shoulders must fit inside the frame.
"""


class SketchProviderError(RuntimeError):
    """El proveedor no pudo entregar líneas. Quien llama decide el respaldo."""


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    fallback_model: str
    api_key: str
    timeout_s: float


def _read_env_file(path: Path) -> dict[str, str]:
    """Lector mínimo de .env. Se evita una dependencia nueva por esto."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_settings(env_file: Path | None = None) -> Settings:
    file_values = _read_env_file(env_file or (ROOT / ".env"))

    def get(key: str, default: str = "") -> str:
        return os.environ.get(key) or file_values.get(key, default)

    return Settings(
        provider=get("SKETCH_PROVIDER", "auto").strip().lower(),
        model=get("OPENROUTER_SKETCH_MODEL", "google/gemini-nano-banana-2.1"),
        fallback_model=get("OPENROUTER_SKETCH_FALLBACK", "google/gemini-3-pro-image"),
        api_key=get("OPENROUTER_API_KEY", ""),
        timeout_s=float(get("SKETCH_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))),
    )


# ---------------------------------------------------------------------------
# Foto -> referencia que entiende el modelo
# ---------------------------------------------------------------------------


def prepare_reference(
    image: np.ndarray,
    models_dir: Path | None = None,
    width: int = OUTPUT_WIDTH,
    height: int = OUTPUT_HEIGHT,
) -> np.ndarray:
    """Recorta cabeza y hombros en 3:4: el modelo gasta los píxeles en la cara.

    Sin este recorte la foto de la cabina entra apaisada, con gente de fondo, y
    el modelo reparte el detalle entre los curiosos que pasan por detrás.
    """
    height_in, width_in = image.shape[:2]
    cropped = image
    model_path = (models_dir or (ROOT / "models")) / "face_detection_yunet_2023mar.onnx"
    if model_path.exists():
        detector = cv2.FaceDetectorYN.create(
            str(model_path), "", (width_in, height_in), 0.6, 0.3, 5000
        )
        _, faces = detector.detect(image)
        if faces is not None and len(faces):
            face = max(faces, key=lambda f: f[2] * f[3])
            face_x, face_y, face_w, face_h = face[:4]
            center_x = face_x + face_w / 2
            center_y = face_y + face_h / 2
            x0 = int(max(0, center_x - face_w * 2.6 / 2))
            x1 = int(min(width_in, center_x + face_w * 2.6 / 2))
            y0 = int(max(0, center_y - face_h * 3.4 * 0.38))
            y1 = int(min(height_in, center_y + face_h * 3.4 * 0.62))
            if x1 > x0 and y1 > y0:
                cropped = image[y0:y1, x0:x1]

    height_c, width_c = cropped.shape[:2]
    target_ratio = width / height
    if width_c / height_c > target_ratio:
        new_width = int(height_c * target_ratio)
        x0 = (width_c - new_width) // 2
        cropped = cropped[:, x0 : x0 + new_width]
    else:
        new_height = int(width_c / target_ratio)
        y0 = (height_c - new_height) // 2
        cropped = cropped[y0 : y0 + new_height, :]
    return cv2.resize(cropped, (width, height), interpolation=cv2.INTER_AREA)


def _to_data_url(image: np.ndarray) -> str:
    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    if not ok:
        raise SketchProviderError("no se pudo codificar la referencia a JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buffer.tobytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Proveedor remoto
# ---------------------------------------------------------------------------


def _request_image(settings: Settings, model: str, reference: np.ndarray) -> tuple[bytes, dict]:
    payload = {
        "model": model,
        "prompt": PROMPT,
        "input_references": [{"type": "image_url", "image_url": {"url": _to_data_url(reference)}}],
        "resolution": "1K",
        "aspect_ratio": "3:4",
        "output_format": "png",
        "n": 1,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "X-Title": "dobot-portrait-sketcher",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=settings.timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise SketchProviderError(f"{model}: HTTP {exc.code} {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SketchProviderError(f"{model}: sin respuesta ({exc})") from exc

    seconds = time.perf_counter() - started
    images = body.get("data") or []
    if not images or "b64_json" not in images[0]:
        raise SketchProviderError(f"{model}: respuesta sin imagen")
    usage = body.get("usage") or {}
    return base64.b64decode(images[0]["b64_json"]), {
        "provider": "openrouter",
        "model": model,
        "seconds": round(seconds, 2),
        "cost_usd": usage.get("cost"),
    }


# ---------------------------------------------------------------------------
# PNG -> máscara de tinta
# ---------------------------------------------------------------------------


def mask_from_png(png: bytes, ink_fraction: float = INK_FRACTION) -> np.ndarray:
    """PNG del modelo -> máscara de tinta (255 = línea).

    Se queda con la fracción `ink_fraction` más oscura: así una línea de un
    píxel sigue siendo una línea, en vez del sombreado que sí se comería un
    umbral fijo.
    """
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise SketchProviderError("el modelo devolvió un PNG ilegible")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    cutoff = float(np.quantile(gray, max(0.001, min(0.5, ink_fraction))))
    mask = (gray <= cutoff).astype(np.uint8) * 255
    return _drop_specks(mask, min_area=6)


def _drop_specks(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (mask > 0).astype(np.uint8), connectivity=8
    )
    clean = np.zeros_like(mask)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= min_area:
            clean[labels == index] = 255
    return clean


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def available_providers(settings: Settings | None = None) -> dict[str, bool]:
    settings = settings or load_settings()
    return {
        "local": False,  # no hay modelo local instalado; pide la PC de 16 GB
        "openrouter": bool(settings.api_key),
    }


def generate_mask(
    image: np.ndarray,
    settings: Settings | None = None,
    models_dir: Path | None = None,
) -> tuple[np.ndarray, dict]:
    """Foto -> máscara de tinta entregada por el proveedor activo."""
    settings = settings or load_settings()
    providers = available_providers(settings)

    if settings.provider == "auto":
        order = ["local", "openrouter"]
    elif settings.provider in providers:
        order = [settings.provider]
    else:
        raise SketchProviderError(f"SKETCH_PROVIDER desconocido: {settings.provider}")

    rejected = [name for name in order if not providers.get(name)]
    order = [name for name in order if providers.get(name)]
    if not order:
        raise SketchProviderError(
            "ningún proveedor disponible"
            + (f" ({', '.join(rejected)})" if rejected else "")
        )

    reference = prepare_reference(image, models_dir=models_dir)
    errors: list[str] = []
    for name in order:
        if name == "local":
            errors.append("local: no instalado")
            continue
        for model in (settings.model, settings.fallback_model):
            if not model:
                continue
            try:
                png, meta = _request_image(settings, model, reference)
                mask = mask_from_png(png)
            except SketchProviderError as exc:
                errors.append(str(exc))
                continue
            meta["reference_sha"] = hashlib.sha256(reference.tobytes()).hexdigest()[:12]
            meta["size"] = f"{reference.shape[1]}x{reference.shape[0]}"
            return mask, meta
    raise SketchProviderError("; ".join(errors) or "sin proveedores")
