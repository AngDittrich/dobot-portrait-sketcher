"""Hojas de papel que el brazo alcanza, medidas moviendo el MG400 de verdad.

La hoja va **acostada**: su lado largo apunta de frente al fondo (el eje X del
robot) y el corto queda a lo ancho. Así el retrato, que también va acostado,
se reparte donde hay sitio.

La caja no es un rectángulo: de frente al fondo el brazo tiene 240 mm útiles
(desde los 199 mm del muro del codo hasta los 439 mm del radio de 440), y a lo
ancho 440 mm. Por eso el centro del papel va en el punto medio de esa banda
—319.24 mm, no en 279.24— y las hojas se miden contra esos 240 mm.
"""

from __future__ import annotations

# nombre: (etiqueta, lado corto mm, lado largo mm). Son las hojas que tienen
# sentido en una cabina de fotos; A3 y A2 no caben ni de lejos.
PAPERS: dict[str, tuple[str, float, float]] = {
    "a6": ("A6", 105.0, 148.0),
    "a5": ("A5", 148.0, 210.0),
    "a4": ("A4", 210.0, 297.0),
}

DEFAULT = "a5"

# Aire entre el borde de la hoja y el retrato.
MARGIN_MM = 8.0

# Caja que alcanza el brazo con el papel acostado, medida en la cabina real.
SAFE_DEPTH_MM = 240.0
SAFE_WIDTH_MM = 440.0

# Dónde hay que centrar la hoja para que esos 240 mm queden repartidos.
CENTER_X_MM = 319.24
CENTER_Y_MM = -27.2

# El recorte del boceto es 3:4; el alto del dibujo acompaña al ancho.
ASPECT = 4.0 / 3.0


def known(name: str) -> bool:
    return str(name or "").strip().lower() in PAPERS


def _key(name: str) -> str:
    """Un nombre que no es una hoja conocida cae en la de por defecto."""
    key = str(name or "").strip().lower()
    return key if key in PAPERS else DEFAULT


def size_mm(name: str) -> tuple[float, float]:
    """(lado corto, lado largo) de la hoja, como viene en el paquete."""
    _, corto, largo = PAPERS[_key(name)]
    return corto, largo


def label(name: str) -> str:
    return PAPERS[_key(name)][0]


def place_mm(name: str) -> tuple[float, float]:
    """(frente al fondo, a lo ancho) de la hoja ya acostada sobre la mesa."""
    corto, largo = size_mm(name)
    return largo, corto


def draw_width_mm(name: str) -> float:
    """Ancho del retrato: el lado corto de la hoja menos el aire de los lados."""
    return size_mm(name)[0] - 2 * MARGIN_MM


def draw_height_mm(name: str) -> float:
    return draw_width_mm(name) * ASPECT


def fits(name: str) -> tuple[bool, str]:
    """(cabe, motivo). El motivo se muestra en el panel cuando no cabe."""
    corto, largo = size_mm(name)
    if largo > SAFE_DEPTH_MM:
        return False, (
            f"{label(name)} no entra de frente al fondo: el brazo llega a "
            f"{SAFE_DEPTH_MM:.0f} mm y la hoja mide {largo:.0f} mm acostada"
        )
    if corto > SAFE_WIDTH_MM:
        return False, (
            f"{label(name)} no entra a lo ancho: el brazo llega a "
            f"{SAFE_WIDTH_MM:.0f} mm y la hoja mide {corto:.0f} mm"
        )
    if draw_height_mm(name) > largo - 2 * MARGIN_MM:
        return False, f"el retrato no cabe en {label(name)}"
    return True, ""


def catalog() -> list[dict]:
    """Lo que el panel lista: tamaños, si caben y por qué no."""
    filas: list[dict] = []
    for name, (name_label, corto, largo) in PAPERS.items():
        cabe, motivo = fits(name)
        filas.append(
            {
                "id": name,
                "label": name_label,
                "width_mm": largo,
                "height_mm": corto,
                "draw_width_mm": draw_width_mm(name),
                "fits": cabe,
                "reason": motivo,
            }
        )
    return filas
