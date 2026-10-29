"""Hojas de papel que el brazo alcanza, medidas moviendo el MG400 de verdad.

La caja no es un rectángulo: hacia la izquierda el codo se queda sin recorrido
antes que la mesa, y hacia la derecha manda el radio de 440 mm. Los números
salen de pasear el brazo desde el centro del papel hasta que un tope lo
detiene, en la cabina real.
"""

from __future__ import annotations

# nombre: (etiqueta, ancho mm, alto mm). Son las hojas que tienen sentido en
# una cabina de fotos; A3 y A2 no caben ni de lejos en el área del MG400.
PAPERS: dict[str, tuple[str, float, float]] = {
    "a6": ("A6", 105.0, 148.0),
    "a5": ("A5", 148.0, 210.0),
    "a4": ("A4", 210.0, 297.0),
}

DEFAULT = "a5"

# Aire entre el borde de la hoja y el retrato.
MARGIN_MM = 8.0

# Caja medida desde el centro del papel, en mm.
SAFE_LEFT_MM = 80.0
SAFE_RIGHT_MM = 160.0
SAFE_UP_MM = 220.0
SAFE_DOWN_MM = 220.0

# El recorte del boceto es 3:4; el alto del dibujo acompaña al ancho.
ASPECT = 4.0 / 3.0


def known(name: str) -> bool:
    return str(name or "").strip().lower() in PAPERS


def _key(name: str) -> str:
    """Un nombre que no es una hoja conocida cae en la de por defecto."""
    key = str(name or "").strip().lower()
    return key if key in PAPERS else DEFAULT


def size_mm(name: str) -> tuple[float, float]:
    _, ancho, alto = PAPERS[_key(name)]
    return ancho, alto


def label(name: str) -> str:
    return PAPERS[_key(name)][0]


def draw_width_mm(name: str) -> float:
    """Ancho del retrato: el de la hoja menos el aire de los dos lados."""
    return size_mm(name)[0] - 2 * MARGIN_MM


def draw_height_mm(name: str) -> float:
    return draw_width_mm(name) * ASPECT


def fits(name: str) -> tuple[bool, str]:
    """(cabe, motivo). El motivo se muestra en el panel cuando no cabe."""
    ancho, alto = size_mm(name)
    falta_izquierda = ancho / 2 - SAFE_LEFT_MM
    if falta_izquierda > 0:
        return False, (
            f"el codo no llega: {label(name)} se pasa {falta_izquierda:.0f} mm "
            "por la izquierda del área del brazo"
        )
    if ancho / 2 > SAFE_RIGHT_MM:
        return False, f"{label(name)} se pasa del radio del brazo por la derecha"
    if alto / 2 > max(SAFE_UP_MM, SAFE_DOWN_MM):
        return False, f"{label(name)} se pasa del área del brazo de arriba a abajo"
    if draw_height_mm(name) > alto - 2 * MARGIN_MM:
        return False, f"el retrato no cabe a lo alto en {label(name)}"
    return True, ""


def catalog() -> list[dict]:
    """Lo que el panel lista: tamaños, si caben y por qué no."""
    filas: list[dict] = []
    for name, (name_label, ancho, alto) in PAPERS.items():
        cabe, motivo = fits(name)
        filas.append(
            {
                "id": name,
                "label": name_label,
                "width_mm": ancho,
                "height_mm": alto,
                "draw_width_mm": draw_width_mm(name),
                "fits": cabe,
                "reason": motivo,
            }
        )
    return filas
