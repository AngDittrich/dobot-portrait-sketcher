"""El MG400 dibuja la trayectoria con el lapiz arriba entre trazos, sin abrir el socket en seco."""

import asyncio
import math
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
    return MG400Client(pace_lead_s=0.0, 
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        host="192.168.10.55",
        user=1,
        tool=2,
        z_draw=-188.0,
        z_travel=-180.0,
        r=12.0,
        speed_factor=20,
        origin_x=150.0,
        origin_y=220.0,
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


def _j4(command: str) -> float:
    """J4 que deja un MovL: R menos el J1 que exige ese X, Y."""
    match = re.match(r"MovL\(([^,]+),([^,]+),[^,]+,([^,]+),", command)
    assert match, command
    x, y, r = (float(part) for part in match.groups())
    return r - math.degrees(math.atan2(y, x))


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
    assert all(_j4(orden) == pytest.approx(-50.0, abs=0.01) for orden in movimientos)
    assert not any("Sync()" in move for move in enlace.moves)


def test_un_punto_en_cero_no_se_manda_como_cero():
    """Y=0 parte la hoja (92 mm bajo el origen). El controlador marca error si el blanco es 0."""
    enlace = EnlaceFalso()
    cliente = MG400Client(pace_lead_s=0.0, 
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=290.0,
        origin_y=-28.0,
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
    """Centro (289, -26.5) y, 142 x 237 mm despues, las esquinas (360, 92) y (218, -145)."""
    enlace = EnlaceFalso()
    cliente = MG400Client(pace_lead_s=0.0, 
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        origin_x=289.0,
        origin_y=-26.5,
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
    assert _j4(movimientos[2]) == pytest.approx(-50.0, abs=0.01)


def test_la_muneca_no_gira_al_dibujar():
    enlace = EnlaceFalso()
    cliente = MG400Client(pace_lead_s=0.0, 
        link=enlace,
        min_step_mm=0.0,
        wait_arrival=False,
        z_draw=-167.0,
        z_travel=-160.0,
        r=145.0,
        r_far=96.0,
        far_x=218.0,
        far_y=-145.0,
        origin_x=289.0,
        origin_y=-26.5,
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
    # El R del .env (145) y el lejano (96) no mandan: J4 queda en -50 en cada punto.
    assert all(_j4(orden) == pytest.approx(-50.0, abs=0.01) for orden in movimientos)


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
    cliente = MG400Client(pace_lead_s=0.0, link=enlace, z_draw=-167.0, z_travel=-160.0, r=145.0)
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


class _EnlaceQueFallaConDiagnostico(_EnlaceQueFalla):
    last_raw = b""

    def dashboard(self, command: str) -> Reply:
        respuestas = {
            "RobotMode()": Reply(code=0, value="9"),
            "GetErrorID()": Reply(code=0, value="[[22],[],[],[],[]]"),
            "GetPose()": Reply(code=0, value="250.0,28.9,-167.0,125.0"),
        }
        return respuestas.get(command, Reply(code=0, value=""))


def test_un_fallo_deja_el_diagnostico_en_el_log(caplog: pytest.LogCaptureFixture):
    enlace = _EnlaceQueFallaConDiagnostico()
    cliente = MG400Client(pace_lead_s=0.0, link=enlace, z_draw=-167.0, z_travel=-160.0, r=145.0)
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [5.0, 0.0]])],
        width_mm=10.0,
        height_mm=10.0,
    )

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(papel, progreso)

    with caplog.at_level("INFO", logger="robot"), pytest.raises(MG400Error):
        asyncio.run(correr())
    texto = caplog.text
    assert "MovL(" in texto
    assert "RobotMode()" in texto and "9" in texto
    assert "GetErrorID()" in texto and "[[22]" in texto
    assert "GetPose()" in texto


class _EnlaceLento(EnlaceFalso):
    def move(self, command: str) -> Reply:
        import time

        time.sleep(0.03)
        return super().move(command)


def test_una_respuesta_lenta_avisa_pero_no_corta(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.robot.client.SLOW_REPLY_S", 0.01)
    enlace = _EnlaceLento()
    cliente = _cliente(enlace)

    async def correr() -> None:
        async def progreso(_valor: float, _segmento: Segment) -> None:
            return None

        await cliente.draw(_trayectoria(), progreso)

    with caplog.at_level("INFO", logger="robot"):
        asyncio.run(correr())
    assert not any("Sync()" in move for move in enlace.moves)
    assert "tardo" in caplog.text


def test_el_movl_espera_lo_que_tarde_la_cola():
    """El controlador retiene la respuesta mientras la cola está llena: no es un fallo."""
    import socket
    import threading
    import time

    from app.robot.mg400 import MG400Link

    def servidor(retraso: float) -> tuple[socket.socket, int]:
        escucha = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        escucha.bind(("127.0.0.1", 0))
        escucha.listen(1)

        def atender() -> None:
            conexion, _ = escucha.accept()
            with conexion:
                while True:
                    datos = conexion.recv(1024)
                    if not datos:
                        return
                    time.sleep(retraso)
                    orden = datos.decode().strip()
                    conexion.sendall(f"0,{{}},{orden};".encode())

        threading.Thread(target=atender, daemon=True).start()
        return escucha, escucha.getsockname()[1]

    tablero, puerto_tablero = servidor(0.0)
    movimiento, puerto_movimiento = servidor(0.4)
    enlace = MG400Link(
        "127.0.0.1",
        dashboard_port=puerto_tablero,
        move_port=puerto_movimiento,
        timeout_s=0.1,
        move_timeout_s=3.0,
    )
    try:
        assert enlace.move("MovL(1,2,3,4)").ok
        assert enlace.last_raw.startswith(b"0,")
    finally:
        enlace.close()
        tablero.close()
        movimiento.close()


def test_dos_consultas_a_la_vez_abren_un_solo_socket(monkeypatch: pytest.MonkeyPatch):
    """El controlador rechaza al segundo cliente. El panel no puede abrir dos."""
    import time

    abiertos = 0

    class EnlaceLento:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            nonlocal abiertos
            abiertos += 1
            time.sleep(0.05)

        def prepare(self, _percent: int = 20) -> None:
            return None

        def dashboard(self, _command: str) -> Reply:
            return Reply(code=0, value="")

        def close(self) -> None:
            return None

    monkeypatch.setattr("app.robot.mg400.MG400Link", EnlaceLento)
    cliente = MG400Client(z_draw=-167.0, z_travel=-160.0, r=145.0, host="192.168.10.55")

    async def correr() -> None:
        await asyncio.gather(cliente.connect(), cliente.connect())

    asyncio.run(correr())
    assert abiertos == 1
    assert cliente._ready is True


def test_leer_el_estado_no_abre_el_puerto_de_movimiento():
    """Abrir el 30003 y dejarlo mudo hace que el controlador cierre el enlace."""
    import socket
    import threading

    from app.robot.mg400 import MG400Link

    tablero = socket.socket()
    tablero.bind(("127.0.0.1", 0))
    tablero.listen(1)
    movimiento = socket.socket()
    movimiento.bind(("127.0.0.1", 0))
    movimiento.listen(1)

    def atender() -> None:
        conexion, _ = tablero.accept()
        with conexion:
            while True:
                datos = conexion.recv(1024)
                if not datos:
                    return
                conexion.sendall(b"0,{5},RobotMode();")

    threading.Thread(target=atender, daemon=True).start()
    enlace = MG400Link(
        "127.0.0.1",
        dashboard_port=tablero.getsockname()[1],
        move_port=movimiento.getsockname()[1],
        timeout_s=0.4,
    )
    try:
        assert enlace.dashboard("RobotMode()").ok
        assert enlace._move is None
        movimiento.settimeout(0.2)
        with pytest.raises(socket.timeout):
            movimiento.accept()
    finally:
        enlace.close()
        tablero.close()
        movimiento.close()


def test_si_el_controlador_cierra_el_enlace_el_sondeo_lo_suelta():
    class Mudo:
        def dashboard(self, _command: str) -> Reply:
            raise ConnectionError("sin respuesta")

        def close(self) -> None:
            return None

    cliente = MG400Client(z_draw=-65.0, z_travel=-57.0, r=0.0, host="192.168.10.55")
    cliente._link = Mudo()
    cliente._ready = True

    with pytest.raises(ConnectionError):
        asyncio.run(cliente.ask("RobotMode()"))
    assert cliente._link is None
    assert cliente._ready is False


def test_el_plazo_del_movl_sale_del_entorno(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ROBOT_DRY_RUN", "1")
    monkeypatch.setenv("ROBOT_MOVE_TIMEOUT_S", "12")
    assert MG400Client.from_env().move_timeout_s == 12.0
    monkeypatch.delenv("ROBOT_MOVE_TIMEOUT_S")
    monkeypatch.setattr("app.robot.client._dotenv", lambda: {"ROBOT_DRY_RUN": "1"})
    assert MG400Client.from_env().move_timeout_s == 60.0


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
    cliente = MG400Client(pace_lead_s=0.0, dry_run=True, host="192.168.10.55", z_draw=1.0, z_travel=6.0, r=0.0)

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
    assert not any("Sync()" in orden for orden in cliente.commands)


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
