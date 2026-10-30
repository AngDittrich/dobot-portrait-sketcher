"""Ritmo de envío: no se debe llenar la cola del controlador.

El MG400 rechaza con -30000 cuando su cola está llena, y varios rechazos
seguidos le tumban el servicio TCP (hay que reiniciar el equipo). La cura no
es reintentar más rápido sino no llegar nunca al tope: mandar un poco más
lento de lo que el brazo consume, dejando un colchón de órdenes.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import (  # noqa: E402
    MG400Client,
    Segment,
    Trajectory,
    effective_speed_mm_s,
    fraction_along,
    pace_gap_s,
)
from app.robot.mg400 import Reply  # noqa: E402


def test_la_pose_lejos_del_final_no_completa_el_dibujo():
    """El porcentaje es la punta, no las órdenes ya encoladas."""
    points = [(0.0, 0.0, 0.0), (10.0, 0.0, 10.0), (20.0, 0.0, 20.0)]

    fraction, _cursor = fraction_along(points, (0.0, 0.0), 0, 0.5)
    assert fraction == 0.0

    fraction, _cursor = fraction_along(points, (10.0, 0.0), 0, 0.5)
    assert fraction == pytest.approx(0.5)

    fraction, cursor = fraction_along(points, (20.0, 0.0), 0, 0.5)
    assert fraction == 1.0
    assert cursor == len(points)

    # CP recorta la esquina: la punta pasa a 3 mm del vértice, no a 0.5.
    fraction, cursor = fraction_along(points, (10.0, 3.0), 0, 0.5)
    assert fraction == pytest.approx(0.5)
    assert cursor == 1

    fraction, _cursor = fraction_along(points, (0.0, 100.0), 0, 0.5)
    assert fraction == 0.0


def test_el_hueco_usa_la_velocidad_efectiva_medida():
    """17.3 mm a 20 mm/s es ~1 s de verdad: el firmware no llega a 20."""
    assert pace_gap_s(17.3, 20) == pytest.approx(1.0, abs=0.02)
    assert pace_gap_s(0.0, 20) == 0.0


def test_el_paso_corto_no_alcanza_la_velocidad_pedida():
    """Con pasos chicos manda la aceleración: v = sqrt(acc × paso).

    Medido en el MG400: AccL=100 y paso 1.5 mm dan ~12 mm/s, no los 20 que
    pide SpeedL. El ritmo tiene que usar esa velocidad real.
    """
    assert effective_speed_mm_s(1.5, 20, acc_mm_s2=100) == pytest.approx(12.25, abs=0.05)
    # En un paso largo sí cabe la rampa y manda SpeedL.
    assert effective_speed_mm_s(40.0, 20, acc_mm_s2=100) == pytest.approx(20.0, abs=0.05)
    # Un paso de 1.5 mm tarda lo que dice la física: ~0.14 s.
    assert pace_gap_s(1.5, 20, acc_mm_s2=100) == pytest.approx(0.1417, abs=0.002)


class Reloj:
    """Reloj y sleep falsos: el test no espera de verdad."""

    def __init__(self) -> None:
        self.now = 100.0
        self.dormido: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.dormido.append(seconds)
        self.now += seconds


class Enlace:
    def __init__(self) -> None:
        self.moves: list[str] = []

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        self.moves.append("Sync()")

    def errors(self) -> str:
        return ""


def test_el_envio_espera_para_no_pasar_el_colchon():
    reloj = Reloj()
    enlace = Enlace()
    cliente = MG400Client(
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
        queue_retry_s=0.0,
        pace_lead_s=1.0,
        clock=reloj,
        sleep=reloj.sleep,
    )
    # Movimiento virtual con la física real: bajar el lápiz 7 mm a 17.3 mm/s
    # (0.40 s) + 19 pasos de 1.7 mm a 11.3 mm/s (0.15 s cada uno = 2.86 s) +
    # subir el lápiz 7 mm (0.40 s) = 3.67 s. Con colchón de 1 s, la espera
    # total es ~2.67 s.
    puntos = [[i * 1.7, 0.0] for i in range(20)]
    papel = Trajectory(
        segments=[Segment(type="draw", points=puntos)],
        width_mm=40.0,
        height_mm=40.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())

    assert sum(reloj.dormido) == pytest.approx(2.67, abs=0.06)
    assert not any("Sync()" in move for move in enlace.moves)


def test_con_cp_alto_el_ritmo_no_se_apaga_aunque_la_pose_diga_que_ya_paso():
    """CP=100 recorta la esquina: la pose se aleja del punto antes de que el
    controlador consuma la orden. Si eso se toma como «ya llegó», el envío
    se vuelve continuo y el MG400 cierra el socket cerca de la orden 100.
    El colchón de un segundo tiene que seguir frenando el envío.
    """
    reloj = Reloj()
    enlace = Enlace()
    lejos = 0

    def pose() -> tuple[float, float, float, float]:
        nonlocal lejos
        lejos += 50.0
        return (1000.0 + lejos, 0.0, -167.0, 0.0)

    enlace.pose = pose  # type: ignore[attr-defined]
    cliente = MG400Client(
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=True,
        arrival_poll_s=0.0,
        pipeline=3,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
        queue_retry_s=0.0,
        pace_lead_s=1.0,
        clock=reloj,
        sleep=reloj.sleep,
    )
    puntos = [[i * 1.7, 0.0] for i in range(20)]
    papel = Trajectory(
        segments=[Segment(type="draw", points=puntos)],
        width_mm=40.0,
        height_mm=40.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())

    assert sum(reloj.dormido) == pytest.approx(2.67, abs=0.15)


def test_el_dibujo_expone_tiempos_y_ordenes_saltadas():
    """El log de una visita separa tinta, pluma arriba, cola y alcance."""
    enlace = Enlace()
    cliente = MG400Client(
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
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]])],
        width_mm=40.0,
        height_mm=40.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())

    assert cliente.motion_stats == {
        "draw_s": pytest.approx(0.0, abs=0.1),
        "air_s": pytest.approx(0.0, abs=0.1),
        "queue_s": pytest.approx(0.0, abs=0.1),
        "skipped_orders": 0,
    }


def test_el_dibujo_avisa_el_avance_mientras_traza():
    """El callback tiene que vivir durante el trazo. Si se apaga al armar
    el cliente, la hoja del visitante se queda en blanco hasta el «terminado»."""
    enlace = Enlace()
    cliente = MG400Client(
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
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])],
        width_mm=40.0,
        height_mm=40.0,
    )
    valores: list[float] = []

    async def correr() -> None:
        async def progreso(valor: float, _segmento: Segment) -> None:
            valores.append(valor)

        await cliente.draw(papel, progreso)

    asyncio.run(correr())

    assert valores, "el dibujo no publicó ningún avance"
    assert any(0.0 < valor < 1.0 for valor in valores)
    assert valores[-1] == pytest.approx(1.0)


def test_el_progreso_solo_cuenta_tinta_confirmada():
    cliente = MG400Client(
        link=Enlace(),
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
    )
    cliente._progress_total = 10.0
    cliente._progress_done = 0.0
    values: list[float] = []
    segment = Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]])

    async def report(value: float, _segment: Segment) -> None:
        values.append(value)

    async def correr() -> None:
        cliente._on_progress = report
        await cliente._record_progress(3.0, segment)
        # Enviar otra orden no llama al callback: solo su confirmación.
        await cliente._record_progress(7.0, segment)

    asyncio.run(correr())

    assert values == [pytest.approx(0.3), pytest.approx(1.0)]
