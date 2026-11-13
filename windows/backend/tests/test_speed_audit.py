"""Lo que hacía lento el retrato: esperas de colchón, cola vacía y el panel."""

import asyncio
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import archive as archive_ops  # noqa: E402
from app import main  # noqa: E402
from app.admin_ops import drop_tokens, issue_token  # noqa: E402
from app.robot import busy  # noqa: E402
from app.robot.client import MG400Client, Segment, Trajectory  # noqa: E402
from app.robot.mg400 import Reply  # noqa: E402

MOVL = re.compile(r"MovL\(([-\d.]+),([-\d.]+),([-\d.]+)")


class EnlaceVeloz:
    """El brazo recorta cada esquina y se planta en la última orden de la cola."""

    def __init__(self) -> None:
        self.moves: list[str] = []
        self.dashboards: list[str] = []
        self.poses = 0
        self._fin = (30.0, 30.0, -160.0, 0.0)

    def move(self, command: str) -> Reply:
        self.moves.append(command)
        found = MOVL.search(command)
        if found:
            self._fin = (float(found.group(1)), float(found.group(2)), float(found.group(3)), 0.0)
        return Reply(code=0, value="")

    def dashboard(self, command: str) -> Reply:
        self.dashboards.append(command)
        if command.strip().startswith("RobotMode"):
            return Reply(code=0, value="5")
        return Reply(code=0, value="")

    def prepare(self, _percent: int = 20) -> None:
        return None

    def sync(self) -> None:
        return None

    def errors(self) -> str:
        return ""

    def pose(self) -> tuple[float, float, float, float]:
        self.poses += 1
        return self._fin


async def _nada(_valor: float, _segmento: Segment) -> None:
    return None


def _zigzag() -> Trajectory:
    puntos = [[i * 4.0, 0.0 if i % 2 == 0 else 4.0] for i in range(16)]
    return Trajectory(
        segments=[
            Segment(type="draw", points=puntos),
            Segment(type="travel", points=[puntos[-1], [10.0, 40.0]]),
            Segment(type="draw", points=[[10.0, 40.0], [30.0, 40.0]]),
        ],
        width_mm=140.0,
        height_mm=140.0,
    )


def test_la_cola_vacia_no_espera_el_colchon_en_cada_esquina() -> None:
    """La punta nunca pisa una esquina recortada. Si cada una espera los 6 s,
    un zigzag de 16 vértices se queda pensando más de un minuto."""
    enlace = EnlaceVeloz()
    cliente = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=30.0,
        origin_y=30.0,
        wait_arrival=True,
        arrival_extra_s=6.0,
        arrival_poll_s=0.005,
        min_step_mm=0.0,
        join_gap_mm=0.0,
        pace_lead_s=10.0,
    )

    started = time.perf_counter()
    asyncio.run(cliente.draw(_zigzag(), _nada))
    elapsed = time.perf_counter() - started

    stats = cliente.motion_stats
    assert elapsed < 2.0, f"se quedó quieto {elapsed:.1f} s"
    assert stats["timeouts"] == 0
    assert stats["long_waits"] == 0
    assert stats["pose_reads"] > 0


def test_subir_y_viajar_no_paran_el_brazo_dos_veces() -> None:
    """Subir y viajar se encolan juntos; solo bajar espera la llegada."""
    enlace = EnlaceVeloz()
    cliente = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=30.0,
        origin_y=30.0,
        wait_arrival=False,
        min_step_mm=0.0,
        join_gap_mm=0.0,
        pace_lead_s=10.0,
    )
    asyncio.run(cliente.draw(_zigzag(), _nada))

    alturas = [float(MOVL.search(move).group(3)) for move in enlace.moves if MOVL.search(move)]
    assert -160.0 in alturas and -167.0 in alturas
    # La muñeca no se revisa en cada viaje: eso vaciaba la cola 50 veces.
    assert sum(1 for cmd in enlace.dashboards if cmd.startswith("GetAngle")) <= 1


def test_el_dibujo_vuelve_al_speedfactor_global() -> None:
    enlace = EnlaceVeloz()
    cliente = MG400Client(
        link=enlace,
        z_draw=-167.0,
        z_travel=-160.0,
        r=0.0,
        origin_x=30.0,
        origin_y=30.0,
        wait_arrival=False,
        global_speed=100,
    )
    asyncio.run(cliente.draw(_zigzag(), _nada))
    assert "SpeedFactor(100)" in enlace.dashboards


class RobotOcupado:
    name = "mg400"
    last_pose = (300.0, 10.0, -160.0, 40.0)

    def __init__(self) -> None:
        self.preguntas: list[str] = []

    async def ask(self, command: str, move: bool = False) -> tuple[int, str]:
        self.preguntas.append(command)
        return 0, "{5}"


def test_el_panel_no_le_pregunta_al_robot_mientras_dibuja(monkeypatch) -> None:
    falso = RobotOcupado()
    monkeypatch.setattr(main, "robot", falso)
    monkeypatch.setattr(main, "booth_from_client", lambda _robot: {})
    drop_tokens()
    token = issue_token()
    busy.enter()
    try:
        data = asyncio.run(main.admin_status(x_admin_token=token))
    finally:
        busy.leave()

    assert falso.preguntas == []
    assert data["busy"] is True
    assert data["pose"] == [300.0, 10.0, -160.0, 40.0]


def test_el_trabajo_queda_en_el_meta_de_la_visita(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(archive_ops, "ARCHIVE_DIR", tmp_path)
    folder = tmp_path / "20261103_120000_sk_0123456789"
    folder.mkdir()
    (folder / "meta.json").write_text(json.dumps({"id": "sk_0123456789"}), encoding="utf-8")

    assert archive_ops.record_job("sk_0123456789", {"seconds": 90.0, "motion": {"timeouts": 0}})

    data = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    assert data["job"]["seconds"] == 90.0
    assert archive_ops.record_job("sk_ffffffffff", {}) is False
