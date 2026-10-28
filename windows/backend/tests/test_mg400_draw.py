"""El MG400 dibuja la trayectoria con el lapiz arriba entre trazos, sin abrir el socket en seco."""

import asyncio
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.robot.client import MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import MG400Error, Reply  # noqa: E402


class EnlaceFalso:
    """Registra ordenes. No abre sockets."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.dashboard_cmds: list[str] = []
        self.prepared: int | None = None

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        self.dashboard_cmds.append(command)
        return Reply(code=0, value="")

    def prepare(self, percent: int = 20) -> None:
        self.prepared = percent

    def sync(self) -> None:
        self.move("Sync()")

    def pose(self) -> tuple[float, float, float, float]:
        return (0.0, 0.0, 0.0, 0.0)


def _cliente(enlace: EnlaceFalso) -> MG400Client:
    return MG400Client(
        link=enlace,
        host="192.168.10.55",
        user=1,
        tool=2,
        z_draw=-188.0,
        z_travel=-180.0,
        r=12.0,
        speed_factor=20,
        origin_x=100.0,
        origin_y=240.0,
        x_sign=1,
        y_sign=-1,
    )


def _trayectoria() -> Trajectory:
    return Trajectory(
        segments=[
            Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]]),
            Segment(type="travel", points=[[10.0, 0.0], [0.0, 20.0]]),
            Segment(type="draw", points=[[0.0, 20.0], [10.0, 20.0]]),
        ],
        width_mm=100.0,
        height_mm=40.0,
    )


def _xyz(command: str) -> tuple[float, float, float]:
    match = re.match(r"MovL\(([^,]+),([^,]+),([^,]+),", command)
    assert match, command
    return tuple(float(part) for part in match.groups())  # type: ignore[return-value]


def test_baja_sobre_el_trazo_y_viaja_en_alto():
    enlace = EnlaceFalso()
    cliente = _cliente(enlace)

    async def correr() -> None:
        await cliente.connect()

        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(_trayectoria(), progreso)

    asyncio.run(correr())

    assert enlace.prepared == 20
    assert "User(1)" in enlace.dashboard_cmds
    assert "Tool(2)" in enlace.dashboard_cmds
    movimientos = [orden for orden in enlace.moves if orden.startswith("MovL")]
    assert [_xyz(orden) for orden in movimientos] == [
        (100.0, 240.0, -180.0),  # acercarse al primer punto, lapiz arriba
        (100.0, 240.0, -188.0),  # bajar
        (110.0, 240.0, -188.0),  # dibujar
        (110.0, 240.0, -180.0),  # subir
        (100.0, 220.0, -180.0),  # viajar
        (100.0, 220.0, -188.0),  # bajar
        (110.0, 220.0, -188.0),  # dibujar
        (110.0, 220.0, -180.0),  # dejar el lapiz arriba al terminar
    ]
    for anterior, orden in zip(movimientos, movimientos[1:]):
        if _xyz(anterior)[2] != _xyz(orden)[2]:
            assert "CP=1" in orden
    assert all(",12.000," in orden for orden in movimientos)
    assert enlace.moves[-1] == "Sync()"


def test_un_punto_en_cero_no_se_manda_como_cero():
    """Y=0 parte la hoja (92 mm bajo el origen). El controlador marca error si el blanco es 0."""
    enlace = EnlaceFalso()
    cliente = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
        x_sign=-1,
        y_sign=-1,
    )
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 92.0], [10.0, 92.0]])],
        width_mm=140.0,
        height_mm=240.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())
    for orden in enlace.moves:
        if not orden.startswith("MovL"):
            continue
        x, y, z = _xyz(orden)
        assert x != 0 and y != 0 and z != 0
        assert ",0.000," not in orden


def test_las_esquinas_medidas_caen_en_el_papel():
    """Superior izquierda (360, 92) y, 142 x 237 mm despues, inferior derecha (218, -145)."""
    enlace = EnlaceFalso()
    cliente = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=360.0,
        origin_y=92.0,
    )
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [142.0, 237.0]])],
        width_mm=142.0,
        height_mm=237.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())
    movimientos = [orden for orden in enlace.moves if orden.startswith("MovL")]
    assert _xyz(movimientos[0]) == (360.0, 92.0, -160.0)
    assert _xyz(movimientos[1]) == (360.0, 92.0, -167.0)
    assert _xyz(movimientos[2]) == (218.0, -145.0, -167.0)
    assert ",145.000," in movimientos[2]


def test_el_giro_llega_a_96_en_la_esquina_lejana():
    enlace = EnlaceFalso()
    cliente = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        r_far=96.0,
        far_x=218.0,
        far_y=-145.0,
        origin_x=360.0,
        origin_y=92.0,
    )
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [142.0, 237.0]])],
        width_mm=142.0,
        height_mm=237.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    asyncio.run(correr())
    movimientos = [orden for orden in enlace.moves if orden.startswith("MovL")]
    assert ",145.000," in movimientos[0]
    assert ",96.000," in movimientos[2]


class _EnlaceQueFalla:
    def __init__(self) -> None:
        self.closed = False
        self.prepared = 0

    def move(self, command: str) -> Reply:
        if command.startswith("MovL"):
            return Reply(code=-99999, value="")
        return Reply(code=0, value="")

    def dashboard(self, _command: str) -> Reply:
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        self.prepared += 1

    def sync(self) -> None:
        return None

    def errors(self) -> str:
        return "9"

    def close(self) -> None:
        self.closed = True


def test_un_fallo_suelta_el_socket_para_el_siguiente_dibujo():
    enlace = _EnlaceQueFalla()
    cliente = MG400Client(link=enlace, z_draw=-167.0, z_travel=-160.0, r=145.0)
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [5.0, 0.0]])],
        width_mm=10.0,
        height_mm=10.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    with pytest.raises(MG400Error, match="sin respuesta"):
        asyncio.run(correr())
    assert enlace.closed
    assert cliente._ready is False
    assert cliente._link is None


def test_rechaza_un_punto_fuera_del_papel_sin_mover():
    enlace = EnlaceFalso()
    cliente = _cliente(enlace)
    fuera = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [150.0, 0.0]])],
        width_mm=140.0,
        height_mm=180.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(fuera, progreso)

    with pytest.raises(MG400Error):
        asyncio.run(correr())
    assert enlace.moves == []
    assert enlace.prepared is None


def test_el_modo_seco_no_abre_el_socket(monkeypatch: pytest.MonkeyPatch):
    def no_conectar(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("el modo seco no abre socket")

    monkeypatch.setattr("app.robot.mg400.MG400Link", no_conectar)
    cliente = MG400Client(dry_run=True, host="192.168.10.55", z_draw=1.0, z_travel=6.0, r=0.0)

    async def correr() -> None:
        await cliente.connect()

        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(
            Trajectory(
                segments=[Segment(type="draw", points=[[0.0, 0.0], [5.0, 0.0]])],
                width_mm=10.0,
                height_mm=10.0,
            ),
            progreso,
        )

    asyncio.run(correr())
    assert any(orden.startswith("MovL") for orden in cliente.commands)
    assert cliente.commands[-1] == "Sync()"


def test_la_ip_por_defecto_es_la_del_robot(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ROBOT_HOST", raising=False)
    monkeypatch.setenv("ROBOT_DRY_RUN", "1")
    monkeypatch.delenv("ROBOT_Z_DRAW", raising=False)
    monkeypatch.delenv("ROBOT_Z_TRAVEL", raising=False)
    cliente = MG400Client.from_env()
    assert cliente.host == "192.168.10.55"
    assert cliente.dry_run is True


def test_sin_alturas_no_arma_el_cliente_real(monkeypatch: pytest.MonkeyPatch):
    for name in ("ROBOT_HOST", "ROBOT_Z_DRAW", "ROBOT_Z_TRAVEL", "ROBOT_DRY_RUN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.robot.client._dotenv", lambda: {})
    with pytest.raises(MG400Error):
        MG400Client.from_env()


def test_sin_backend_sigue_el_simulador(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ROBOT_BACKEND", raising=False)
    monkeypatch.setattr("app.robot.client._dotenv", lambda: {})
    from app.robot.client import robot_from_env

    assert robot_from_env().name == "mock"


def test_backend_mg400_usa_el_cliente_real(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ROBOT_BACKEND", "mg400")
    monkeypatch.setenv("ROBOT_DRY_RUN", "1")
    monkeypatch.delenv("ROBOT_HOST", raising=False)
    from app.robot.client import robot_from_env

    cliente = robot_from_env()
    assert cliente.name == "mg400"
    assert cliente.host == "192.168.10.55"


def test_el_archivo_env_elige_el_mg400_en_seco(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ROBOT_BACKEND", raising=False)
    monkeypatch.delenv("ROBOT_DRY_RUN", raising=False)
    monkeypatch.delenv("ROBOT_HOST", raising=False)
    monkeypatch.setattr(
        "app.robot.client._dotenv",
        lambda: {"ROBOT_BACKEND": "mg400", "ROBOT_DRY_RUN": "1"},
    )
    from app.robot.client import robot_from_env

    cliente = robot_from_env()
    assert cliente.name == "mg400"
    assert cliente.host == "192.168.10.55"
    assert cliente.dry_run is True
