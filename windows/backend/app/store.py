"""Almacén en memoria de bocetos y trabajos (se reinicia con el servidor)."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Sketch:
    """Boceto listo para dibujar: preview, SVG, trazos y trayectoria."""

    id: str
    preview: str
    svg: str
    strokes: list[dict] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class Job:
    """Trabajo de dibujo del robot."""

    id: str
    sketch_id: str
    status: str = "queued"  # queued | drawing | done | error
    progress: float = 0.0
    eta_seconds: float = 0.0
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class _BoundedStore:
    """Store LRU sencillo para no crecer sin control."""

    def __init__(self, max_items: int = 32) -> None:
        self._items: OrderedDict[str, Any] = OrderedDict()
        self._max_items = max_items

    def put(self, key: str, value: Any) -> None:
        self._items[key] = value
        self._items.move_to_end(key)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def get(self, key: str) -> Any | None:
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def latest(self, count: int) -> list[Any]:
        """Los más recientes primero (el OrderedDict crece hacia el final)."""
        return list(reversed(self._items.values()))[:count]

    def drop_settled(self) -> int:
        """Quita lo ya terminado. Un dibujo en curso o en cola se queda."""
        keys = [
            key
            for key, job in self._items.items()
            if getattr(job, "status", "") not in {"drawing", "queued"}
        ]
        for key in keys:
            del self._items[key]
        return len(keys)


class SketchStore(_BoundedStore):
    pass


class JobStore(_BoundedStore):
    pass
