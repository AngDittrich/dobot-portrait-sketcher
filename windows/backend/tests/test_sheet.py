"""Hojas de papel contra la caja que se midió moviendo el brazo de verdad."""

import pytest

from app.robot import sheet


def test_la_a5_cabe_en_el_area_que_el_brazo_alcanza():
    cabe, motivo = sheet.fits("a5")
    assert cabe
    assert motivo == ""


def test_la_a4_no_cabe_de_frente_al_fondo():
    # Acostada mide 297 mm y el brazo solo tiene 240 mm de fondo útil.
    cabe, motivo = sheet.fits("a4")
    assert not cabe
    assert "fondo" in motivo


def test_la_hoja_se_mide_acostada():
    # A5 acostada: 210 mm de frente al fondo y 148 a lo ancho.
    assert sheet.place_mm("a5") == (210.0, 148.0)


def test_el_dibujo_deja_margen_a_los_lados():
    # 148 mm de hoja menos 8 mm por lado: el retrato no llega al borde.
    assert sheet.draw_width_mm("a5") == pytest.approx(132.0)
    assert sheet.draw_width_mm("a6") == pytest.approx(89.0)


def test_el_retrato_cabe_a_lo_alto_en_cada_hoja():
    for name in sheet.PAPERS:
        _, largo = sheet.size_mm(name)
        assert sheet.draw_height_mm(name) <= largo - 2 * sheet.MARGIN_MM


def test_un_nombre_desconocido_cae_en_la_hoja_de_por_defecto():
    assert sheet.size_mm("carta") == sheet.size_mm(sheet.DEFAULT)


def test_el_catalogo_dice_cual_cabe_para_el_panel():
    filas = {fila["id"]: fila for fila in sheet.catalog()}
    assert filas["a5"]["fits"] is True
    assert filas["a4"]["fits"] is False
    assert filas["a5"]["draw_width_mm"] == pytest.approx(132.0)


CALIBRACION = {
    "backend": "mg400",
    "host": "192.168.10.55",
    "user": 0,
    "tool": 0,
    "z_draw": -97,
    "z_travel": -90,
    "r": 120.57,
    "r_far": 0,
    "far_x": 0,
    "far_y": 0,
    "speed_factor": 20,
    "origin_x": 279.24,
    "origin_y": -27.2,
    "x_sign": -1,
    "y_sign": -1,
    "cp_draw": 100,
}


def test_la_cabina_guarda_la_hoja_elegida():
    from app.robot.booth import parse_booth

    booth = parse_booth({**CALIBRACION, "sheet": "a6"})
    assert booth.sheet == "a6"


def test_sin_hoja_guardada_se_usa_la_de_por_defecto():
    from app.robot.booth import parse_booth

    assert parse_booth(dict(CALIBRACION)).sheet == sheet.DEFAULT


def test_una_hoja_que_no_existe_no_se_guarda():
    from app.robot.booth import BoothError, parse_booth

    with pytest.raises(BoothError):
        parse_booth({**CALIBRACION, "sheet": "carta"})
