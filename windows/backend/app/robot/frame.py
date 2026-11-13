"""Marco de la hoja a partir de las esquinas enseñadas con el brazo.

Se enseñan la esquina superior izquierda, la superior derecha y la inferior
izquierda, mirando la hoja como se va a ver el dibujo. Con eso se ajusta el
rectángulo más cercano en el plano del papel: un error de uno o dos grados
ya no se estira entero en la esquina que no se midió.

Si la inferior derecha se escribe a mano, el marco pasa por las cuatro puntas.

Coordenadas de la hoja: `u` va de la esquina superior izquierda hacia la
derecha y `v` hacia abajo, en mm. La Z de dibujo sale del plano de las
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
# Por debajo de esto el ajuste se nota en el papel y conviene avisarlo.
ADJUST_WARN_MM = 3.0
MIN_SIDE_MM = 40.0
DEFAULT_LIFT_MM = 8.0
DEFAULT_MARGIN_MM = 8.0
# Alto del retrato entre su ancho: recorte 3:4 más el rótulo SYSCOM ROBOTICS.
PORTRAIT_ASPECT = 1.45

CORNERS = ("tl", "tr", "bl")
QUAD = ("tl", "tr", "br", "bl")

Vec = tuple[float, float, float]


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

    def xyz(self) -> Vec:
        return (self.x, self.y, self.z)


@dataclass(frozen=True)
class Frame:
    """Esquinas con las que se dibuja.

    En automático son el rectángulo ajustado. Si `manual` es verdadero, son
    las cuatro puntas tal como se escribieron y el trazado pasa por ellas.
    """

    tl: Corner
    tr: Corner
    bl: Corner
    br: Corner
    manual: bool = False
    straighten_deg: float = 0.0
    residuals_mm: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    raw_angle_deg: float = 90.0

    @classmethod
    def from_corners(cls, tl: Corner, tr: Corner, bl: Corner, br: Corner | None = None) -> Frame:
        angle = _corner_angle(tl, tr, bl)
        _require_sides(tl, tr, bl, angle)
        if br is None:
            quad, straighten, residuals = _fit_rectangle(tl, tr, bl)
            return cls(
                *quad,
                manual=False,
                straighten_deg=straighten,
                residuals_mm=residuals,
                raw_angle_deg=angle,
            )
        _require_point(br)
        _require_sides(tl, tr, bl, angle)
        if _dist(bl.xyz(), br.xyz()) < MIN_SIDE_MM or _dist(tr.xyz(), br.xyz()) < MIN_SIDE_MM:
            raise FrameError("la esquina inferior derecha quedó pegada a otra")
        return cls(
            tl,
            tr,
            bl,
            br,
            manual=True,
            straighten_deg=abs(angle - 90.0),
            residuals_mm=(0.0, 0.0, 0.0, 0.0),
            raw_angle_deg=angle,
        )

    @classmethod
    def from_dict(cls, raw: dict) -> Frame:
        corners = []
        for key in CORNERS:
            corners.append(_corner_from(raw, key, required=True))
        br_raw = raw.get("br") if isinstance(raw, dict) else None
        br = _corner_from(raw, "br", required=False) if isinstance(br_raw, dict) else None
        return cls.from_corners(*corners, br)

    def as_dict(self) -> dict:
        data = {key: getattr(self, key).as_dict() for key in CORNERS}
        if self.manual:
            data["br"] = self.br.as_dict()
        return data

    @property
    def width(self) -> float:
        return _dist(self.tl.xyz(), self.tr.xyz())

    @property
    def height(self) -> float:
        return _dist(self.tl.xyz(), self.bl.xyz())

    @property
    def corner_angle_deg(self) -> float:
        return _corner_angle(self.tl, self.tr, self.bl)

    @property
    def shift_mm(self) -> float:
        return max(self.residuals_mm)

    @property
    def orientation(self) -> str:
        return "horizontal" if self.width >= self.height else "vertical"

    def to_robot(self, u: float, v: float) -> tuple[float, float, float, float]:
        """Punto de la hoja (mm desde la esquina superior izquierda) → X, Y, Z, R del robot."""
        a = u / self.width
        b = v / self.height

        def mix(name: str) -> float:
            tl = getattr(self.tl, name)
            tr = getattr(self.tr, name)
            bl = getattr(self.bl, name)
            br = getattr(self.br, name)
            return (1 - a) * (1 - b) * tl + a * (1 - b) * tr + (1 - a) * b * bl + a * b * br

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


def _corner_from(raw: dict, key: str, *, required: bool) -> Corner:
    point = raw.get(key) if isinstance(raw, dict) else None
    if not isinstance(point, dict):
        if required:
            raise FrameError("faltan esquinas: enseña las tres")
        raise FrameError("la esquina inferior derecha no trae X, Y y Z")
    try:
        corner = Corner(
            x=float(point["x"]),
            y=float(point["y"]),
            z=float(point["z"]),
            r=float(point.get("r", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FrameError("una esquina no trae X, Y y Z") from exc
    _require_point(corner)
    return corner


def _require_point(corner: Corner) -> None:
    if any(abs(value) > 2000 for value in (corner.x, corner.y, corner.z, corner.r)):
        raise FrameError("una esquina se sale del rango")


def _require_sides(tl: Corner, tr: Corner, bl: Corner, angle: float) -> None:
    width = _dist(tl.xyz(), tr.xyz())
    height = _dist(tl.xyz(), bl.xyz())
    if width < MIN_SIDE_MM or height < MIN_SIDE_MM:
        raise FrameError(
            f"la hoja mide {width:.0f} × {height:.0f} mm: "
            "alguna esquina quedó repetida o muy cerca de otra"
        )
    if abs(angle - 90.0) > SQUARE_TOLERANCE_DEG:
        raise FrameError(
            f"las esquinas forman un ángulo de {angle:.0f}°: "
            "vuelve a enseñar la que quedó chueca"
        )


def _corner_angle(tl: Corner, tr: Corner, bl: Corner) -> float:
    return _angle_between(_sub(tr.xyz(), tl.xyz()), _sub(bl.xyz(), tl.xyz()))


def _angle_between(u: Vec, v: Vec) -> float:
    nu, nv = _norm(u), _norm(v)
    if nu <= 1e-9 or nv <= 1e-9:
        return 0.0
    cos = max(-1.0, min(1.0, _dot(u, v) / (nu * nv)))
    return math.degrees(math.acos(cos))


def _fit_rectangle(
    tl: Corner, tr: Corner, bl: Corner
) -> tuple[tuple[Corner, Corner, Corner, Corner], float, tuple[float, float, float, float]]:
    """Rectángulo más cercano: reparte el ángulo y centra el error en las tres puntas."""
    u = _sub(tr.xyz(), tl.xyz())
    v = _sub(bl.xyz(), tl.xyz())
    normal = _cross(u, v)
    length = _norm(normal)
    if length <= 1e-9:
        raise FrameError("las esquinas están en línea: vuelve a enseñar una")
    axis = _scale(normal, 1.0 / length)
    theta = math.atan2(length, _dot(u, v))
    delta = theta - math.pi / 2
    if abs(delta) < 1e-12:
        u2, v2 = u, v
    else:
        # El eje es U × V, así que girar U hacia V y V hacia U cierra el ángulo.
        u2 = _rot(u, axis, delta / 2)
        v2 = _rot(v, axis, -delta / 2)
    origin = tl.xyz()
    fitted = (
        origin,
        _add(origin, u2),
        _add(origin, v2),
        _add(origin, _add(u2, v2)),
    )
    taught = (tl.xyz(), tr.xyz(), bl.xyz())
    mean = tuple(sum(taught[i][axis_i] - fitted[i][axis_i] for i in range(3)) / 3.0 for axis_i in range(3))
    fitted = tuple(_add(point, mean) for point in fitted)
    raw_br = _add(tl.xyz(), _add(u, v))
    br_r = tr.r + bl.r - tl.r
    quad = (
        Corner(*fitted[0], tl.r),
        Corner(*fitted[1], tr.r),
        Corner(*fitted[2], bl.r),
        Corner(*fitted[3], br_r),
    )
    residuals = (
        _dist(fitted[0], tl.xyz()),
        _dist(fitted[1], tr.xyz()),
        _dist(fitted[2], bl.xyz()),
        _dist(fitted[3], raw_br),
    )
    return quad, abs(math.degrees(delta)), residuals


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Vec, factor: float) -> Vec:
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: Vec) -> float:
    return math.sqrt(_dot(a, a))


def _dist(a: Vec, b: Vec) -> float:
    return _norm(_sub(a, b))


def _rot(vector: Vec, axis: Vec, radians: float) -> Vec:
    """Giro de Rodrigues. `axis` tiene que estar normalizado."""
    cos = math.cos(radians)
    sin = math.sin(radians)
    crossed = _cross(axis, vector)
    along = _dot(axis, vector)
    return tuple(
        vector[i] * cos + crossed[i] * sin + axis[i] * along * (1.0 - cos) for i in range(3)
    )


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


def outline_block(frame: Frame, width_mm: float, height_mm: float) -> str:
    """Por qué no se puede recorrer un rectángulo de ese tamaño centrado en la hoja.

    Vacío si las cuatro esquinas entran en el alcance. El rectángulo puede
    sobresalir de lo enseñado: así se ve el tamaño real de una hoja estándar.
    """
    u0 = (frame.width - width_mm) / 2
    v0 = (frame.height - height_mm) / 2
    spots = (
        ("superior izquierda", u0, v0),
        ("superior derecha", u0 + width_mm, v0),
        ("inferior derecha", u0 + width_mm, v0 + height_mm),
        ("inferior izquierda", u0, v0 + height_mm),
    )
    for label, u, v in spots:
        x, y, _, _ = frame.to_robot(u, v)
        radius = _radius(x, y)
        if radius > REACH_MAX_MM:
            return (
                f"el marco de {width_mm:.0f} × {height_mm:.0f} mm saca la esquina "
                f"{label} a {radius:.0f} mm del eje; el brazo llega a {REACH_MAX_MM:.0f}"
            )
        angle = math.degrees(math.atan2(y, x))
        if abs(angle) > J1_LIMIT_DEG:
            return f"el marco de {width_mm:.0f} × {height_mm:.0f} mm saca la esquina {label} detrás del robot"
    return ""


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
    if frame.manual and frame.straighten_deg > 1.0:
        warnings.append(
            f"la esquina a mano deja la hoja a {frame.corner_angle_deg:.1f}° en vez de 90°. "
            "El perímetro pasa por las cuatro puntas que escribiste"
        )
    elif not frame.manual and frame.shift_mm > ADJUST_WARN_MM:
        warnings.append(
            f"para dejar la hoja a escuadra hubo que mover una esquina {frame.shift_mm:.1f} mm. "
            "Si el papel no coincide, vuelve a tomarla o escribe la inferior derecha"
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

    labels = ("tl", "tr", "bl", "br")
    return {
        "width_mm": round(frame.width, 1),
        "height_mm": round(frame.height, 1),
        "orientation": frame.orientation,
        "angle_deg": round(frame.corner_angle_deg, 1),
        "straighten_deg": round(frame.straighten_deg, 2),
        "shift_mm": round(frame.shift_mm, 2),
        "manual_br": frame.manual,
        "residuals_mm": {name: round(frame.residuals_mm[index], 2) for index, name in enumerate(labels)},
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
