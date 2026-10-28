"""Órdenes del panel admin, tomadas del protocolo TCP del MG400.

No acepta texto libre: cada acción arma un comando conocido. Las de movimiento
se niegan mientras hay un dibujo en curso. Paro, limpiar alarma y continuar
siguen disponibles.
"""

from __future__ import annotations

import hmac
import secrets

# Tope del joystick. El dibujo no usa este valor: sigue con ROBOT_SPEED_FACTOR.
SPEED_MAX = 100
STEP_MAX = 20.0

MOTION = {"jog", "step", "movl", "drag"}

# R cartesiana es J4 en este MG400. MoveJog(R+) no gira la muñeca.
JOG_AXES = {
    "X+": "X+",
    "X-": "X-",
    "Y+": "Y+",
    "Y-": "Y-",
    "Z+": "Z+",
    "Z-": "Z-",
    "R+": "J4+",
    "R-": "J4-",
    "J1+": "J1+",
    "J1-": "J1-",
    "J2+": "J2+",
    "J2-": "J2-",
    "J3+": "J3+",
    "J3-": "J3-",
    "J4+": "J4+",
    "J4-": "J4-",
}

STEP_CARTESIAN = {
    "X+": (1, 0, 0, 0),
    "X-": (-1, 0, 0, 0),
    "Y+": (0, 1, 0, 0),
    "Y-": (0, -1, 0, 0),
    "Z+": (0, 0, 1, 0),
    "Z-": (0, 0, -1, 0),
}

JOINT_INDEX = {"J1": 0, "J2": 1, "J3": 2, "J4": 3, "R": 3}

MODES = {
    1: "inicializando",
    2: "freno puesto",
    3: "apagado",
    4: "deshabilitado",
    5: "habilitado",
    6: "arrastre",
    7: "en movimiento",
    8: "grabando",
    9: "error",
    10: "pausa",
    11: "colisión",
}

ALARMS = {
    16: "cinemática inversa: singularidad",
    17: "cinemática inversa: sin solución",
    18: "la pose toca el límite de una articulación",
    22: "cambio de orientación del brazo",
    23: "un punto del tramo recto queda fuera del área de trabajo",
}

_tokens: set[str] = set()


class AdminOpError(ValueError):
    """La acción no se puede armar (eje, rango o dibujo en curso)."""


def pin_ok(pin: str, expected: str) -> bool:
    if len(pin) != 4 or not pin.isdigit() or len(expected) != 4 or not expected.isdigit():
        return False
    return hmac.compare_digest(pin, expected)


def issue_token() -> str:
    token = secrets.token_urlsafe(24)
    _tokens.add(token)
    return token


def token_ok(token: str) -> bool:
    return bool(token) and token in _tokens


def drop_tokens() -> None:
    _tokens.clear()


def mode_label(mode: int) -> str:
    return MODES.get(mode, "desconocido")


def describe_alarms(raw: str) -> str:
    labels: list[str] = []
    number = ""
    for char in raw:
        if char.isdigit() or (char == "-" and not number):
            number += char
            continue
        if number and number not in {"-", ""}:
            code = int(number)
            if code != 0:
                labels.append(ALARMS.get(code, f"alarma {code}"))
        number = ""
    if not labels:
        return ""
    return "; ".join(dict.fromkeys(labels))


def plan(action: str, payload: dict, *, busy: bool) -> tuple[str, bool, bool]:
    """Devuelve (comando, es_movimiento, hay_que_preparar_la_cola)."""
    # Stop() sale por el puerto de movimiento y se cruzaría con el dibujo en curso.
    # El paro de emergencia va por el dashboard y sí se puede usar.
    if busy and (action in MOTION or action == "stop"):
        raise AdminOpError("el robot está dibujando; solo se puede parar o limpiar la alarma")

    if action == "enable":
        return "EnableRobot()", False, False
    if action == "disable":
        return "DisableRobot()", False, False
    if action == "clear":
        return "ClearError()", False, False
    if action == "continue":
        return "Continue()", False, False
    if action == "pause":
        return "Pause()", False, False
    if action == "estop":
        return "EmergencyStop()", False, False
    if action == "reset":
        return "ResetRobot()", False, False
    if action == "stop":
        return "Stop()", True, False
    if action == "speed":
        return f"SpeedFactor({_speed(payload.get('value'))})", False, False
    if action == "collision":
        level = _int(payload.get("value"), 0, 5, "nivel")
        return f"SetCollisionLevel({level})", False, False
    if action == "drag":
        return ("StartDrag()" if payload.get("on") else "StopDrag()"), False, False
    if action == "di":
        index = _int(payload.get("index"), 1, 16, "entrada")
        return f"DI({index})", False, False
    if action == "jog":
        axis = payload.get("axis") or ""
        if axis == "":
            return "MoveJog()", True, False
        if axis not in JOG_AXES:
            raise AdminOpError("eje de jog desconocido")
        return f"MoveJog({JOG_AXES[axis]})", True, True
    if action == "step":
        speed = _speed(payload["speed"]) if payload.get("speed") is not None else 20
        return _step(str(payload.get("axis") or ""), _step_size(payload.get("mm")), speed), True, True
    if action == "inverse":
        x, y, z, r = _pose(payload)
        return f"InverseSolution({x:.3f},{y:.3f},{z:.3f},{r:.3f},0,0)", False, False
    if action == "movl":
        x, y, z, r = _pose(payload)
        speed = _speed(payload.get("speed", 20))
        return (
            f"MovL({x:.3f},{y:.3f},{z:.3f},{r:.3f},SpeedL={speed},AccL={speed},CP=1)",
            True,
            True,
        )
    raise AdminOpError("acción desconocida")


def rate_for(action: str, payload: dict) -> int | None:
    """Porcentaje del slider para un jog, un paso o un MovL. None conserva la del dibujo."""
    if action not in {"jog", "step", "movl"} or payload.get("speed") is None:
        return None
    return _speed(payload.get("speed"))


def _step(axis: str, size: float, speed: int = 20) -> str:
    if axis in STEP_CARTESIAN:
        dx, dy, dz, dr = (part * size for part in STEP_CARTESIAN[axis])
        return f"RelMovL({dx:.3f},{dy:.3f},{dz:.3f},{dr:.3f},{speed},{speed})"
    name = axis[:-1]
    sign = axis[-1:] if axis else ""
    if name not in JOINT_INDEX or sign not in {"+", "-"}:
        raise AdminOpError("eje de paso desconocido")
    offsets = [0.0, 0.0, 0.0, 0.0]
    offsets[JOINT_INDEX[name]] = size if sign == "+" else -size
    return "RelJointMovJ({:.3f},{:.3f},{:.3f},{:.3f},{:d},{:d})".format(*offsets, speed, speed)


def _pose(payload: dict) -> tuple[float, float, float, float]:
    from app.robot.client import _nonzero

    try:
        values = tuple(float(payload[key]) for key in ("x", "y", "z", "r"))
    except (KeyError, TypeError, ValueError) as exc:
        raise AdminOpError("la pose necesita x, y, z y r") from exc
    if any(abs(value) > 2000 for value in values):
        raise AdminOpError("la pose se sale del rango permitido")
    return tuple(_nonzero(value) for value in values)  # type: ignore[return-value]


def _speed(value: object) -> int:
    return _int(value, 1, SPEED_MAX, "velocidad")


def _step_size(value: object) -> float:
    try:
        size = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise AdminOpError("el paso tiene que ser un número") from exc
    if size <= 0 or size > STEP_MAX:
        raise AdminOpError(f"el paso va de 0 a {STEP_MAX:g} mm")
    return size


def _int(value: object, low: int, high: int, name: str) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise AdminOpError(f"{name} tiene que ser un entero") from exc
    if number < low or number > high:
        raise AdminOpError(f"{name} va de {low} a {high}")
    return number
