"""prepare_motion no repite lo ya preparado y el puerto de movimiento no espera al dashboard."""

import asyncio

from app.robot.client import MG400Client
from app.robot.mg400 import Reply


class Enlace:
    def __init__(self) -> None:
        self.prepares: list[int] = []
        self.moves: list[str] = []
        self.dashboards: list[str] = []

    def prepare(self, percent: int = 20) -> None:
        self.prepares.append(percent)

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        self.dashboards.append(command)
        return Reply(code=0, value="")


def _cliente(enlace: Enlace) -> MG400Client:
    return MG400Client(link=enlace, z_draw=-65.0, z_travel=-57.0)


def test_prepare_se_repite_solo_si_cambia_la_velocidad():
    enlace = Enlace()
    cliente = _cliente(enlace)
    asyncio.run(cliente.prepare_motion(50))
    assert enlace.prepares.count(50) == 1
    # Misma velocidad: no viaja nada más al robot.
    asyncio.run(cliente.prepare_motion(50))
    assert enlace.prepares.count(50) == 1
    # Otra velocidad: se prepara una vez más.
    asyncio.run(cliente.prepare_motion(30))
    assert enlace.prepares.count(30) == 1


def test_reconectar_vuelve_a_preparar():
    enlace = Enlace()
    cliente = _cliente(enlace)
    asyncio.run(cliente.prepare_motion(50))
    assert enlace.prepares.count(50) == 1
    cliente._drop()
    asyncio.run(cliente.prepare_motion(50))
    assert enlace.prepares.count(50) == 2


def test_orden_de_estado_invalida_lo_preparado():
    enlace = Enlace()
    cliente = _cliente(enlace)
    asyncio.run(cliente.prepare_motion(50))
    assert enlace.prepares.count(50) == 1
    code, _ = asyncio.run(cliente.ask("EnableRobot()"))
    assert code == 0
    asyncio.run(cliente.prepare_motion(50))
    assert enlace.prepares.count(50) == 2


def test_movimiento_usa_otro_candado_que_el_dashboard():
    enlace = Enlace()
    cliente = _cliente(enlace)
    assert cliente._move_wire is not cliente._wire
    code, _ = asyncio.run(cliente.ask("MoveJog(X+)", move=True))
    assert code == 0
    assert enlace.moves == ["MoveJog(X+)"]
    # El jog va por el puerto de movimiento. User y Tool salen una vez por el dashboard.
    assert enlace.dashboards == ["User(0)", "Tool(0)"]
