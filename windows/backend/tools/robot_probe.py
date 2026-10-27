"""Sonda de comunicacion con el Dobot MG400 (solo lectura).

No mueve el robot: consulta el servidor Dashboard (puerto 29999) y lista lo que
responde, para saber en que estado esta antes de mandarle nada.

Uso:
    python tools/robot_probe.py [--host 192.168.10.55]
"""

from __future__ import annotations

import argparse
import socket

DASHBOARD_PORT = 29999
CONNECT_TIMEOUT_S = 3.0
# El Dashboard no siempre termina la respuesta con salto de linea, asi que en
# vez de esperar un terminador se corta tras un silencio corto.
SILENCE_S = 0.35
# Consultas inocuas: no cambian el estado del robot.
QUERIES = [
    "RobotMode()",
    "GetPose()",
    "GetAngle()",
    "GetErrorID()",
    "SpeedFactor()",
    "DragTeachStatus()",
    "Payload()",
    "Version()",
]


def _drain(sock: socket.socket, first_timeout: float = 1.5) -> str:
    """Lee hasta que el robot deja de hablar."""
    sock.settimeout(first_timeout)
    data = b""
    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        sock.settimeout(SILENCE_S)
    return data.decode("utf-8", errors="replace").strip()


def ask(host: str, command: str, port: int = DASHBOARD_PORT) -> str:
    """Manda un comando al dashboard y devuelve su respuesta."""
    with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT_S) as sock:
        # El servidor saluda al conectar; se descarta para no confundir el
        # saludo con la respuesta del comando.
        _drain(sock)
        sock.sendall((command + "\n").encode("ascii"))
        return _drain(sock)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.10.55")
    parser.add_argument(
        "--send",
        action="append",
        default=None,
        metavar="COMANDO",
        help="manda este comando y muestra la respuesta (se puede repetir)",
    )
    args = parser.parse_args()

    print(f"MG400 en {args.host}:{DASHBOARD_PORT}\n", flush=True)
    if args.send:
        for command in args.send:
            try:
                answer = ask(args.host, command)
            except OSError as exc:
                print(f"  {command:<24} sin respuesta ({exc})", flush=True)
                continue
            print(f"  {command:<24} {answer or '(vacio)'}", flush=True)
        return

    for command in QUERIES:
        try:
            answer = ask(args.host, command)
        except OSError as exc:
            print(f"  {command:<20} sin respuesta ({exc})", flush=True)
            continue
        shown = answer.replace("\n", " | ") or "(vacio)"
        print(f"  {command:<20} {shown}", flush=True)


if __name__ == "__main__":
    main()
