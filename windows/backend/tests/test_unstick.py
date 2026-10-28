"""La cola del MG400 se traba y hay que desbloquearla sin ir al robot.

Medido en el robot real: tras una alarma el controlador acepta MovL con codigo
0 y el brazo no se mueve. Stop() devuelve -10000, ClearError() responde 0 pero
no basta, y ResetRobot() si: despues de eso la ida y vuelta de 5 mm volvio a dar
187.308 -> 192.308 -> 187.308 exactos.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+)")


class EnlaceTrabado:
    """Enlace que acepta las ordenes y nunca mueve el brazo."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.dashboards: list[str] = []
        self.pose_fija = (100.0, 100.0, -160.0, 0.0)

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        self.dashboards.append(command)
        if command.strip().startswith("RobotMode"):
            return Reply(code=0, value="5")
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        self.moves.append("Sync()")

    def errors(self) -> str:
        return ""

    def pose(self) -> tuple[float, float, float, float]:
        return self.pose_fija


def _destino(command: str) -> tuple[str, str, str] | None:
    found = MOVL.search(command)
    if not found:
        return None
    return found.groups()


async def _nada(_valor: float, _segmento: Segment) -> None:
    return None


def _cliente(enlace: EnlaceTrabado) -> MG400Client:
    return MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=100.0,
        origin_y=100.0,
        pipeline=1,
        wait_arrival=True,
        arrival_extra_s=0.02,
        arrival_poll_s=0.005,
        min_step_mm=0.0,
        unstick_resets=1,
        unstick_sleep_s=0.0,
    )


def test_la_cola_trabada_se_desbloquea_sola() -> None:
    enlace = EnlaceTrabado()
    client = _cliente(enlace)
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]])],
        width_mm=140.0,
        height_mm=140.0,
    )

    asyncio.run(client.draw(papel, _nada))

    assert any("ResetRobot()" in command for command in enlace.dashboards)
    destinos = [d for d in (_destino(m) for m in enlace.moves) if d]
    assert destinos, "no se mando ningun MovL"
    reenviados = [d for d in set(destinos) if destinos.count(d) == 2]
    assert reenviados, f"ningun destino se reenvio tras el reset: {destinos}"


def test_no_se_reinicia_si_el_brazo_se_mueve() -> None:
    class EnlaceVivo(EnlaceTrabado):
        def move(self, command: str) -> Reply:
            self.moves.append(command)
            found = MOVL.search(command)
            if found:
                self.pose_fija = (float(found.group(1)), float(found.group(2)), float(found.group(3)), 0.0)
            return Reply(code=0, value="")

    enlace = EnlaceVivo()
    client = _cliente(enlace)
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]])],
        width_mm=140.0,
        height_mm=140.0,
    )

    asyncio.run(client.draw(papel, _nada))

    assert not any("ResetRobot()" in command for command in enlace.dashboards)
