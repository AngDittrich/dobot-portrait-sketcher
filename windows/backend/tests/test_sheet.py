"""Catálogo de hojas estándar: sirve para comprobar la hoja enseñada."""

import pytest

from app.robot import sheet


def test_el_dibujo_sin_esquinas_deja_margen_a_los_lados():
    # 148 mm de lado corto menos 8 mm por lado: el retrato no llega al borde.
    assert sheet.draw_width_mm("a5") == pytest.approx(132.0)
    assert sheet.draw_width_mm("a6") == pytest.approx(89.0)


def test_un_nombre_desconocido_cae_en_la_hoja_de_por_defecto():
    assert sheet.size_mm("tabloide") == sheet.size_mm(sheet.DEFAULT)


def test_el_catalogo_trae_carta_y_media_carta():
    filas = {fila["id"]: fila for fila in sheet.catalog()}
    assert filas["carta"]["short_mm"] == pytest.approx(216.0)
    assert filas["media_carta"]["long_mm"] == pytest.approx(216.0)
    assert all(fila["short_mm"] < fila["long_mm"] for fila in filas.values())
