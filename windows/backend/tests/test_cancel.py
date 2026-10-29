"""Cancelar un dibujo corta el lazo y la bitácora no borra el que sigue."""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import DrawCancelled, MockRobotClient, Segment, Trajectory  # noqa: E402
from app.store import Job, JobStore  # noqa: E402


def test_el_simulador_corta_el_dibujo_entre_tramos():
    cliente = MockRobotClient(speed_mm_s=1000.0, time_scale=0.0)
    trayecto = Trajectory(
        segments=[
            Segment(type="draw", points=[[0.0, 0.0], [1.0, 0.0]]),
            Segment(type="draw", points=[[1.0, 0.0], [2.0, 0.0]]),
        ],
        width_mm=10.0,
        height_mm=10.0,
    )

    async def al_avanzar(_valor: float, _tramo: Segment) -> None:
        cliente._cancel = True

    with pytest.raises(DrawCancelled):
        asyncio.run(cliente.draw(trayecto, al_avanzar))


def test_borrar_la_bitacora_deja_el_dibujo_en_curso():
    store = JobStore()
    store.put("listo", Job(id="listo", sketch_id="s", status="done"))
    store.put("mal", Job(id="mal", sketch_id="s", status="error"))
    store.put("ahora", Job(id="ahora", sketch_id="s", status="drawing"))
    assert store.drop_settled() == 2
    assert store.get("ahora") is not None
    assert store.get("listo") is None
    assert store.get("mal") is None
