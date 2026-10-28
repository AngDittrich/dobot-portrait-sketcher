"""Marca cuando un dibujo tiene el brazo. El panel admin no lo mueve en ese rato."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_depth = 0


def enter() -> None:
    global _depth
    with _lock:
        _depth += 1


def leave() -> None:
    global _depth
    with _lock:
        _depth = max(0, _depth - 1)


def active() -> bool:
    with _lock:
        return _depth > 0
