"""El control mueve X, Y y Z juntos y conserva el J4 que giró la palanca derecha."""

import asyncio
import math
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main  # noqa: E402
from app.admin_ops import drop_tokens, issue_token  # noqa: E402
from app.robot import busy  # noqa: E402
from app.robot.client import (  # noqa: E402
    J4_FIXED,
    MG400Client,
    PAD_J4_DEG,
    PAD_LEAD_S,
    PAD_SPEED_MM_S,
    PAD_STEP_MM,
    Segment,
    Trajectory,
    pad_deltas,
)
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+),")


class Enlace:
    def __init__(self) -> None:
        self.moves: list[str] = []
        self.dashboards: list[str] = []
        self.pose_value = (300.0, 10.0, -160.0, 40.0)
        self.angle_value = (20.0, 10.0, 30.0, -20.0)

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        self.dashboards.append(command)
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def pose(self) -> tuple[float, float, float, float]:
        return self.pose_value

    def angles(self) -> tuple[float, float, float, float]:
        return self.angle_value

    def sync(self) -> None:
        return None

    def errors(self) -> str:
        return ""


def _cliente(enlace: Enlace) -> MG400Client:
    return MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=300.0,
        origin_y=0.0,
        wait_arrival=False,
        min_step_mm=0.0,
        pace_lead_s=10.0,
    )


def _r(command: str) -> float:
    found = MOVL.search(command)
    assert found is not None
    return float(found.group(4))


def test_el_paso_cubre_distancia_y_la_cruceta_es_fija() -> None:
    assert pad_deltas(1, 0, 0, 0, 100) == (PAD_STEP_MM, 0.0, 0.0, 0.0)
    mitad = PAD_STEP_MM / 2
    assert pad_deltas(1, -1, 0.5, 0, 50) == (mitad, -mitad, mitad / 2, 0.0)
    # Una palanca fuera de ±1 no pide más que un paso.
    assert pad_deltas(5, 0, 0, 0, 100) == (PAD_STEP_MM, 0.0, 0.0, 0.0)
    assert pad_deltas(-1, 0, 0, 1, 100, mm=1) == (-1.0, 0.0, 0.0, 0.0)
    assert pad_deltas(0, 0, 0, 0, 80) is None


def test_la_palanca_quieta_no_manda_movimiento() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    assert asyncio.run(cliente.pad_nudge(0, 0, 0, 0, 50)) is None
    assert enlace.moves == []
    assert enlace.dashboards == []


def test_el_movl_conserva_un_j4_distinto_de_menos_50() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    asyncio.run(cliente.pad_nudge(0, 0, 0, 1, 100))
    assert cliente.pad_j4 == pytest.approx(-20.0 + PAD_J4_DEG)
    esperado = math.degrees(math.atan2(10.0, 300.0)) + (-20.0 + PAD_J4_DEG)
    assert _r(enlace.moves[-1]) == pytest.approx(esperado, abs=0.01)
    assert _r(enlace.moves[-1]) != pytest.approx(J4_FIXED, abs=0.5)
    assert "SpeedFactor(100)" in enlace.dashboards
    assert enlace.moves[-1].endswith("SpeedL=100,AccL=100,CP=100)")

    asyncio.run(cliente.pad_nudge(0, 0, 0, 1, 100))
    assert cliente.pad_j4 == pytest.approx(-20.0 + 2 * PAD_J4_DEG)
    # El global se fija una vez por gesto, no en cada paso.
    assert enlace.dashboards.count("SpeedFactor(100)") == 1

    # Mover en X no devuelve la muñeca a -50 y sale del último punto, no de la pose.
    asyncio.run(cliente.pad_nudge(1, 0, 0, 0, 100))
    destino = 300.0 + PAD_STEP_MM
    mantenido = math.degrees(math.atan2(10.0, destino)) + (-20.0 + 2 * PAD_J4_DEG)
    assert _r(enlace.moves[-1]) == pytest.approx(mantenido, abs=0.01)
    assert cliente.pad_j4 == pytest.approx(-20.0 + 2 * PAD_J4_DEG)


def test_j4_no_pasa_de_170() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    cliente.pad_j4 = 169.0
    asyncio.run(cliente.pad_nudge(0, 0, 0, 1, 100))
    assert cliente.pad_j4 == 170.0
    antes = len(enlace.moves)
    assert asyncio.run(cliente.pad_nudge(0, 0, 0, 1, 100)) is None
    assert len(enlace.moves) == antes
    assert cliente.pad_j4 == 170.0


def test_con_modelo_j4_la_r_es_el_angulo() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    cliente.r_model = "j4"
    cliente.pad_j4 = -17.0
    asyncio.run(cliente.pad_nudge(1, 0, 0, 0, 100))
    assert _r(enlace.moves[-1]) == pytest.approx(-17.0)


def test_el_paro_no_devuelve_j4() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    cliente.pad_j4 = -17.0
    cliente._pad_factor_set = True
    cliente._pad_target = (300.0, 10.0, -160.0)
    cliente._pad_due = 1.0
    code, _value = asyncio.run(cliente.pad_stop())
    assert code == 0
    assert enlace.moves == ["Stop()"]
    assert cliente.pad_j4 == -17.0
    assert cliente._pad_factor_set is False
    assert cliente._pad_target is None
    assert cliente._pad_due is None


def test_no_manda_el_brazo_contra_la_columna() -> None:
    enlace = Enlace()
    enlace.pose_value = (200.0, 0.0, -160.0, 40.0)
    cliente = _cliente(enlace)
    asyncio.run(cliente.pad_nudge(-1, 0, 0, 0, 100))
    assert enlace.moves[-1].startswith("MovL(170.000,")
    # Ya en el borde, seguir hacia adentro no manda otro punto.
    assert asyncio.run(cliente.pad_nudge(-1, 0, 0, 0, 100)) is None
    assert len(enlace.moves) == 1


def test_una_pose_en_el_origen_no_se_manda() -> None:
    enlace = Enlace()
    enlace.pose_value = (0.0, 0.0, 0.0, 0.0)
    cliente = _cliente(enlace)
    assert asyncio.run(cliente.pad_nudge(1, 0, 0, 0, 100)) is None
    assert enlace.moves == []


def test_el_segundo_paso_no_relee_la_pose() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    lecturas = 0

    def contar() -> tuple[float, float, float, float]:
        nonlocal lecturas
        lecturas += 1
        return enlace.pose_value

    enlace.pose = contar  # type: ignore[method-assign]
    asyncio.run(cliente.pad_nudge(1, 0, 0, 0, 100))
    enlace.pose_value = (0.0, 0.0, -160.0, 40.0)
    asyncio.run(cliente.pad_nudge(1, 0, 0, 0, 100))
    assert lecturas == 1
    assert enlace.moves[-1].startswith(f"MovL({300.0 + 2 * PAD_STEP_MM:.3f},10.000,")


def test_no_encola_mas_movimiento_del_que_cabe(monkeypatch: pytest.MonkeyPatch) -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    reloj = {"t": 1000.0}
    esperas: list[float] = []

    monkeypatch.setattr("app.robot.client.time.monotonic", lambda: reloj["t"])

    async def dormir(segundos: float) -> None:
        esperas.append(segundos)
        reloj["t"] += segundos

    cliente._sleep = dormir
    for _ in range(3):
        asyncio.run(cliente.pad_nudge(1, 0, 0, 0, 100))
    tramo = PAD_STEP_MM / PAD_SPEED_MM_S
    assert len(enlace.moves) == 3
    assert len(esperas) == 1
    assert esperas[0] == pytest.approx(2 * tramo - PAD_LEAD_S)


def test_un_dibujo_olvida_el_j4_del_control() -> None:
    enlace = Enlace()
    cliente = _cliente(enlace)
    cliente.pad_j4 = -17.0
    papel = Trajectory(
        segments=[Segment(type="draw", points=[[0.0, 0.0], [10.0, 0.0]])],
        width_mm=40.0,
        height_mm=40.0,
    )

    async def nada(_valor: float, _segmento: Segment) -> None:
        return None

    asyncio.run(cliente.draw(papel, nada))
    assert cliente.pad_j4 is None


def _token() -> str:
    drop_tokens()
    return issue_token()


def test_pad_se_niega_durante_un_dibujo(monkeypatch: pytest.MonkeyPatch) -> None:
    class Robot:
        name = "mg400"

        def __init__(self) -> None:
            self.nudge = 0

        async def pad_nudge(self, *_args: object, **_kwargs: object) -> str:
            self.nudge += 1
            return "MovL(0,0,0,0)"

    robot = Robot()
    monkeypatch.setattr(main, "robot", robot)
    busy.enter()
    try:
        with pytest.raises(main.HTTPException) as exc:
            asyncio.run(
                main.admin_command(
                    main.AdminCommand(action="pad", x=1, y=0, z=0, j4=0, speed=40),
                    x_admin_token=_token(),
                )
            )
    finally:
        busy.leave()
    assert exc.value.status_code == 409
    assert robot.nudge == 0


def test_padstop_no_llama_a_ensure_j4(monkeypatch: pytest.MonkeyPatch) -> None:
    class Robot:
        name = "mg400"

        def __init__(self) -> None:
            self.pad_j4: float | None = -17.0
            self.ensured = False

        async def pad_stop(self) -> tuple[int, str]:
            return 0, ""

        async def ensure_j4(self, lift: bool = True) -> bool:
            self.ensured = True
            return True

    robot = Robot()
    monkeypatch.setattr(main, "robot", robot)
    data = asyncio.run(
        main.admin_command(main.AdminCommand(action="padstop"), x_admin_token=_token())
    )
    assert data["command"] == "Stop()"
    assert robot.ensured is False
    assert robot.pad_j4 == -17.0


def test_j4_a_menos_50_olvida_el_angulo_del_control(monkeypatch: pytest.MonkeyPatch) -> None:
    class Robot:
        name = "mg400"

        def __init__(self) -> None:
            self.pad_j4: float | None = -17.0

        def clear_pad_j4(self) -> None:
            self.pad_j4 = None

        async def prepare_motion(self, _rate: int | None) -> None:
            return None

        async def ensure_j4(self, lift: bool = True) -> bool:
            return True

    robot = Robot()
    monkeypatch.setattr(main, "robot", robot)
    asyncio.run(main.admin_command(main.AdminCommand(action="j4home"), x_admin_token=_token()))
    assert robot.pad_j4 is None
