"""El origen del papel es su centro, no su esquina.

Con el origen en la esquina, la coordenada `y` del papel (0 arriba del recorte)
se traducía a "centro menos la altura entera" y el brazo se iba 135 mm por
debajo del centro: salió del rango de los ejes y tumbó el controlador. El
centro no depende del tamaño del recorte, que cambia con cada foto.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from app.robot.client import MG400Client, Segment, Trajectory


def _cliente() -> MG400Client:
    async def dormir(_segundos: float) -> None:
        return None

    return MG400Client(
        z_draw=-97.0,
        z_travel=-90.0,
        origin_x=279.24,
        origin_y=-27.20,
        x_sign=-1,
        y_sign=-1,
        dry_run=True,
        speed_factor=20,
        cp_draw=100,
        min_step_mm=0.0,
        join_gap_mm=0.0,
        pipeline=1,
        pace_lead_s=0.0,
        sleep=dormir,
    )


def _movimientos(cliente: MG400Client) -> list[tuple[float, float]]:
    puntos: list[tuple[float, float]] = []
    for command in cliente.commands:
        match = re.match(r"MovL\((-?[\d.]+),(-?[\d.]+),", command)
        if match:
            puntos.append((float(match.group(1)), float(match.group(2))))
    return puntos


def _dibujar(cliente: MG400Client, ancho: float, alto: float) -> list[tuple[float, float]]:
    trayectoria = Trajectory(
        segments=[
            Segment(
                type="draw",
                points=[[0.0, 0.0], [ancho, alto]],
            )
        ],
        width_mm=ancho,
        height_mm=alto,
    )

    async def progreso(_valor: float, _segmento: Segment | None = None) -> None:
        return None

    asyncio.run(cliente.draw(trayectoria, progreso))
    return _movimientos(cliente)


def test_el_papel_queda_centrado_en_el_origen() -> None:
    puntos = _dibujar(_cliente(), 140.0, 145.1)

    xs = [x for x, _ in puntos]
    ys = [y for _, y in puntos]
    # x = 0 es el borde derecho del papel; x = 140, el izquierdo.
    assert max(xs) == pytest.approx(279.24 + 70.0)
    assert min(xs) == pytest.approx(279.24 - 70.0)
    # y = 0 es el borde de arriba; y = 145.1, el de abajo.
    assert max(ys) == pytest.approx(-27.20 + 145.1 / 2)
    assert min(ys) == pytest.approx(-27.20 - 145.1 / 2)


def test_un_recorte_mas_alto_sigue_centrado() -> None:
    puntos = _dibujar(_cliente(), 140.0, 180.0)

    ys = [y for _, y in puntos]
    assert max(ys) == pytest.approx(-27.20 + 90.0)
    assert min(ys) == pytest.approx(-27.20 - 90.0)
