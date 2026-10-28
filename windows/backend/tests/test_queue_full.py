"""La cola del MG400 devuelve -30000 cuando está llena: eso no es un fallo.

El controlador acepta unas decenas de MovL mientras el brazo dibuja. Cuando se
llena rechaza la orden con -30000 y el cliente lo trataba como error fatal:
soltura el socket y el dibujo se quedaba corto, mientras el brazo terminaba lo
que ya tenía encolado (la pantalla decía EL ROBOT SE DETUVO con el robot
moviéndose).
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import MG400Error, Reply, _parse  # noqa: E402


def test_el_parser_no_pierde_el_codigo_cuando_no_hay_coma():
    """El controlador contesta `-30000MovL(...);` sin coma: el código es -30000."""
    respuesta = _parse("-30000MovL(274.368,-67.592,-119.230,0.001,SpeedL=40,AccL=40,CP=1);")
    assert respuesta.code == -30000
    assert not respuesta.ok


class ColaLlena:
    """Rechaza las primeras `rechazos` órdenes con -30000 y después acepta."""

    def __init__(self, rechazos: int) -> None:
        self.rechazos = rechazos
        self.moves: list[str] = []
        self.dashboard_cmds: list[str] = []

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        if command.startswith("MovL") and self.rechazos > 0:
            self.rechazos -= 1
            return Reply(code=-30000, value="")
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        self.dashboard_cmds.append(command)
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        self.moves.append("Sync()")

    def errors(self) -> str:
        return ""


def _cliente(enlace) -> MG400Client:
    return MG400Client(
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
        queue_retry_s=0.0,
        pace_lead_s=0.0,
    )


def _papel() -> Trajectory:
    return Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]])],
        width_mm=20.0,
        height_mm=20.0,
    )


def _correr(cliente: MG400Client, papel: Trajectory) -> None:
    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())


def test_cola_llena_se_reintenta_y_el_dibujo_termina():
    enlace = ColaLlena(rechazos=3)
    cliente = _cliente(enlace)

    _correr(cliente, _papel())

    assert not any("Sync()" in move for move in enlace.moves)
    # Tres rechazos, tres reenvíos: la orden no se pierde ni corta el dibujo.
    assert sum(1 for orden in enlace.moves if orden.startswith("MovL")) == 4 + 3
    assert cliente._sent == 4


class EnlaceRoto(ColaLlena):
    def move(self, command: str) -> Reply:
        self.moves.append(command)
        if command.startswith("MovL"):
            return Reply(code=-1, value="")
        return Reply(code=0, value="")


def test_un_error_de_verdad_no_se_reintenta():
    enlace = EnlaceRoto(rechazos=0)
    cliente = _cliente(enlace)

    with pytest.raises(MG400Error):
        _correr(cliente, _papel())

    movimientos = [orden for orden in enlace.moves if orden.startswith("MovL")]
    assert len(movimientos) == 1
    assert cliente._link is None
