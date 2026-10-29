"""Medidas de hojas estándar.

Sirven para comprobar la hoja enseñada con las esquinas: si lo medido no se
parece a ninguna, lo más probable es que una esquina quedó mal. El tamaño del
retrato sale del marco enseñado (`frame.py`), no de esta lista.
"""

from __future__ import annotations

# nombre: (etiqueta, lado corto mm, lado largo mm). Se comparan en las dos
# orientaciones: la cabina trabaja con la hoja horizontal.
PAPERS: dict[str, tuple[str, float, float]] = {
    "a6": ("A6", 105.0, 148.0),
    "a5": ("A5", 148.0, 210.0),
    "media_carta": ("Media carta", 140.0, 216.0),
    "a4": ("A4", 210.0, 297.0),
    "carta": ("Carta", 216.0, 279.0),
}

DEFAULT = "a5"

# Aire entre el borde de la hoja y el retrato.
MARGIN_MM = 8.0


def known(name: str) -> bool:
    return str(name or "").strip().lower() in PAPERS


def _key(name: str) -> str:
    """Un nombre que no es una hoja conocida cae en la de por defecto."""
    key = str(name or "").strip().lower()
    return key if key in PAPERS else DEFAULT


def size_mm(name: str) -> tuple[float, float]:
    _, corto, largo = PAPERS[_key(name)]
    return corto, largo


def label(name: str) -> str:
    return PAPERS[_key(name)][0]


def draw_width_mm(name: str) -> float:
    """Ancho del retrato sin esquinas enseñadas: el lado corto menos el aire de los dos lados."""
    return size_mm(name)[0] - 2 * MARGIN_MM


def catalog() -> list[dict]:
    """Las medidas que el panel muestra junto a la hoja enseñada."""
    return [
        {"id": name, "label": name_label, "short_mm": corto, "long_mm": largo}
        for name, (name_label, corto, largo) in PAPERS.items()
    ]
