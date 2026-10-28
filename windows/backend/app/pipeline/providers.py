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
# Catálogo: dice qué parámetros acepta cada modelo. Se consulta una vez.
API_MODELS_URL = "https://openrouter.ai/api/v1/images/models"
DEFAULT_TIMEOUT_S = 25.0
# Todo lo que no sea papel cuenta como tinta. El modelo no siempre dibuja con el
# mismo grosor: con umbral por cuantil, las caras que dibujaba con línea fina se
# partían en guiones. Fijo aguanta ambas.
#
# 180 y no 200: el "papel blanco" que devuelve el modelo es gris 223 con grano, y
# a 200 el grano de las esquinas entraba como tinta (58 manchas falsas medidas en
# una foto real, que el robot dibujaba como una maraña de garabatos). El trazo del
# modelo está en 25 de gris, así que 180 sigue sin perder ni una línea.
INK_THRESHOLD = 180
# Cierre en px para volver a pegar los huecos de un píxel de la línea fina.
GAP_CLOSE_PX = 3
OUTPUT_WIDTH = 768
OUTPUT_HEIGHT = 1024

# Caricatura de pocos trazos. Las reglas de tinta existen por defectos ya vistos
# en papel: tramado, texto de la camiseta y barba inventada. No se sueltan.
# La lista de identidad no es decorativa. Sin ella el modelo entrega a un
# pariente más guapo: le puso barba a quien tenía tres días de vello y le alargó
# el pelo a quien lo tenía corto. Son datos que se comparan en el papel.
FIDELITY_RULES = """FIDELITY RULES, most important:
- The drawing must be recognizable as the exact same person in the photo.
- Keep the same face shape and jaw, the same eye size and the distance between
  the eyes, the same eyebrows, nose and lips.
- Keep their real age. Do not beautify, slim, widen or age the face.
- Keep the same hairstyle and hair length. Never restyle, shorten or lengthen it.
- Keep the real hairline and the real amount of hair. Short, faded or shaved at
  the sides is not the same as bald: draw the hair mass over the whole skull and
  the visible hairline. Never give a receding hairline or an empty scalp that the
  photo does not have.
- Draw facial hair only if it is visible in the photo. Never invent a beard,
  mustache or goatee.
- The eyes stay open with a visible pupil. Never draw them closed or as arcs."""

# Reglas que valen para los cuatro estilos; antes solo las llevaba el prompt
# por defecto. El pelo se perdió una vez por pedir "menos líneas": salió un
# calvo con tres pelos y el visitante no se reconoció.
DRAWING_RULES = """DRAWING RULES:
- Single-weight pure black lines on pure white paper. No gray, no gradient,
  no color.
- NO hatching, NO cross-hatching, NO stippling, NO dots, NO tone, NO shading of
  any kind. Fewer lines is better.
- Hair and facial hair keep their real silhouette and volume, drawn with a few
  long confident strokes. Never leave the head bald or with a few stray hairs.
- Hair, beards and mustaches are an outline with at most three short interior
  strokes, never a filled solid black shape and never hatched or scribbled
  inside. A thin goatee or mustache stays thin: one contour, not a black patch.
- No words, letters, numbers, logos, signatures or watermarks anywhere.
- Plain white background, nothing else in the frame: no border, no vignette.
- Clothing stays blank unless a costume is added below.
- The whole head and shoulders must fit inside the frame.
- An added costume or hat is a few simple outlines, never a detailed drawing,
  and it never covers the face or the eyes."""

RULES = "\n\n" + FIDELITY_RULES + "\n\n" + DRAWING_RULES

CARICATURE_OPENING = """Redraw this photograph as a bold, playful black ink caricature on plain
white paper.

Make the character bigger than life. Pick the two features that already stand
out in the photo, such as a big nose, a round chin, strong eyebrows or full
cheeks, and draw them clearly oversized. Use loose, confident hand-drawn
outlines, a touch imperfect on purpose, with one bold weight instead of many
thin lines.

The exaggeration is only the size of those features. The expression stays the
one in the photo: if the person is not smiling there, the drawing does not
smile either, and the mouth keeps its real shape. The eyes keep their exact
position, size and distance so the person is still recognizable, and nothing is
added that is not already in the photo.

The character can be whimsical, but the paper stays a drawing: black lines on
white, no color, no shading, no scenery, no sky, no clouds and no background of
any kind."""

PROMPT = CARICATURE_OPENING + RULES

# El visitante elige uno. Un id desconocido vuelve a la caricatura.
DEFAULT_STYLE = "caricatura"
STYLE_OPENINGS = {
    "retrato": (
        "Redraw this photograph as a faithful minimal black ink portrait "
        "on plain white paper.\n\n"
        "Do not exaggerate anything: same proportions, same expression and the "
        "same pose as in the photo."
    ),
    "anime": (
        "Redraw this photograph as minimal black ink anime line art "
        "on plain white paper.\n\n"
        "Larger expressive eyes with a visible pupil, a smaller nose and mouth, "
        "and the hair as a few clean locks that keep its real shape. No screentones."
    ),
    "cartoon": (
        "Redraw this photograph as a simple black ink cartoon "
        "on plain white paper.\n\n"
        "Rounder shapes and fewer, bolder outlines, but the expression stays "
        "the one in the photo, the hair keeps its real shape and volume, and the "
        "eyes stay open with a visible pupil."
    ),
}

# Ids que manda la cabina. Texto libre del visitante no entra al prompt.
TRAIT_LINES = {
    "chef": "Dress them as a chef: a plain toque and a simple jacket, few outlines.",
    "medico": "Dress them as a doctor: a plain coat and a simple stethoscope, few outlines.",
    "astronauta": "Dress them as an astronaut: a simple round helmet outline that does not hide the face.",
    "musico": "Dress them as a musician: simple headphones, few outlines, face still clear.",
    "piloto": "Dress them as a pilot: a simple peaked cap, face still clear, few outlines.",
    "bombero": "Dress them as a firefighter: a simple helmet that leaves the face clear, few outlines.",
    "cientifico": "Dress them as a scientist: a plain lab coat, few outlines, face still clear.",
    "artista": "Dress them as an artist: a simple beret, few outlines, face still clear.",
    "sombrero": "Add one simple wide-brim hat.",
    "gorra": "Add one simple baseball cap.",
    "corona": "Add one simple three-point crown.",
    "lentes": "Add one pair of simple round glasses.",
    "mono": "Add one simple bow tie.",
    "flor": "Add one simple five-petal flower beside the ear.",
}

# Qué parte del cuerpo ocupa cada rasgo. Dos rasgos que comparten espacio se
# dibujan uno encima del otro: "bombero" ya trae casco, y sumarle "gorra" son
# dos sombreros sobre la misma cabeza. El filtro se hace también aquí porque el
# pedido puede llegar armado desde fuera; el frontend ya apaga el botón.
TRAIT_SLOTS = {
    "chef": ("head", "body"),
    "medico": ("body",),
    "astronauta": ("head", "body"),
    "musico": ("ears", "body"),
    "piloto": ("head", "body"),
    "bombero": ("head", "body"),
    "cientifico": ("body",),
    "artista": ("head", "body"),
    "sombrero": ("head",),
    "gorra": ("head",),
    "corona": ("head",),
    "lentes": ("eyes",),
    "mono": ("neck",),
    "flor": ("hair",),
}


def resolve_style(style: str | None) -> str:
    """Caricatura si no eligieron, o si el id no existe."""
    if style in STYLE_OPENINGS or style == DEFAULT_STYLE:
        return style or DEFAULT_STYLE
    return DEFAULT_STYLE


def filter_traits(traits: list[str] | None) -> list[str]:
    """Deja un rasgo por espacio, y el disfraz manda sobre el accesorio.

    Sin esto, elegir bombero y gorro le pide al modelo dos sombreros sobre la
    misma cabeza. El disfraz (el que ocupa el cuerpo) se resuelve antes, así que
    sobrevive al gorro aunque llegue después en la lista.
    """
    known = [trait for trait in traits or [] if trait in TRAIT_LINES]
    ordered = sorted(known, key=lambda trait: "body" not in TRAIT_SLOTS.get(trait, ()))
    kept: list[str] = []
    taken: set[str] = set()
    for trait in ordered:
        slots = set(TRAIT_SLOTS.get(trait, ()))
        if slots & taken:
            continue
        taken |= slots
        kept.append(trait)
    return kept


def build_prompt(traits: list[str] | None = None, style: str | None = None) -> str:
    """Estilo elegido más los rasgos conocidos. Ids que no están en el mapa se ignoran."""
    chosen = resolve_style(style)
    opening = CARICATURE_OPENING if chosen == DEFAULT_STYLE else STYLE_OPENINGS[chosen]
    base = opening + RULES
    extras = [TRAIT_LINES[trait] for trait in filter_traits(traits)]
    if not extras:
        return base
    lines = "\n".join(f"- {line}" for line in extras)
    return (
        base.rstrip()
        + "\n\nADD ONLY THESE, in the same simple black line, and change nothing else:\n"
        + lines
        + "\n"
    )


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

_CAPABILITIES: dict[str, dict] | None = None


def _capabilities() -> dict[str, dict]:
    """Parámetros que acepta cada modelo, según el catálogo de OpenRouter.

    Se consulta una vez y se guarda. Sin esto hay que mandar el pedido completo
    y el modelo que no admite un parámetro contesta 400, cobra el intento y se
    pierde la visita. Medido en el catálogo: gpt-image-1-mini solo acepta 1:1,
    3:2, 2:3 y auto; flux.2-klein, mai-image y recraft no aceptan `resolution`.

    Si el catálogo no responde devuelve vacío, y entonces se manda el pedido de
    siempre: es preferible arriesgar un 400 a no dibujar nada.
    """
    global _CAPABILITIES
    if _CAPABILITIES is not None:
        return _CAPABILITIES
    try:
        with urllib.request.urlopen(API_MODELS_URL, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        _CAPABILITIES = {}
        return _CAPABILITIES
    entries = body.get("data") if isinstance(body, dict) else body
    table: dict[str, dict] = {}
    for entry in entries or []:
        model_id = entry.get("id")
        if model_id:
            table[model_id] = entry.get("supported_parameters") or {}
    _CAPABILITIES = table
    return _CAPABILITIES


def _accepts(supported: dict | None, name: str, value: object = None) -> bool:
    """Si el modelo declara el parámetro, y el valor cuando es una lista cerrada."""
    if supported is None:
        return True  # catálogo desconocido: se manda como siempre
    spec = supported.get(name)
    if spec is None:
        return False
    values = spec.get("values")
    return values is None or value is None or value in values


def build_payload(
    model: str,
    supported: dict | None,
    prompt: str,
    reference_url: str,
) -> dict:
    """Pedido a la API con solo los parámetros que ese modelo acepta.

    Así cambiar de modelo es cambiar una variable de entorno y no reescribir el
    pedido: `supported` sale tal cual del catálogo de OpenRouter.
    """
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "input_references": [{"type": "image_url", "image_url": {"url": reference_url}}],
    }
    if _accepts(supported, "resolution", "1K"):
        payload["resolution"] = "1K"
    if _accepts(supported, "aspect_ratio", "3:4"):
        payload["aspect_ratio"] = "3:4"
    if _accepts(supported, "output_format", "png"):
        payload["output_format"] = "png"
    if _accepts(supported, "n", 1):
        payload["n"] = 1
    return payload


def _request_image(
    settings: Settings,
    model: str,
    reference: np.ndarray,
    prompt: str,
) -> tuple[bytes, dict]:
    payload = build_payload(
        model,
        _capabilities().get(model),
        prompt,
        _to_data_url(reference),
    )
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


def mask_from_png(png: bytes, ink_threshold: int = INK_THRESHOLD) -> np.ndarray:
    """PNG del modelo -> máscara de tinta (255 = línea).

    El umbral es fijo y generoso (todo lo que no sea papel cuenta como tinta)
    porque el modelo no siempre dibuja igual: a una cara con gafas y barba le
    pone trazo grueso y negro, y a una cara lisa se le va la mano a líneas
    finas y claras. Con el umbral por cuantil que había antes, esa segunda
    versión se partía en trozos y el robot dibujaba guiones. Medido sobre las
    salidas reales: fijo + cierre de huecos da trazos 25 % más largos que el
    cuantil, y aguanta las líneas claras.

    El cierre de 3 px vuelve a pegar los huecos de un píxel que deja la línea
    fina al binarizarse; sin él el contorno se corta y el ojo sale abierto.
    """
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise SketchProviderError("el modelo devolvió un PNG ilegible")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    mask = (gray <= max(1, min(254, ink_threshold))).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (GAP_CLOSE_PX, GAP_CLOSE_PX))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return _drop_specks(mask, min_area=6)


def _dump_debug(png: bytes, mask: np.ndarray, reference: np.ndarray, meta: dict) -> None:
    """Guarda referencia, PNG del modelo y máscara si `SKETCH_DEBUG_DIR` existe.

    Sirve para reproducir un caso raro (una cara que salió en guiones) sin
    gastar otra llamada a la API. Apagado por defecto: en la expo no se escribe
    nada en disco.
    """
    target = os.environ.get("SKETCH_DEBUG_DIR")
    if not target:
        return
    folder = Path(target)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    model = str(meta.get("model") or "modelo").replace("/", "_")
    cv2.imwrite(str(folder / f"{stamp}_{model}_reference.png"), reference)
    (folder / f"{stamp}_{model}_raw.png").write_bytes(png)
    cv2.imwrite(str(folder / f"{stamp}_{model}_mask.png"), mask)


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
    traits: list[str] | None = None,
    style: str | None = None,
) -> tuple[np.ndarray, dict]:
    """Foto -> máscara de tinta entregada por el proveedor activo."""
    settings = settings or load_settings()
    prompt = build_prompt(traits, style)
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
                png, meta = _request_image(settings, model, reference, prompt)
                mask = mask_from_png(png)
            except SketchProviderError as exc:
                errors.append(str(exc))
                continue
            _dump_debug(png, mask, reference, meta)
            meta["traits"] = [trait for trait in traits or [] if trait in TRAIT_LINES]
            meta["style"] = resolve_style(style)
            meta["reference_sha"] = hashlib.sha256(reference.tobytes()).hexdigest()[:12]
            meta["size"] = f"{reference.shape[1]}x{reference.shape[0]}"
            return mask, meta
    raise SketchProviderError("; ".join(errors) or "sin proveedores")
