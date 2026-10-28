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
        origin_x=30.0,
        origin_y=30.0,
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


def test_un_limite_del_brazo_se_salta_sin_reiniciar() -> None:
    class EnlaceEnLimite(EnlaceTrabado):
        def __init__(self) -> None:
            super().__init__()
            self.modo = 9

        def mode(self) -> int:
            return self.modo

        def errors(self) -> str:
            return "18" if self.modo == 9 else ""

        def dashboard(self, command: str) -> Reply:
            self.dashboards.append(command)
            if command.startswith("ClearError"):
                self.modo = 5
            if command.startswith("RobotMode"):
                return Reply(code=0, value=str(self.modo))
            return Reply(code=0, value="")

        def move(self, command: str) -> Reply:
            self.moves.append(command)
            if self.modo != 5:
                return Reply(code=0, value="")
            found = MOVL.search(command)
            if found:
                self.pose_fija = (
                    float(found.group(1)),
                    float(found.group(2)),
                    float(found.group(3)),
                    0.0,
                )
            return Reply(code=0, value="")

    enlace = EnlaceEnLimite()
    client = _cliente(enlace)
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])],
        width_mm=140.0,
        height_mm=140.0,
    )

    asyncio.run(client.draw(papel, _nada))

    assert not any("ResetRobot()" in command for command in enlace.dashboards)
    assert any(command.startswith("ClearError()") for command in enlace.dashboards)
    ilegal = [command for command in enlace.moves if "90.000,100.000" in command]
    assert len(ilegal) == 1
    assert not any("80.000,100.000" in command for command in enlace.moves)


def test_si_no_llega_no_sigue_mas_adentro() -> None:
    class EnlaceCorto(EnlaceTrabado):
        def __init__(self) -> None:
            super().__init__()
            self._pedido: tuple[float, float] | None = None
            self._lecturas = 0

        def move(self, command: str) -> Reply:
            self.moves.append(command)
            found = MOVL.search(command)
            if found:
                self._pedido = (float(found.group(1)), float(found.group(2)))
                self._lecturas = 0
            return Reply(code=0, value="")

        def pose(self) -> tuple[float, float, float, float]:
            if self._pedido is None:
                return self.pose_fija
            dx = self._pedido[0] - self.pose_fija[0]
            dy = self._pedido[1] - self.pose_fija[1]
            dist = (dx * dx + dy * dy) ** 0.5
            radio_pedido = (self._pedido[0] ** 2 + self._pedido[1] ** 2) ** 0.5
            radio_pose = (self.pose_fija[0] ** 2 + self.pose_fija[1] ** 2) ** 0.5
            self._lecturas += 1
            if dist > 0.5 and radio_pedido >= radio_pose - 0.1:
                self.pose_fija = (self._pedido[0], self._pedido[1], self.pose_fija[2], 0.0)
                return self.pose_fija
            if dist > 3 and self._lecturas == 2:
                self.pose_fija = (
                    self.pose_fija[0] + 2 * dx / dist,
                    self.pose_fija[1] + 2 * dy / dist,
                    self.pose_fija[2],
                    0.0,
                )
            return self.pose_fija

    enlace = EnlaceCorto()
    client = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=30.0,
        origin_y=30.0,
        speed_factor=100,
        pipeline=1,
        wait_arrival=True,
        arrival_extra_s=0.05,
        arrival_poll_s=0.01,
        min_step_mm=0.0,
        unstick_resets=1,
        unstick_sleep_s=0.0,
    )
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [40.0, 0.0], [80.0, 0.0]])],
        width_mm=140.0,
        height_mm=140.0,
    )

    asyncio.run(client.draw(papel, _nada))

    assert not any("ResetRobot()" in command for command in enlace.dashboards)
    assert sum("60.000,100.000" in command for command in enlace.moves) == 1
    assert not any("20.000,100.000" in command for command in enlace.moves)


def test_en_alarma_se_limpia_antes_de_habilitar() -> None:
    from app.robot.mg400 import MG400Error, MG400Link

    class Enlace(MG400Link):
        def __init__(self) -> None:
            self.comandos: list[str] = []
            self.last_raw = b""

        def mode(self) -> int:
            self.last_raw = b"0,{9},RobotMode();"
            return 9

        def _step(self, command: str) -> Reply:
            if command == "EnableRobot()" and "ClearError()" not in self.comandos:
                raise MG400Error("EnableRobot devolvio -1")
            self.comandos.append(command)
            return Reply(code=0, value="")

    enlace = Enlace()
    enlace.prepare(20)
    assert enlace.comandos.index("ClearError()") < enlace.comandos.index("EnableRobot()")
