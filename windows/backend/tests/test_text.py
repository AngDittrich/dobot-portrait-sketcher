"""SYSCOM de prueba queda centrado en la hoja y el panel lo manda a dibujar."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.text import syscom_trajectory  # noqa: E402


def test_syscom_queda_en_el_centro_de_la_hoja():
    trayecto = syscom_trajectory(210.0, 148.0, margin_mm=8.0)
    puntos = [punto for tramo in trayecto.segments for punto in tramo.points]
    assert len(trayecto.segments) >= 6
    assert all(tramo.type == "draw" for tramo in trayecto.segments)
    xs = [x for x, _ in puntos]
    ys = [y for _, y in puntos]
    assert min(xs) > 8 and max(xs) < 210 - 8
    assert min(ys) > 8 and max(ys) < 148 - 8
    assert (min(xs) + max(xs)) / 2 == pytest.approx(105.0, abs=1.0)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(74.0, abs=1.0)


def test_el_panel_dibuja_syscom_sobre_la_hoja_ensenada(monkeypatch: pytest.MonkeyPatch):
    import asyncio

    from app import main
    from app.admin_ops import drop_tokens, issue_token

    class Robot:
        name = "mg400"
        frame = None
        lift_mm = 8.0
        margin_mm = 8.0

        def set_frame(self, frame, lift, margin) -> None:
            self.frame = frame
            self.lift_mm = lift
            self.margin_mm = margin

        async def draw(self, trajectory, on_progress, *, sheet_mm: bool = False) -> None:
            self.sheet_mm = sheet_mm
            self.size = (trajectory.width_mm, trajectory.height_mm)
            await on_progress(1.0, trajectory.segments[0])

    robot = Robot()
    monkeypatch.setattr(main, "robot", robot)
    pending: list = []
    real = asyncio.create_task

    def capture(coro):
        task = real(coro)
        pending.append(task)
        return task

    monkeypatch.setattr(main.asyncio, "create_task", capture)
    drop_tokens()
    esquinas = {
        "tl": {"x": 320.0, "y": 105.0, "z": -65.0, "r": 120.0},
        "tr": {"x": 320.0, "y": -105.0, "z": -65.0, "r": 120.0},
        "bl": {"x": 172.0, "y": 105.0, "z": -65.0, "r": 120.0},
    }

    async def run() -> None:
        data = await main.admin_test_draw(
            {"corners": esquinas, "lift_mm": 8, "margin_mm": 8},
            x_admin_token=issue_token(),
        )
        await asyncio.gather(*pending)
        assert data["text"] == "SYSCOM"
        assert robot.sheet_mm is True
        assert robot.size == pytest.approx((210.0, 148.0))

    asyncio.run(run())

