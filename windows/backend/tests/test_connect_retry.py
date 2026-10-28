"""La conexión que pasó minutos ociosa amanece cerrada.

El controlador cierra los sockets cuando nadie los usa: entre que el visitante
termina la foto y el boceto llega (unos quince segundos con el proveedor de
IA) el robot ya no contesta la primera orden y el trabajo moría al 0 %. Hay que
reconectar y volver a intentar, no declarar el fallo.
"""

from __future__ import annotations

import asyncio

from app.robot.client import MG400Client
from app.robot.mg400 import MG400Error, Reply


class EnlaceOcioso:
    """El primer `prepare` falla como un socket que el controlador cerró."""

    def __init__(self, fallos: int = 1) -> None:
        self.fallos = fallos
        self.prepares = 0
        self.cerrados = 0

    def prepare(self, percent: int = 20) -> None:
        self.prepares += 1
        if self.prepares <= self.fallos:
            raise MG400Error("RobotMode devolvio -99999")

    def dashboard(self, command: str) -> Reply:
        return Reply(0, "")

    def move(self, command: str) -> Reply:
        return Reply(0, "")

    def sync(self) -> None:
        return None

    def errors(self) -> str:
        return ""

    def pose(self) -> tuple[float, float, float, float]:
        return (279.24, -27.20, -95.0, 120.57)

    def close(self) -> None:
        self.cerrados += 1


def _cliente(enlace: EnlaceOcioso) -> MG400Client:
    async def dormir(_segundos: float) -> None:
        return None

    return MG400Client(
        link=enlace,
        z_draw=-97.0,
        z_travel=-90.0,
        sleep=dormir,
    )


def test_connect_reintenta_si_el_socket_estaba_ocioso() -> None:
    enlace = EnlaceOcioso()
    cliente = _cliente(enlace)

    asyncio.run(cliente.connect())

    assert enlace.prepares == 2
    assert enlace.cerrados >= 1
    assert cliente._ready is True


def test_connect_no_reintenta_para_siempre() -> None:
    enlace = EnlaceOcioso(fallos=99)
    cliente = _cliente(enlace)

    try:
        asyncio.run(cliente.connect())
    except MG400Error:
        pass
    else:  # pragma: no cover - si no falla, el test no sirve
        raise AssertionError("connect debía rendirse")

    assert enlace.prepares == cliente.connect_retries
    assert cliente._ready is False
