"""Marco de la hoja a partir de tres esquinas enseñadas con el brazo.

Se enseñan la esquina superior izquierda, la superior derecha y la inferior
izquierda, mirando la hoja como se va a ver el dibujo. Con eso salen la
orientación, el sentido de los ejes y el ancho y alto reales: no hacen falta
signos ni un centro adivinado.

Coordenadas de la hoja: `u` va de la esquina superior izquierda hacia la
derecha y `v` hacia abajo, en mm. La Z de dibujo sale del plano de las tres
esquinas (la mesa no siempre está pareja) y la R se interpola igual.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.robot import sheet as sheet_ops

# Alcance del MG400 según la hoja de datos: radio de 440 mm y J1 en ±160°.
REACH_MAX_MM = 440.0
J1_LIMIT_DEG = 160.0
# Junto a la columna el brazo se queda sin codo. No es un dato del fabricante:
# por debajo de esto conviene probar la esquina con "Ir aquí" antes de dibujar.
REACH_MIN_MM = 170.0
# Un rectángulo más torcido que esto es una esquina mal enseñada.
SQUARE_TOLERANCE_DEG = 5.0
MIN_SIDE_MM = 40.0
DEFAULT_LIFT_MM = 8.0
DEFAULT_MARGIN_MM = 8.0
# Alto del retrato entre su ancho: recorte 3:4 más el rótulo SYSCOM ROBOTICS.
PORTRAIT_ASPECT = 1.45

CORNERS = ("tl", "tr", "bl")


class FrameError(ValueError):
    """Las esquinas no forman una hoja."""


@dataclass(frozen=True)
class Corner:
    x: float
    y: float
    z: float
    r: float

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "z": self.z, "r": self.r}


@dataclass(frozen=True)
class Frame:
    tl: Corner
    tr: Corner
    bl: Corner

    @classmethod
    def from_corners(cls, tl: Corner, tr: Corner, bl: Corner) -> Frame:
        frame = cls(tl, tr, bl)
        if frame.width < MIN_SIDE_MM or frame.height < MIN_SIDE_MM:
            raise FrameError(
                f"la hoja mide {frame.width:.0f} × {frame.height:.0f} mm: "
                "alguna esquina quedó repetida o muy cerca de otra"
            )
        skew = abs(frame.corner_angle_deg - 90.0)
        if skew > SQUARE_TOLERANCE_DEG:
            raise FrameError(
                f"las esquinas forman un ángulo de {frame.corner_angle_deg:.0f}°: "
                "vuelve a enseñar la que quedó chueca"
            )
        return frame

    @classmethod
    def from_dict(cls, raw: dict) -> Frame:
        corners = []
        for key in CORNERS:
            point = raw.get(key) if isinstance(raw, dict) else None
            if not isinstance(point, dict):
                raise FrameError("faltan esquinas: enseña las tres")
            try:
                corners.append(
                    Corner(
                        x=float(point["x"]),
                        y=float(point["y"]),
                        z=float(point["z"]),
                        r=float(point.get("r", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise FrameError("una esquina no trae X, Y y Z") from exc
        return cls.from_corners(*corners)

    def as_dict(self) -> dict:
        return {key: getattr(self, key).as_dict() for key in CORNERS}

    @property
    def width(self) -> float:
        return math.hypot(self.tr.x - self.tl.x, self.tr.y - self.tl.y)

    @property
    def height(self) -> float:
        return math.hypot(self.bl.x - self.tl.x, self.bl.y - self.tl.y)

    @property
    def corner_angle_deg(self) -> float:
        ux, uy = self.tr.x - self.tl.x, self.tr.y - self.tl.y
        vx, vy = self.bl.x - self.tl.x, self.bl.y - self.tl.y
        norm = math.hypot(ux, uy) * math.hypot(vx, vy)
        if norm <= 1e-9:
            return 0.0
        cos = max(-1.0, min(1.0, (ux * vx + uy * vy) / norm))
        return math.degrees(math.acos(cos))

    @property
    def orientation(self) -> str:
        return "horizontal" if self.width >= self.height else "vertical"

    def to_robot(self, u: float, v: float) -> tuple[float, float, float, float]:
        """Punto de la hoja (mm desde la esquina superior izquierda) → X, Y, Z, R del robot."""
        a = u / self.width
        b = v / self.height

        def mix(name: str) -> float:
            origin = getattr(self.tl, name)
            return (
                origin
                + a * (getattr(self.tr, name) - origin)
                + b * (getattr(self.bl, name) - origin)
            )

        return mix("x"), mix("y"), mix("z"), mix("r")

    def named(self, name: str) -> tuple[float, float, float, float]:
        """Las cuatro esquinas y el centro, para mandar el brazo con "Ir aquí"."""
        spots = {
            "tl": (0.0, 0.0),
            "tr": (self.width, 0.0),
            "bl": (0.0, self.height),
            "br": (self.width, self.height),
            "center": (self.width / 2, self.height / 2),
        }
        if name not in spots:
            raise FrameError(f"no hay un punto llamado {name}")
        return self.to_robot(*spots[name])


def fit(
    frame: Frame,
    width_mm: float,
    height_mm: float,
    margin_mm: float = DEFAULT_MARGIN_MM,
) -> tuple[float, float, float]:
    """(escala, u0, v0) para meter un dibujo dentro de la hoja, centrado y sin estirarlo."""
    usable_w = frame.width - 2 * margin_mm
    usable_h = frame.height - 2 * margin_mm
    if usable_w <= 0 or usable_h <= 0 or width_mm <= 0 or height_mm <= 0:
        raise FrameError("el margen no deja espacio para el dibujo")
    scale = min(usable_w / width_mm, usable_h / height_mm)
    u0 = margin_mm + (usable_w - scale * width_mm) / 2
    v0 = margin_mm + (usable_h - scale * height_mm) / 2
    return scale, u0, v0


def portrait_width_mm(frame: Frame, margin_mm: float = DEFAULT_MARGIN_MM) -> float:
    """Ancho al que se genera el retrato para que llene la hoja sin pasarse de alto."""
    usable_w = frame.width - 2 * margin_mm
    usable_h = frame.height - 2 * margin_mm
    return max(20.0, min(usable_w, usable_h / PORTRAIT_ASPECT))


def _radius(x: float, y: float) -> float:
    return math.hypot(x, y)


def _edge_points(frame: Frame, samples: int = 40) -> list[tuple[float, float]]:
    w, h = frame.width, frame.height
    path = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)]
    points: list[tuple[float, float]] = []
    for (u0, v0), (u1, v1) in zip(path, path[1:]):
        for step in range(samples):
            t = step / samples
            x, y, _, _ = frame.to_robot(u0 + t * (u1 - u0), v0 + t * (v1 - v0))
            points.append((x, y))
    return points


def reach_report(frame: Frame) -> tuple[list[str], list[str]]:
    """(errores, avisos). Un error impide guardar; un aviso pide probar con "Ir aquí"."""
    errors: list[str] = []
    warnings: list[str] = []
    labels = {
        "tl": "superior izquierda",
        "tr": "superior derecha",
        "bl": "inferior izquierda",
        "br": "inferior derecha",
    }
    for key, label in labels.items():
        x, y, _, _ = frame.named(key)
        radius = _radius(x, y)
        if radius > REACH_MAX_MM:
            errors.append(f"la esquina {label} queda a {radius:.0f} mm del eje; el brazo llega a {REACH_MAX_MM:.0f}")
        angle = math.degrees(math.atan2(y, x))
        if abs(angle) > J1_LIMIT_DEG:
            errors.append(f"la esquina {label} queda detrás del robot ({angle:.0f}°)")
    nearest = min(_radius(x, y) for x, y in _edge_points(frame))
    if nearest < REACH_MIN_MM:
        warnings.append(
            f"el borde de la hoja pasa a {nearest:.0f} mm del eje: junto a la columna "
            "el brazo puede no llegar. Prueba esa zona con Ir aquí"
        )
    return errors, warnings


def nearest_paper(frame: Frame) -> dict | None:
    """La hoja estándar que más se parece a lo medido, en cualquier orientación."""
    long_side = max(frame.width, frame.height)
    short_side = min(frame.width, frame.height)
    best: tuple[float, str, str] | None = None
    for key, (label, a, b) in sheet_ops.PAPERS.items():
        diff = max(abs(long_side - max(a, b)), abs(short_side - min(a, b)))
        if best is None or diff < best[0]:
            best = (diff, key, label)
    if best is None:
        return None
    diff, key, label = best
    return {"id": key, "label": label, "diff_mm": round(diff, 1), "matches": diff <= 5.0}


def summary(frame: Frame, margin_mm: float = DEFAULT_MARGIN_MM) -> dict:
    """Lo que el panel muestra: medida, orientación, dónde cae el retrato y avisos."""
    errors, warnings = reach_report(frame)
    paper = nearest_paper(frame)
    if paper and not paper["matches"]:
        warnings.append(
            f"la medida no coincide con ninguna hoja estándar (la más cercana es "
            f"{paper['label']}, a {paper['diff_mm']:.0f} mm). Revisa las esquinas"
        )
    draw_w = portrait_width_mm(frame, margin_mm)
    draw_h = draw_w * PORTRAIT_ASPECT
    scale, u0, v0 = fit(frame, draw_w, draw_h, margin_mm)
    box = [
        (u0, v0),
        (u0 + scale * draw_w, v0),
        (u0 + scale * draw_w, v0 + scale * draw_h),
        (u0, v0 + scale * draw_h),
    ]

    def xy(name: str) -> list[float]:
        x, y, z, r = frame.named(name)
        return [round(x, 2), round(y, 2), round(z, 2), round(r, 2)]

    return {
        "width_mm": round(frame.width, 1),
        "height_mm": round(frame.height, 1),
        "orientation": frame.orientation,
        "angle_deg": round(frame.corner_angle_deg, 1),
        "paper": paper,
        "draw_width_mm": round(scale * draw_w, 1),
        "draw_height_mm": round(scale * draw_h, 1),
        "points": {name: xy(name) for name in ("tl", "tr", "br", "bl", "center")},
        "draw_box": [
            [round(value, 2) for value in frame.to_robot(u, v)[:2]] for u, v in box
        ],
        "errors": errors,
        "warnings": warnings,
    }
