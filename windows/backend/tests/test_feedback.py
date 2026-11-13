"""El paquete del 30004 se entiende y el lector entrega estado fresco o nada."""

import socket
import struct
import threading
import time

from app.robot import feedback as feedback_ops
from app.robot.client import MG400Client


def _paquete(
    *,
    mode: int = 5,
    pose: tuple[float, float, float, float] = (300.0, -20.0, -60.0, 10.0),
    joints: tuple[float, float, float, float] = (30.0, 10.0, -20.0, -50.0),
    di: int = 0b101,
    do: int = 0b11,
    error: int = 0,
) -> bytes:
    buf = bytearray(feedback_ops.PACKET_SIZE)
    struct.pack_into("<h", buf, 0, feedback_ops.PACKET_SIZE)
    struct.pack_into("<q", buf, 8, di)
    struct.pack_into("<q", buf, 16, do)
    struct.pack_into("<q", buf, 24, mode)
    struct.pack_into("<6d", buf, 432, joints[0], joints[1], joints[2], joints[3], 0.0, 0.0)
    struct.pack_into("<6d", buf, 624, pose[0], pose[1], pose[2], 0.0, 0.0, pose[3])
    struct.pack_into("<b", buf, 1029, error)
    return bytes(buf)


def test_paquete_valido_da_modo_pose_y_bits():
    parsed = feedback_ops.parse_packet(_paquete())
    assert parsed is not None
    assert parsed["mode"] == 5
    assert parsed["pose"] == [300.0, -20.0, -60.0, 10.0]
    assert parsed["angles"] == [30.0, 10.0, -20.0, -50.0]
    assert parsed["di_bits"] == 0b101
    assert parsed["do_bits"] == 0b11
    assert parsed["error"] == 0


def test_paquete_corto_o_corrido_se_rechaza():
    assert feedback_ops.parse_packet(b"") is None
    assert feedback_ops.parse_packet(bytes(feedback_ops.PACKET_SIZE)) is None
    corrido = bytearray(_paquete())
    struct.pack_into("<h", corrido, 0, 0)
    assert feedback_ops.parse_packet(bytes(corrido)) is None


class Servidor:
    """Controlador de mentira: escupe el paquete cada 20 ms hasta que se cierra."""

    def __init__(self, packet: bytes) -> None:
        self.packet = packet
        self._stop = threading.Event()
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self._thread = threading.Thread(target=self._sirvo, daemon=True)
        self._thread.start()

    def _sirvo(self) -> None:
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    conn.sendall(self.packet)
                except OSError:
                    return
                self._stop.wait(0.02)

    def close(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


def test_lector_entrega_y_caduca():
    servidor = Servidor(_paquete(mode=7))
    lector = feedback_ops.FeedbackReader("127.0.0.1", servidor.port, stale_s=0.4, retry_s=0.1)
    lector.start()
    try:
        visto = None
        limite = time.monotonic() + 3.0
        while time.monotonic() < limite:
            visto = lector.snapshot()
            if visto is not None:
                break
            time.sleep(0.02)
        assert visto is not None and visto["mode"] == 7
        servidor.close()
        caducado = None
        limite = time.monotonic() + 3.0
        while time.monotonic() < limite:
            caducado = lector.snapshot()
            if caducado is None:
                break
            time.sleep(0.05)
        assert caducado is None
    finally:
        lector.stop()
        servidor.close()


def test_lector_sin_robot_devuelve_none():
    cerrado = socket.socket()
    cerrado.bind(("127.0.0.1", 0))
    puerto_libre = cerrado.getsockname()[1]
    cerrado.close()
    lector = feedback_ops.FeedbackReader("127.0.0.1", puerto_libre, retry_s=5.0)
    lector.start()
    try:
        time.sleep(0.5)
        assert lector.snapshot() is None
    finally:
        lector.stop()


def test_cliente_sin_socket_no_escucha_feedback():
    class Enlace:
        def dashboard(self, command: str) -> object:
            from app.robot.mg400 import Reply

            return Reply(code=0, value="")

    cliente = MG400Client(link=Enlace(), z_draw=-65.0, z_travel=-57.0)
    assert cliente.feedback_status() is None
