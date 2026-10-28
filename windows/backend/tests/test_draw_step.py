"""Dibujo sin Sync y con pasos largos.

Medido en el MG400 real: mandar ~1700 MovL seguidos, o llamar a Sync() una
sola vez, tumba el socket de movimiento (y a veces deja el controlador en
alarma 9 hasta reiniciarlo a mano). Lo único que aguantó 40 órdenes seguidas
fue mandar una orden y esperar a que el brazo llegue de verdad. Con pasos
cortos eso da 2.4 mm/s; con pasos de 6 mm sube a ~10 mm/s.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+)")


class Enlace:
    """Enlace falso: la pose es el último destino que se le mandó."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.target = (0.0, 0.0, 0.0, 0.0)

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        found = MOVL.search(command)
        if found:
            self.target = (float(found.group(1)), float(found.group(2)), float(found.group(3)), 0.0)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        self.moves.append("Sync()")

    def errors(self) -> str:
        return ""

    def pose(self) -> tuple[float, float, float, float]:
        return self.target


def _cliente(enlace: Enlace) -> MG400Client:
    return MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=100.0,
        origin_y=100.0,
        x_sign=1,
        y_sign=1,
        queue_retry_s=0.0,
        pace_lead_s=0.0,
        min_step_mm=6.0,
        pipeline=1,
    )


def _trazar(cliente: MG400Client, puntos: list[list[float]]) -> None:
    papel = Trajectory(segments=[Segment(type="draw", points=puntos)], width_mm=40.0, height_mm=40.0)

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())


def test_los_puntos_pegados_se_colapsan():
    enlace = Enlace()
    # 10 puntos cada 1.5 mm: 13.5 mm de trazo. Con paso mínimo de 6 mm solo
    # deben quedar 0, 6, 12 y el final (13.5): 4 comandos en vez de 10.
    puntos = [[i * 1.5, 0.0] for i in range(10)]
    _trazar(_cliente(enlace), puntos)

    movimientos = [move for move in enlace.moves if "CP=100" in move]
    assert len(movimientos) <= 4


def test_el_dibujo_termina_sin_sync():
    enlace = Enlace()
    puntos = [[i * 6.0, 0.0] for i in range(4)]
    _trazar(_cliente(enlace), puntos)

    assert not any("Sync()" in move for move in enlace.moves)


def test_cada_orden_espera_la_llegada_del_brazo():
    """La pose se lee después de mover: sin eso el controlador corta a los 2-3 s."""
    enlace = Enlace()
    leidas: list[tuple[float, float, float, float]] = []

    def pose_espia() -> tuple[float, float, float, float]:
        leidas.append(enlace.target)
        return enlace.target

    enlace.pose = pose_espia  # type: ignore[method-assign]
    puntos = [[i * 6.0, 0.0] for i in range(4)]
    _trazar(_cliente(enlace), puntos)

    assert len(leidas) >= 4


def test_una_conexion_caida_se_reconecta_y_sigue():
    """Medido: el controlador se cae a media obra pero queda sano al reconectar."""

    class EnlaceQueSeCae(Enlace):
        def __init__(self) -> None:
            super().__init__()
            self.caidas = 0
            self.prepares = 0

        def prepare(self, _percent: int = 20) -> None:
            self.prepares += 1

        def move(self, command: str) -> Reply:
            if self.caidas == 0 and "CP=100" in command and len(self.moves) > 3:
                self.caidas += 1
                return Reply(code=-99999, value="")
            return super().move(command)

    enlace = EnlaceQueSeCae()
    puntos = [[i * 6.0, 0.0] for i in range(6)]
    _trazar(_cliente(enlace), puntos)

    assert enlace.caidas == 1
    assert enlace.prepares >= 2
    dibujo = [move for move in enlace.moves if "CP=100" in move]
    assert len(dibujo) >= 5
