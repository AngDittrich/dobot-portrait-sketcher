"""Enlace directo con el Dobot MG400 por TCP/IP.

El MG400 escucha tres puertos: 29999 (Dashboard, órdenes de estado y ajustes),
30003 (movimiento, cola de trayectorias) y 30004 (feedback continuo). Aquí se
usan los dos primeros; el feedback se lee aparte cuando haga falta.

Se habla el protocolo en crudo, sin SDK ni dependencias: la respuesta siempre
tiene la forma `codigo,{valor},Comando();`, con `codigo = 0` cuando salió bien.

Requiere que el robot esté en modo "TCP/IP Secondary development"; en el modo
de DobotStudio contesta `-1` a todo aunque el socket conecte.
"""

from __future__ import annotations

import logging
import re
import socket
import time
from dataclasses import dataclass

logger = logging.getLogger("robot")

DASHBOARD_PORT = 29999
MOVE_PORT = 30003
# Silencio tras el cual se da por terminada la respuesta: el robot no siempre
# cierra con salto de línea.
SILENCE_S = 0.12
# RobotMode() devuelve 5 cuando el robot está habilitado, 4 deshabilitado, 9 error.
MODE_ENABLED = 5
# El controlador rechaza la orden con este código cuando su cola de movimiento
# está llena. Es "espera", no un fallo: hay que reenviarla, no soltar el socket.
QUEUE_FULL_CODE = -30000


class MG400Error(RuntimeError):
    """El robot rechazó la orden (código distinto de 0)."""


@dataclass
class Reply:
    code: int
    value: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def _parse(raw: str) -> Reply:
    """Separa `codigo,{valor},Comando();` en sus dos partes útiles."""
    raw = raw.strip()
    if not raw:
        return Reply(code=-99999, value="")
    head, _, rest = raw.partition(",")
    try:
        code = int(head)
    except ValueError:
        # El controlador también contesta códigos negativos pegados al eco de la
        # orden, sin coma: `-30000MovL(...);`. Si se descarta ese número, el
        # error real (cola llena) se confunde con un socket mudo (-99999).
        digits = re.match(r"(-?\d+)", raw)
        if digits is None:
            return Reply(code=-99999, value=rest)
        code = int(digits.group(1))
        rest = raw[len(digits.group(1)) :]
    value = rest
    if value.startswith("{"):
        end = value.rfind("}")
        value = value[1:end] if end > 0 else value[1:]
    else:
        value = value.rsplit(",", 1)[0] if "," in value else value
    return Reply(code=code, value=value.strip())


class MG400Link:
    """Dos sockets abiertos contra el controlador: órdenes y movimiento."""

    def __init__(
        self,
        host: str,
        dashboard_port: int = DASHBOARD_PORT,
        move_port: int = MOVE_PORT,
        timeout_s: float = 5.0,
        move_timeout_s: float = 60.0,
    ) -> None:
        self.host = host
        self.timeout_s = timeout_s
        # Con la cola llena el controlador retiene la respuesta del MovL hasta
        # que hay espacio; cortar antes cierra el socket y detiene el brazo.
        self.move_timeout_s = move_timeout_s
        self.last_raw = b""
        logger.info("conectando a %s (dashboard %s, movimiento %s)", host, dashboard_port, move_port)
        self._dashboard = self._open(dashboard_port)
        self._move = self._open(move_port)

    def _open(self, port: int) -> socket.socket:
        sock = socket.create_connection((self.host, port), timeout=self.timeout_s)
        sock.settimeout(self.timeout_s)
        return sock

    def _ask(self, sock: socket.socket, command: str, timeout_s: float | None = None) -> Reply:
        sock.sendall((command + "\n").encode("ascii"))
        sock.settimeout(self.timeout_s if timeout_s is None else timeout_s)
        data = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            data += chunk
            # El dashboard cierra cada respuesta con `;`. Se corta ahí en vez de
            # esperar a que el socket se quede callado: esa espera costaba 0.12 s
            # por comando y el pad se sentía lento con cinco comandos por clic.
            text = data.decode("utf-8", errors="replace").strip()
            if text.endswith(";") and "," in text:
                break
            sock.settimeout(SILENCE_S)
        self.last_raw = data
        return _parse(data.decode("utf-8", errors="replace"))

    def dashboard(self, command: str) -> Reply:
        return self._ask(self._dashboard, command)

    def move(self, command: str) -> Reply:
        return self._ask(self._move, command, timeout_s=self.move_timeout_s)

    def _step(self, command: str) -> Reply:
        started = time.monotonic()
        reply = self.dashboard(command)
        logger.info(
            "%s -> %s %r (%.2f s)", command, reply.code, self.last_raw, time.monotonic() - started
        )
        return self.require(reply, command)

    def require(self, reply: Reply, command: str) -> Reply:
        if not reply.ok:
            raise MG400Error(f"{command} devolvio {reply.code}")
        return reply

    # --- lectura de estado -------------------------------------------------

    @staticmethod
    def _numbers(value: str) -> list[float]:
        """Saca los números de la respuesta, tolerando llaves y basura.

        Cuando el dashboard contesta `0,{},GetPose();` el valor llega con la
        llave puesta y convertirla revienta con ValueError, así que se descarta
        todo lo que no sea un número.
        """
        numbers: list[float] = []
        for chunk in value.replace("{", "").replace("}", "").split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                numbers.append(float(chunk))
            except ValueError:
                continue
        return numbers

    def mode(self) -> int:
        """Modo del robot: 5 es habilitado, 9 error, 4 deshabilitado."""
        reply = self.require(self.dashboard("RobotMode()"), "RobotMode")
        numbers = self._numbers(reply.value)
        return int(numbers[0]) if numbers else -1

    def pose(self) -> tuple[float, float, float, float]:
        """Posición cartesiana real en mm y grados: x, y, z, r."""
        reply = self.require(self.dashboard("GetPose()"), "GetPose")
        numbers = self._numbers(reply.value)[:4]
        if len(numbers) < 4:
            raise MG400Error(f"GetPose devolvio una pose incompleta: {reply.value!r}")
        return numbers[0], numbers[1], numbers[2], numbers[3]

    def angles(self) -> list[float]:
        reply = self.require(self.dashboard("GetAngle()"), "GetAngle")
        return self._numbers(reply.value)

    def errors(self) -> str:
        reply = self.require(self.dashboard("GetErrorID()"), "GetErrorID")
        return reply.value

    # --- órdenes de estado -------------------------------------------------

    def enable(self) -> Reply:
        return self.dashboard("EnableRobot()")

    def prepare(self, percent: int = 20) -> None:
        """Deja el robot listo para obedecer.

        Al cambiar al modo TCP/IP la cola de movimiento puede quedar pausada o
        con una orden vieja encolada: se limpian alarmas, se reanuda la cola
        (si no, los comandos se aceptan y nunca se ejecutan) y se fija la
        velocidad global de este modo.

        `EnableRobot` solo se manda si hace falta: en un robot ya habilitado
        tarda más de un segundo y es lo que hacía sentir lento cada clic.
        """
        mode = self.mode()
        logger.info("RobotMode() -> %s %r", mode, self.last_raw)
        if mode != MODE_ENABLED:
            self._step("EnableRobot()")
        self._step("ClearError()")
        self._step("Continue()")
        self._step(f"SpeedFactor({int(percent)})")

    def disable(self) -> Reply:
        return self.dashboard("DisableRobot()")

    def clear_error(self) -> Reply:
        return self.dashboard("ClearError()")

    def speed_factor(self, percent: int) -> Reply:
        """Velocidad global en porcentaje (1-100). Afecta a todo lo que siga."""
        return self.dashboard(f"SpeedFactor({int(percent)})")

    # --- movimiento --------------------------------------------------------

    def rel_movl(
        self,
        dx: float,
        dy: float,
        dz: float = 0.0,
        dr: float = 0.0,
        speed: int = 20,
        acc: int = 20,
        wait: bool = True,
    ) -> None:
        """Desplazamiento recto en milímetros desde la posición actual."""
        command = f"RelMovL({dx:.3f},{dy:.3f},{dz:.3f},{dr:.3f},{int(speed)},{int(acc)})"
        reply = self.move(command)
        if not reply.ok:
            raise MG400Error(f"{command} devolvio {reply.code}")
        if wait:
            self.sync()

    def sync(self) -> None:
        """Espera a que la cola de movimiento se vacíe.

        Un retrato puede tardar hasta un par de minutos. El tiempo de lectura
        de un MovL no alcanza: si se corta antes, el socket se desfasa y el
        siguiente dibujo ya no obtiene respuesta.
        """
        reply = self._ask(self._move, "Sync()", timeout_s=180.0)
        if not reply.ok:
            raise MG400Error(f"Sync devolvio {reply.code}")

    def jog(self, axis: str) -> None:
        """Arranca un desplazamiento continuo hasta `jog_stop` (X+, Y-, Z+...)."""
        self.move(f"MoveJog({axis})")

    def jog_stop(self) -> None:
        self.move("MoveJog()")

    def stop(self) -> None:
        self.move("Stop()")

    def close(self) -> None:
        for sock in (self._dashboard, self._move):
            try:
                sock.close()
            except OSError:
                pass

    def __enter__(self) -> "MG400Link":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
