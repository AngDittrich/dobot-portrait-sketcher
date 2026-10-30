"""Archivo de cada visita: la foto, la IA y el vector, fuera de git.

Una carpeta por boceto. El panel de depuración lee esas carpetas; no vuelve
a llamar al modelo.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import cv2
import numpy as np

ARCHIVE_DIR = Path(__file__).resolve().parents[1] / "archive"

# Nombre, título y pie por defecto. El llamador puede afinar el pie.
STEPS: tuple[tuple[str, str, str], ...] = (
    ("01-original.jpg", "Foto original", "La foto tal como llegó de la cabina."),
    (
        "02-referencia.png",
        "Recorte",
        "Lo que se manda al modelo, con el rectángulo de la cara de la foto.",
    ),
    ("03-ia.png", "Modelo", "El dibujo que devolvió el modelo, sin tocar."),
    ("04-tinta.png", "Tinta", "Máscara: lo oscuro cuenta como línea."),
    (
        "05-trazos.png",
        "Trazos",
        "Línea central, antes de recortar por tiempo.",
    ),
    (
        "06-vector.png",
        "Vector",
        "Lo que ve el visitante y dibuja el robot.",
    ),
)

STEP_FILES = {name for name, _, _ in STEPS}
_VISIT = re.compile(r"\d{8}_\d{6}_sk_[0-9a-f]{10}\Z")


def visit_name(sketch_id: str, now: float | None = None) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    return f"{stamp}_{sketch_id}"


def save_visit(
    sketch_id: str,
    images: dict[str, np.ndarray | bytes],
    info: dict,
) -> str:
    """Escribe la carpeta y devuelve su nombre. Lo que no llegó, no se inventa."""
    folder_name = visit_name(sketch_id)
    folder = ARCHIVE_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    notes = info.get("notes") or {}
    written: list[dict[str, str]] = []
    for filename, title, note in STEPS:
        blob = images.get(filename)
        if blob is None:
            continue
        path = folder / filename
        if isinstance(blob, (bytes, bytearray)):
            path.write_bytes(blob)
        elif not cv2.imwrite(str(path), blob):
            continue
        written.append({"file": filename, "title": title, "note": str(notes.get(filename, note))})
    payload = {
        "id": sketch_id,
        "folder": folder_name,
        "created_at": time.time(),
        "model": info.get("model"),
        "ai_seconds": info.get("ai_seconds"),
        "strokes_before": info.get("strokes_before"),
        "strokes_after": info.get("strokes_after"),
        "estimated_seconds": info.get("estimated_seconds"),
        "steps": written,
    }
    (folder / "meta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return folder_name


def list_visits() -> list[dict]:
    """Visitas más recientes primero. Una carpeta ilegible se salta."""
    if not ARCHIVE_DIR.is_dir():
        return []
    visits: list[dict] = []
    for folder in ARCHIVE_DIR.iterdir():
        meta_path = folder / "meta.json"
        if not folder.is_dir() or not meta_path.is_file():
            continue
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data["folder"] = folder.name
            visits.append(data)
    visits.sort(key=lambda item: str(item.get("folder", "")), reverse=True)
    return visits


def image_path(folder: str, filename: str) -> Path | None:
    """Ruta de una etapa, o None si el nombre no es de este archivo."""
    if _VISIT.fullmatch(folder) is None or filename not in STEP_FILES:
        return None
    root = ARCHIVE_DIR.resolve()
    path = (ARCHIVE_DIR / folder / filename).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path
