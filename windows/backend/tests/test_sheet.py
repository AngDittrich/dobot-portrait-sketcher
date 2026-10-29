"""Hojas estándar en horizontal, contra la caja medida del brazo."""

import pytest

from app.robot import sheet


def test_la_a5_horizontal_cabe():
    cabe, motivo = sheet.fits("a5")
    assert cabe
    assert motivo == ""


def test_la_a4_horizontal_cabe_porque_el_lado_corto_va_de_frente():
    # 210 mm de fondo entran en los 240 medidos. Con el lado largo de frente
    # al fondo no entraría: 297 mm no caben en 240.
    cabe, motivo = sheet.fits("a4")
    assert cabe
    assert motivo == ""
    assert sheet.place_mm("a4") == (297.0, 210.0)


def test_la_hoja_horizontal_pone_el_lado_largo_de_izquierda_a_derecha():
    assert sheet.place_mm("a5") == (210.0, 148.0)


def test_el_retrato_se_queda_dentro_del_lado_corto():
    # A5 horizontal: 148 mm de fondo menos 8 por lado = 132, y el retrato
    # es más alto que ancho, así que el fondo es el que manda.
    ancho, alto = sheet.draw_size_mm("a5")
    assert alto == pytest.approx(132.0)
    assert ancho == pytest.approx(132.0 / sheet.PORTRAIT_ASPECT)
    assert alto <= 148.0 - 2 * sheet.MARGIN_MM


def test_un_nombre_desconocido_cae_en_la_hoja_de_por_defecto():
    assert sheet.size_mm("tabloide") == sheet.size_mm(sheet.DEFAULT)


def test_el_catalogo_dice_el_tamano_horizontal_y_si_cabe():
    filas = {fila["id"]: fila for fila in sheet.catalog()}
    assert filas["a5"]["width_mm"] == pytest.approx(210.0)
    assert filas["a5"]["height_mm"] == pytest.approx(148.0)
    assert filas["a5"]["fits"] is True
    assert filas["carta"]["fits"] is True
    assert filas["a4"]["draw_height_mm"] <= 210.0 - 2 * sheet.MARGIN_MM
