"""Varias órdenes en vuelo para esconder el costo por orden.

Medido en el MG400 real: cada MovL cuesta ~0.51 s y el dibujo completo tardó
431.9 s. La idea es mandar hasta `pipeline` órdenes de dibujo sin esperar la
llegada de cada una, manteniendo la cola muy corta (el controlador se cae con
flujo continuo). Los cambios de altura del lápiz siempre se hacen con la cola
vacía: bajar el lápiz mientras el brazo todavía viaja dejaría una raya de más.
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client, Segment, Trajectory, ya_paso  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+)")


class Enlace:
    """Enlace falso: la pose es el último destino que se le mandó."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.target = (0.0, 0.0, 0.0, 0.0)
        self.pendientes: list[tuple[float, float, float, float]] = []
        self.lecturas = 0
        self.lecturas_al_mover: list[int] = []

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        self.lecturas_al_mover.append(self.lecturas)
        found = MOVL.search(command)
        if found:
            self.target = (
                float(found.group(1)),
                float(found.group(2)),
                float(found.group(3)),
                0.0,
            )
            self.pendientes.append(self.target)
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
        """El brazo va llegando por orden: la primera pendiente ya está hecha."""
        self.lecturas += 1
        if self.pendientes:
            return self.pendientes.pop(0)
        return self.target


def _cliente(enlace: Enlace, pipeline: int = 3) -> MG400Client:
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
        pipeline=pipeline,
    )


def _trazar(cliente: MG400Client, segmentos: list[Segment]) -> None:
    papel = Trajectory(segments=segmentos, width_mm=80.0, height_mm=80.0)

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())


def test_manda_varias_ordenes_antes_de_esperar_la_llegada():
    enlace = Enlace()
    puntos = [[i * 6.0, 0.0] for i in range(8)]
    _trazar(_cliente(enlace), [Segment(type="draw", points=puntos)])

    dibujo = [i for i, move in enumerate(enlace.moves) if "CP=100" in move]
    lecturas = enlace.lecturas_al_mover
    # Entre la 2ª y la 3ª orden de dibujo no se esperó; entre la 3ª y la 4ª sí:
    # la cola llegó a `pipeline` y hubo que soltar una.
    assert lecturas[dibujo[2]] == lecturas[dibujo[1]]
    assert lecturas[dibujo[3]] >= lecturas[dibujo[2]] + 1


def test_una_sola_orden_en_vuelo_si_pipeline_es_uno():
    enlace = Enlace()
    puntos = [[i * 6.0, 0.0] for i in range(4)]
    _trazar(_cliente(enlace, pipeline=1), [Segment(type="draw", points=puntos)])

    dibujo = [i for i, move in enumerate(enlace.moves) if "CP=100" in move]
    assert enlace.lecturas_al_mover[dibujo[1]] >= 1


def test_la_cola_queda_vacia_antes_de_cambiar_de_altura():
    enlace = Enlace()
    trazado = Segment(type="draw", points=[[i * 6.0, 0.0] for i in range(5)])
    paseo = Segment(type="travel", points=[[30.0, 30.0]])
    _trazar(_cliente(enlace), [trazado, paseo])

    subida = next(
        i
        for i, move in enumerate(enlace.moves)
        if ",-160.000," in move and any("CP=100" in prev for prev in enlace.moves[:i])
    )
    # Antes de levantar el lápiz se esperó lo que faltaba: la última orden de
    # dibujo ya no tenía ninguna pendiente.
    anteriores = [i for i, move in enumerate(enlace.moves[:subida]) if "CP=100" in move]
    # Después de la última orden de dibujo todavía se leyó la pose (para
    # vaciar la cola) antes de levantar el lápiz.
    assert enlace.lecturas_al_mover[subida] > enlace.lecturas_al_mover[anteriores[-1]]


def test_el_punto_ya_pasado_no_bloquea_la_espera():
    """Si el brazo ya dejó atrás el punto, esperar su llegada exacta es perder."""
    assert ya_paso(0.4, 3.0, 0.5) is True
    assert ya_paso(0.4, 1.0, 0.5) is False
