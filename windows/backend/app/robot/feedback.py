"""Lector del puerto 30004: estado del MG400 cada 8 ms, sin preguntar.

El controlador escupe un paquete binario de 1440 bytes varias veces por
segundo (pose, articulaciones, modo, entradas y salidas). El formato es el
de la demo oficial `TCP-IP-4Axis-Python` de Dobot (`MyType` en
`dobot_api.py`): enteros y flotantes en little-endian, sin numpy.

Sirve para que el sondeo del panel no tenga que mandar 4 comandos por el
dashboard en cada vuelta: con el último paquete fresco basta pedir las
alarmas (`GetErrorID`), que no vienen en el paquete.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time

logger = logging.getLogger("robot")

FEEDBACK_PORT = 30004
PACKET_SIZE = 1440
# Frescura máxima del paquete para fiarse de él: el controlador lo manda
# cada 8 ms, así que 1 s sin nada ya es enlace caído.
STALE_S = 1.0

# Desplazamientos dentro del paquete (ver `MyType` de la demo oficial).
_LEN_OFFSET = 0
_DI_BITS_OFFSET = 8
_DO_BITS_OFFSET = 16
_ROBOT_MODE_OFFSET = 24
_Q_ACTUAL_OFFSET = 432  # 6 × float64, las 4 primeras son J1..J4
_TOOL_VECTOR_OFFSET = 624  # 6 × float64: x, y, z, rx, ry, rz
_VEL_RATIO_OFFSET = 1016  # int8, porcentaje de velocidad articular
_XYZ_VEL_RATIO_OFFSET = 1019  # int8, porcentaje de velocidad cartesiana
_ERROR_STATUS_OFFSET = 1029  # int8, 0 es sin error


def parse_packet(data: bytes) -> dict | None:
    """Saca modo, pose, articulaciones y bits de E/S de un paquete.

    Devuelve None si el trozo no es un paquete entero: el lector, en ese
    caso, reconecta para volver a sincronizarse en vez de leer corrido.
    """
    if len(data) != PACKET_SIZE:
        return None
    (length,) = struct.unpack_from("<h", data, _LEN_OFFSET)
    if length != PACKET_SIZE:
        return None
    (di_bits,) = struct.unpack_from("<q", data, _DI_BITS_OFFSET)
    (do_bits,) = struct.unpack_from("<q", data, _DO_BITS_OFFSET)
    (mode,) = struct.unpack_from("<q", data, _ROBOT_MODE_OFFSET)
    joints = struct.unpack_from("<6d", data, _Q_ACTUAL_OFFSET)
    tool = struct.unpack_from("<6d", data, _TOOL_VECTOR_OFFSET)
    (vel_ratio,) = struct.unpack_from("<b", data, _VEL_RATIO_OFFSET)
    (xyz_vel_ratio,) = struct.unpack_from("<b", data, _XYZ_VEL_RATIO_OFFSET)
    (error,) = struct.unpack_from("<b", data, _ERROR_STATUS_OFFSET)
    return {
        "mode": int(mode),
        "pose": [float(tool[0]), float(tool[1]), float(tool[2]), float(tool[5])],
        "angles": [float(joint) for joint in joints[:4]],
        "di_bits": int(di_bits),
        "do_bits": int(do_bits),
        "error": int(error),
        "speed_ratio": int(vel_ratio),
        "xyz_speed_ratio": int(xyz_vel_ratio),
    }


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    """Lee justo `size` bytes o falla: el TCP puede partir el paquete."""
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("el controlador cerró el feedback")
        data += chunk
    return data


class FeedbackReader:
    """Hilo que mantiene el último paquete del puerto 30004.

    Nunca levanta: si no hay robot o se cae el enlace, `snapshot` devuelve
    None y el panel vuelve al sondeo por el dashboard. Reintenta solo en
    segundo plano, con pausas, para no martillar al controlador.
    """

    def __init__(
        self,
        host: str,
        port: int = FEEDBACK_PORT,
        stale_s: float = STALE_S,
        retry_s: float = 2.0,
    ) -> None:
        self._host = host
        self._port = port
        self._stale_s = stale_s
        self._retry_s = retry_s
        self._lock = threading.Lock()
        self._latest: dict | None = None
        self._stamp = 0.0
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="mg400-feedback", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Pide parar y cierra el socket; el hilo (daemon) sale solo.

        No se espera al hilo: `stop` se llama desde código asíncrono y
        bloquear el bucle sería peor que dejar morir el hilo en paz.
        """
        self._stop.set()
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def snapshot(self) -> dict | None:
        """Último estado si llegó hace poco. Copia: el hilo sigue escribiendo."""
        with self._lock:
            if self._latest is None or time.monotonic() - self._stamp > self._stale_s:
                return None
            return dict(self._latest)

    def _store(self, parsed: dict) -> None:
        with self._lock:
            self._latest = parsed
            self._stamp = time.monotonic()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._listen()
            except Exception as exc:  # noqa: BLE001 - el hilo no puede tumbar uvicorn
                if not self._stop.is_set():
                    logger.warning("feedback %s:%s: %s", self._host, self._port, exc)
            sock, self._sock = self._sock, None
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            if not self._stop.is_set():
                self._stop.wait(self._retry_s)

    def _listen(self) -> None:
        sock = socket.create_connection((self._host, self._port), timeout=3.0)
        sock.settimeout(3.0)
        self._sock = sock
        logger.info("feedback escuchando en %s:%s", self._host, self._port)
        while not self._stop.is_set():
            try:
                packet = _recv_exact(sock, PACKET_SIZE)
            except socket.timeout:
                continue
            parsed = parse_packet(packet)
            if parsed is None:
                # Llegó corrido: se reconecta y se vuelve a sincronizar.
                logger.warning("feedback con paquete inválido; reconectando")
                return
            self._store(parsed)
