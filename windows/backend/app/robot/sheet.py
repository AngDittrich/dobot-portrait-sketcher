"""Hojas estándar y la caja que el brazo alcanza.

Medido en la cabina: de frente al fondo hay 240 mm útiles (de 199 mm, donde
acaba el codo, a 439 mm, el radio) y a lo ancho 440 mm. La hoja va
**horizontal**: el lado largo de izquierda a derecha y el corto de frente al
fondo. Así A4 entra (210 mm de fondo); con el lado largo de frente al fondo
no entraría, porque 297 mm no caben en 240.

Las esquinas enseñadas dicen dónde está el papel. Esta lista dice si ese
tamaño cabe y cuánto ocupa el retrato, de pie, dentro de la hoja.
"""

from __future__ import annotations

# nombre: (etiqueta, lado corto mm, lado largo mm).
PAPERS: dict[str, tuple[str, float, float]] = {
    "a6": ("A6", 105.0, 148.0),
    "a5": ("A5", 148.0, 210.0),
    "media_carta": ("Media carta", 140.0, 216.0),
    "a4": ("A4", 210.0, 297.0),
    "carta": ("Carta", 216.0, 279.0),
}

DEFAULT = "a5"

MARGIN_MM = 8.0

# Caja medida. El fondo es el eje X del robot; el ancho, el Y.
SAFE_DEPTH_MM = 240.0
SAFE_WIDTH_MM = 440.0
CENTER_X_MM = 319.24
CENTER_Y_MM = -27.2

# Alto del retrato entre su ancho: recorte 3:4 más el rótulo. Igual que frame.PORTRAIT_ASPECT.
PORTRAIT_ASPECT = 1.45


def known(name: str) -> bool:
    return str(name or "").strip().lower() in PAPERS


def _key(name: str) -> str:
    key = str(name or "").strip().lower()
    return key if key in PAPERS else DEFAULT


def size_mm(name: str) -> tuple[float, float]:
    """(lado corto, lado largo), como viene en el paquete."""
    _, corto, largo = PAPERS[_key(name)]
    return corto, largo


def label(name: str) -> str:
    return PAPERS[_key(name)][0]


def place_mm(name: str) -> tuple[float, float]:
    """(izquierda-derecha, frente al fondo) con la hoja horizontal."""
    corto, largo = size_mm(name)
    return largo, corto


def draw_size_mm(name: str) -> tuple[float, float]:
    """Retrato de pie, centrado en la hoja horizontal, sin salirse del lado corto."""
    ancho, fondo = place_mm(name)
    usable_w = ancho - 2 * MARGIN_MM
    usable_h = fondo - 2 * MARGIN_MM
    width = min(usable_w, usable_h / PORTRAIT_ASPECT)
    return width, width * PORTRAIT_ASPECT


def draw_width_mm(name: str) -> float:
    return draw_size_mm(name)[0]


def draw_height_mm(name: str) -> float:
    return draw_size_mm(name)[1]


def fits(name: str) -> tuple[bool, str]:
    """(cabe, motivo) con la hoja horizontal sobre la caja medida."""
    ancho, fondo = place_mm(name)
    if fondo > SAFE_DEPTH_MM:
        return False, (
            f"{label(name)} no entra de frente al fondo: el brazo llega a "
            f"{SAFE_DEPTH_MM:.0f} mm y el lado corto mide {fondo:.0f} mm"
        )
    if ancho > SAFE_WIDTH_MM:
        return False, (
            f"{label(name)} no entra a lo ancho: el brazo llega a "
            f"{SAFE_WIDTH_MM:.0f} mm y el lado largo mide {ancho:.0f} mm"
        )
    return True, ""


def catalog() -> list[dict]:
    """Lo que el panel lista: tamaño horizontal, retrato y si cabe."""
    filas: list[dict] = []
    for name, (name_label, corto, largo) in PAPERS.items():
        cabe, motivo = fits(name)
        draw_w, draw_h = draw_size_mm(name)
        filas.append(
            {
                "id": name,
                "label": name_label,
                "short_mm": corto,
                "long_mm": largo,
                "width_mm": largo,
                "height_mm": corto,
                "draw_width_mm": round(draw_w, 1),
                "draw_height_mm": round(draw_h, 1),
                "fits": cabe,
                "reason": motivo,
            }
        )
    return filas
