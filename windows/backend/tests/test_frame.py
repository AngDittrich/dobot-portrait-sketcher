"""Marco de la hoja con tres esquinas: orientación, ejes, plano Z y alcance."""

import pytest

from app.robot.frame import (
    Corner,
    Frame,
    FrameError,
    fit,
    nearest_paper,
    portrait_width_mm,
    reach_report,
    summary,
)


def _a5_horizontal(z: float = -65.0) -> Frame:
    # Hoja de 210 × 148 frente al robot: lo ancho va de lado a lado (eje Y del
    # robot) y "arriba" del dibujo queda lejos de la base.
    return Frame.from_corners(
        Corner(320.0, 105.0, z, 0.0),
        Corner(320.0, -105.0, z, 0.0),
        Corner(172.0, 105.0, z, 0.0),
    )


def test_la_hoja_horizontal_sale_de_las_esquinas():
    frame = _a5_horizontal()
    assert frame.width == pytest.approx(210.0)
    assert frame.height == pytest.approx(148.0)
    assert frame.orientation == "horizontal"
    assert nearest_paper(frame)["id"] == "a5"


def test_los_ejes_de_la_hoja_caen_donde_se_enseñaron():
    frame = _a5_horizontal()
    assert frame.to_robot(0, 0)[:2] == pytest.approx((320.0, 105.0))
    assert frame.to_robot(210, 0)[:2] == pytest.approx((320.0, -105.0))
    assert frame.to_robot(0, 148)[:2] == pytest.approx((172.0, 105.0))
    assert frame.named("br")[:2] == pytest.approx((172.0, -105.0))
    assert frame.named("center")[:2] == pytest.approx((246.0, 0.0))


def test_una_hoja_girada_tambien_se_mapea():
    frame = Frame.from_corners(
        Corner(300.0, 0.0, -65.0, 0.0),
        Corner(300.0 + 100.0, 100.0, -65.0, 0.0),
        Corner(300.0 - 100.0, 100.0, -65.0, 0.0),
    )
    assert frame.width == pytest.approx(141.42, abs=0.01)
    x, y, _, _ = frame.named("br")
    assert (x, y) == pytest.approx((300.0, 200.0))


def test_la_z_sigue_la_mesa_si_no_esta_pareja():
    frame = Frame.from_corners(
        Corner(320.0, 105.0, -65.0, 0.0),
        Corner(320.0, -105.0, -63.0, 0.0),
        Corner(172.0, 105.0, -66.0, 0.0),
    )
    # A mitad del borde de arriba la mesa queda entre las dos alturas enseñadas.
    assert frame.to_robot(frame.width / 2, 0)[2] == pytest.approx(-64.0, abs=0.05)
    assert frame.named("br")[2] == pytest.approx(-64.0, abs=0.05)


def test_la_r_se_interpola_entre_esquinas():
    frame = Frame.from_corners(
        Corner(320.0, 105.0, -65.0, 120.0),
        Corner(320.0, -105.0, -65.0, 160.0),
        Corner(172.0, 105.0, -65.0, 120.0),
    )
    assert frame.to_robot(105, 74)[3] == pytest.approx(140.0)


def test_una_esquina_repetida_no_es_una_hoja():
    with pytest.raises(FrameError):
        Frame.from_corners(
            Corner(320.0, 105.0, -65.0, 0.0),
            Corner(320.0, 105.5, -65.0, 0.0),
            Corner(172.0, 105.0, -65.0, 0.0),
        )


def test_una_esquina_chueca_se_rechaza():
    with pytest.raises(FrameError, match="ángulo"):
        Frame.from_corners(
            Corner(320.0, 105.0, -65.0, 0.0),
            Corner(320.0, -105.0, -65.0, 0.0),
            Corner(172.0, 160.0, -65.0, 0.0),
        )


def test_el_retrato_vertical_se_centra_en_la_hoja_horizontal():
    frame = _a5_horizontal()
    ancho = portrait_width_mm(frame, 8.0)
    # En horizontal manda el alto: 148 - 16 = 132 mm de alto útil.
    assert ancho == pytest.approx(132.0 / 1.45)
    escala, u0, v0 = fit(frame, ancho, ancho * 1.45, 8.0)
    assert escala == pytest.approx(1.0)
    assert v0 == pytest.approx(8.0)
    assert u0 == pytest.approx((210.0 - ancho) / 2)


def test_un_dibujo_mas_grande_se_achica_sin_estirarse():
    frame = _a5_horizontal()
    escala, _, _ = fit(frame, 140.0, 200.0, 8.0)
    assert escala == pytest.approx(132.0 / 200.0)


def test_una_esquina_fuera_del_radio_impide_guardar():
    frame = Frame.from_corners(
        Corner(440.0, 105.0, -65.0, 0.0),
        Corner(440.0, -105.0, -65.0, 0.0),
        Corner(292.0, 105.0, -65.0, 0.0),
    )
    errores, _ = reach_report(frame)
    assert any("440" in error for error in errores)


def test_una_hoja_pegada_a_la_columna_avisa():
    frame = Frame.from_corners(
        Corner(250.0, 105.0, -65.0, 0.0),
        Corner(250.0, -105.0, -65.0, 0.0),
        Corner(102.0, 105.0, -65.0, 0.0),
    )
    errores, avisos = reach_report(frame)
    assert not errores
    assert any("columna" in aviso for aviso in avisos)


def _esquinas_a_dos_grados():
    """210 × 148 con la esquina inferior 2° abierta. El paralelogramo estira la otra punta."""
    import math

    tl = Corner(320.0, 105.0, -65.0, 0.0)
    tr = Corner(320.0, -105.0, -65.0, 0.0)
    radians = math.radians(92.0)
    bl = Corner(320.0 - 148.0 * math.sin(radians), 105.0 - 148.0 * math.cos(radians), -65.0, 0.0)
    return tl, tr, bl


def test_dos_grados_se_enderezan_en_un_rectangulo():
    tl, tr, bl = _esquinas_a_dos_grados()
    frame = Frame.from_corners(tl, tr, bl)
    assert frame.straighten_deg == pytest.approx(2.0, abs=0.05)
    assert frame.corner_angle_deg == pytest.approx(90.0, abs=0.05)
    assert frame.manual is False
    ux, uy, uz = frame.tr.x - frame.tl.x, frame.tr.y - frame.tl.y, frame.tr.z - frame.tl.z
    vx, vy, vz = frame.bl.x - frame.tl.x, frame.bl.y - frame.tl.y, frame.bl.z - frame.tl.z
    assert ux * vx + uy * vy + uz * vz == pytest.approx(0.0, abs=0.05)
    # El error se reparte: ninguna punta se queda con los ~7 mm del paralelogramo.
    assert frame.shift_mm < 5.0
    assert frame.residuals_mm[3] > 1.0
    datos = summary(frame)
    assert datos["straighten_deg"] == pytest.approx(2.0, abs=0.05)
    assert any("escuadra" in aviso for aviso in datos["warnings"])


def test_la_esquina_escrita_a_mano_se_respeta():
    tl, tr, bl = _esquinas_a_dos_grados()
    br = Corner(170.0, -100.0, -65.0, 0.0)
    frame = Frame.from_corners(tl, tr, bl, br)
    assert frame.manual is True
    assert frame.named("br")[:3] == pytest.approx((170.0, -100.0, -65.0))
    assert frame.named("tl")[:2] == pytest.approx((tl.x, tl.y))
    assert frame.named("tr")[:2] == pytest.approx((tr.x, tr.y))
    assert frame.named("bl")[:2] == pytest.approx((bl.x, bl.y))
    otra = Frame.from_dict({"tl": tl.as_dict(), "tr": tr.as_dict(), "bl": bl.as_dict(), "br": br.as_dict()})
    assert otra.manual is True
    assert otra.as_dict()["br"]["x"] == pytest.approx(170.0)


def test_el_resumen_da_la_caja_del_retrato_dentro_de_la_hoja():
    datos = summary(_a5_horizontal(), 8.0)
    assert datos["orientation"] == "horizontal"
    assert datos["paper"]["label"] == "A5"
    assert datos["errors"] == []
    xs = [x for x, _ in datos["draw_box"]]
    ys = [y for _, y in datos["draw_box"]]
    assert min(xs) >= 172.0 and max(xs) <= 320.0
    assert min(ys) >= -105.0 and max(ys) <= 105.0
