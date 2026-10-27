"""Pad de botones para mover el MG400 a mano.

Levanta una página local con la misma disposición que el DobotStudio: dos cruces
cartesianas (X/Y y Z/R) y dos de articulaciones (J1/J2 y J3/J4). En modo Jog el
robot se mueve mientras el botón está apretado; en modo Step avanza el paso
elegido y se detiene. No forma parte de la cabina: es una herramienta de taller.

Uso:
    python tools/robot_pad.py [--host 192.168.10.55] [--port 8010]

Luego abre http://127.0.0.1:8010
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.robot.mg400 import MG400Error, MG400Link  # noqa: E402

ROBOT_HOST = "192.168.10.55"
# Límites duros: el pad es para probar, no para trazar.
MAX_STEP_MM = 10.0
MIN_SPEED = 5
MAX_SPEED = 40
# Si el navegador deja de avisar, el robot se detiene solo. Una pestaña que se
# cierra mientras se sostiene un botón no puede dejar el brazo caminando solo.
JOG_KEEPALIVE_S = 1.0
JOG_WATCHDOG_S = 0.25
PULSE_S = 0.18

# Ejes con paso relativo exacto: cuánto suma cada paso a (dx, dy, dz, dr).
# La R se queda fuera a propósito. Pedir 1° por `RelMovL` no gira la muñeca en
# este controlador: movió el brazo 2 mm en X y 3.3 mm en Z sin tocar R, y el paso
# inverso no hizo nada. En modo Step la R se mueve con un pulso de J4, que sí
# gira solo la muñeca.
CARTESIAN = {
    "X+": (1, 0, 0, 0),
    "X-": (-1, 0, 0, 0),
    "Y+": (0, 1, 0, 0),
    "Y-": (0, -1, 0, 0),
    "Z+": (0, 0, 1, 0),
    "Z-": (0, 0, -1, 0),
}

# Nombre del botón -> nombre que espera MoveJog. En el MG400 de 4 ejes la R del
# plano cartesiano es la cuarta articulación, así que R± se mueve como J4±.
# `Rz+` también lo acepta el controlador, pero no gira la muñeca: medido con el
# robot quieto, movió 5 mm en X y dejó R intacta.
JOG: dict[str, str] = {
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

_LOCK = threading.Lock()
_ROBOT: MG400Link | None = None
_JOG_AXIS: str | None = None
_JOG_DEADLINE = 0.0


def robot() -> MG400Link:
    """Enlace fijo: el MG400 atiende un solo cliente de dashboard a la vez.

    Abrir y cerrar un socket por clic dejaba la sesión anterior colgada unos
    segundos y la orden siguiente se perdía en el vacío (-99999 = sin
    respuesta), así que se reutiliza siempre el mismo enlace.
    """
    global _ROBOT
    if _ROBOT is None:
        _ROBOT = MG400Link(ROBOT_HOST)
    return _ROBOT


def drop() -> None:
    """Tira el enlace para que el siguiente intento empiece de cero."""
    global _ROBOT
    if _ROBOT is not None:
        try:
            _ROBOT.close()
        except OSError:
            pass
        _ROBOT = None


def link_ready(speed: int) -> MG400Link:
    """Devuelve el enlace listo para moverse.

    `prepare` reanuda la cola si quedó pausada: sin eso el robot acepta la orden
    y se queda quieto. Si la sesión del dashboard se quedó vieja, se reabre una
    vez y se reintenta.
    """
    link = robot()
    try:
        link.prepare(speed)
    except MG400Error:
        drop()
        link = robot()
        link.prepare(speed)
    return link


def jog_stop() -> None:
    global _JOG_AXIS
    with _LOCK:
        _JOG_AXIS = None
        try:
            robot().jog_stop()
        except (OSError, MG400Error):
            drop()


def _watchdog() -> None:
    """Detiene el jog si el navegador dejó de latir."""
    while True:
        time.sleep(JOG_WATCHDOG_S)
        if _JOG_AXIS and time.monotonic() > _JOG_DEADLINE:
            jog_stop()


threading.Thread(target=_watchdog, daemon=True, name="jog-watchdog").start()


PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MG400</title>
<style>
  :root {
    --ink: #10151c;
    --panel: #171e28;
    --panel-2: #1e2733;
    --line: #2a3644;
    --text: #e8eef5;
    --dim: #8b98a7;
    --accent: #4f7cff;
    --danger: #e2564a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    background: radial-gradient(120% 90% at 50% 0%, #1b2430 0%, #0b0f14 70%);
    color: var(--text);
    font: 15px/1.45 "Segoe UI", system-ui, sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    -webkit-user-select: none;
    user-select: none;
  }
  main { width: min(860px, 100%); }
  header {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }
  .seg {
    display: flex;
    border: 1px solid var(--line);
    border-radius: 10px;
    overflow: hidden;
  }
  .seg button {
    background: none;
    border: 0;
    color: var(--dim);
    padding: 8px 20px;
    font: inherit;
    cursor: pointer;
  }
  .seg button.on { background: var(--accent); color: #fff; }
  .steps { display: flex; gap: 6px; margin-left: auto; }
  .steps button {
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--dim);
    border-radius: 8px;
    padding: 7px 13px;
    font: inherit;
    cursor: pointer;
  }
  .steps button.on { border-color: var(--accent); color: #fff; }
  .speed {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    color: var(--dim);
    font-size: 13px;
  }
  input[type=range] { flex: 1; accent-color: var(--accent); }

  .board {
    display: grid;
    grid-template-columns: 92px 1fr 1fr;
    gap: 18px 14px;
    align-items: center;
  }
  .read { font-variant-numeric: tabular-nums; }
  .read b { display: block; font-size: 11px; letter-spacing: .12em; color: var(--dim); font-weight: 600; }
  .read span { font-size: 19px; }

  .cross {
    position: relative;
    aspect-ratio: 1;
    border-radius: 50%;
    background: radial-gradient(circle at 50% 42%, var(--panel-2), var(--panel) 70%);
    border: 1px solid var(--line);
  }
  .cross button {
    position: absolute;
    width: 32%;
    height: 30%;
    background: none;
    border: 0;
    color: var(--dim);
    font: 600 15px/1 "Segoe UI", system-ui, sans-serif;
    cursor: pointer;
    border-radius: 12px;
    transition: color .12s, background .12s;
  }
  .cross button:hover { color: #fff; }
  .cross button.held { color: #fff; background: rgba(79, 124, 255, .28); }
  .cross button.n { top: 2%;  left: 34%; }
  .cross button.s { bottom: 2%; left: 34%; }
  .cross button.w { left: 2%;  top: 35%; }
  .cross button.e { right: 2%; top: 35%; }
  .cross::after {
    content: "";
    position: absolute;
    inset: 39%;
    border-radius: 50%;
    border: 1px solid var(--line);
  }

  footer {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-top: 22px;
  }
  .stop {
    background: var(--danger);
    color: #fff;
    border: 0;
    border-radius: 10px;
    padding: 12px 26px;
    font: 600 15px/1 inherit;
    cursor: pointer;
  }
  .hint { color: var(--dim); font-size: 13px; }
  .err { color: var(--danger); font-size: 13px; min-height: 18px; }
</style>
</head>
<body>
<main>
  <header>
    <div class="seg">
      <button id="mode-jog" class="on">Jog</button>
      <button id="mode-step">Step</button>
    </div>
    <div class="steps">
      <button data-step="0.1">0.1</button>
      <button data-step="1" class="on">1</button>
      <button data-step="5">5</button>
      <button data-step="10">10</button>
    </div>
    <label class="speed">velocidad
      <input id="speed" type="range" min="5" max="40" value="20">
      <span id="speed-val">20%</span>
    </label>
  </header>

  <div class="board">
    <div class="read"><b>X</b><span id="x">--</span></div>
    <div class="cross" data-cross="xy">
      <button class="n" data-axis="X+">X+</button>
      <button class="w" data-axis="Y+">Y+</button>
      <button class="e" data-axis="Y-">Y-</button>
      <button class="s" data-axis="X-">X-</button>
    </div>
    <div class="cross" data-cross="zr">
      <button class="n" data-axis="Z+">Z+</button>
      <button class="w" data-axis="R+">R+</button>
      <button class="e" data-axis="R-">R-</button>
      <button class="s" data-axis="Z-">Z-</button>
    </div>

    <div class="read"><b>Y</b><span id="y">--</span></div>
    <div class="cross" data-cross="j12">
      <button class="n" data-axis="J1+">J1+</button>
      <button class="w" data-axis="J2+">J2+</button>
      <button class="e" data-axis="J2-">J2-</button>
      <button class="s" data-axis="J1-">J1-</button>
    </div>
    <div class="cross" data-cross="j34">
      <button class="n" data-axis="J3+">J3+</button>
      <button class="w" data-axis="J4+">J4+</button>
      <button class="e" data-axis="J4-">J4-</button>
      <button class="s" data-axis="J3-">J3-</button>
    </div>

    <div class="read"><b>Z</b><span id="z">--</span></div>
    <div class="read"><b>R</b><span id="r">--</span></div>
    <div class="read"><b>modo</b><span id="m">--</span></div>

    <div class="read"><b>J1</b><span id="j1">--</span></div>
    <div class="read"><b>J2</b><span id="j2">--</span></div>
    <div class="read"><b>J3</b><span id="j3">--</span></div>
    <div class="read"><b>J4</b><span id="j4">--</span></div>
  </div>

  <footer>
    <button class="stop" id="stop">Detener</button>
    <span class="hint" id="hint">Jog: mantén el botón. Step: un clic por paso.</span>
    <span class="err" id="err"></span>
  </footer>
</main>
<script>
const $ = (id) => document.getElementById(id);
let mode = 'jog';
let step = 1;
let speed = 20;
let holding = null;
let holdTimer = 0;
let holdStart = 0;

async function post(path, body) {
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json();
    if (data.error) showError(data.error); else showError('');
    return data;
  } catch (err) {
    showError('sin respuesta del pad');
    return {};
  }
}

function showError(text) { $('err').textContent = text || ''; }

function setMode(next) {
  mode = next;
  $('mode-jog').classList.toggle('on', mode === 'jog');
  $('mode-step').classList.toggle('on', mode === 'step');
  $('hint').textContent = mode === 'jog'
    ? 'Jog: mantén el botón. Step: un clic por paso.'
    : 'Step: un clic por paso (las articulaciones avanzan un pulso).';
  stopJog();
}

function startHold(button) {
  const axis = button.dataset.axis;
  if (!axis || holding) return;
  button.classList.add('held');
  if (mode === 'step') {
    if (/^[XYZ][+-]$/.test(axis)) {
      // Paso relativo exacto: el robot avanza y se queda ahí.
      post('/api/step', { axis, step, speed });
      setTimeout(() => button.classList.remove('held'), 160);
      return;
    }
    // R y las articulaciones no tienen paso relativo: se mueven un pulso corto.
    holdPulse(axis, button);
    return;
  }
  holding = axis;
  holdStart = performance.now();
  post('/api/jog', { axis, speed });
  // Late mientras se sostiene: si la pestaña muere, el robot se detiene solo.
  holdTimer = setInterval(() => {
    if (performance.now() - holdStart > 6000) { stopJog(); return; }
    post('/api/jog', { axis, speed });
  }, 400);
}

function holdPulse(axis, button) {
  holding = axis;
  post('/api/jog', { axis, speed });
  setTimeout(() => { stopJog(); button.classList.remove('held'); }, 180);
}

function stopJog() {
  if (!holding) return;
  holding = null;
  clearInterval(holdTimer);
  post('/api/jog/stop', {});
  document.querySelectorAll('.cross button.held').forEach((b) => b.classList.remove('held'));
}

document.querySelectorAll('.cross button').forEach((button) => {
  button.addEventListener('pointerdown', (event) => { event.preventDefault(); startHold(button); });
  button.addEventListener('pointerup', stopJog);
  button.addEventListener('pointerleave', stopJog);
  button.addEventListener('pointercancel', stopJog);
});

$('mode-jog').onclick = () => setMode('jog');
$('mode-step').onclick = () => setMode('step');
document.querySelectorAll('.steps button').forEach((button) => {
  button.onclick = () => {
    step = parseFloat(button.dataset.step);
    document.querySelectorAll('.steps button').forEach((b) => b.classList.toggle('on', b === button));
  };
});
$('speed').oninput = (event) => {
  speed = parseInt(event.target.value, 10);
  $('speed-val').textContent = speed + '%';
};
$('stop').onclick = () => { stopJog(); post('/api/stop', {}); };

window.addEventListener('blur', stopJog);
document.addEventListener('visibilitychange', () => { if (document.hidden) stopJog(); });
window.addEventListener('keyup', (event) => { if (event.key === ' ') { stopJog(); post('/api/stop', {}); } });

async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    if (data.pose) {
      $('x').textContent = data.pose[0].toFixed(2);
      $('y').textContent = data.pose[1].toFixed(2);
      $('z').textContent = data.pose[2].toFixed(2);
      $('r').textContent = data.pose[3].toFixed(2);
    }
    if (data.angles) {
      for (let i = 0; i < 4; i += 1) {
        const cell = $('j' + (i + 1));
        if (cell) cell.textContent = data.angles[i].toFixed(2);
      }
    }
    $('m').textContent = data.mode === 5 ? 'habilitado' : (data.error ? 'sin enlace' : String(data.mode));
    showError(data.error || '');
  } catch (err) {
    showError('sin respuesta del pad');
  }
}
poll();
setInterval(poll, 1200);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    # Sin keep-alive el navegador abre un socket por consulta y el sondeo de la
    # pose se encola delante de los clics.
    protocol_version = "HTTP/1.1"

    def _send(self, payload: dict | str, status: int = 200, kind: str = "application/json") -> None:
        body = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # La pestaña se cerró o se recargó: no es un fallo del robot.
            self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802 - nombre que impone la stdlib
        if self.path in ("/", "/index.html"):
            self._send(PAGE, kind="text/html")
            return
        if self.path == "/api/state":
            try:
                with _LOCK:
                    link = robot()
                    payload = {"pose": link.pose(), "angles": link.angles(), "mode": link.mode()}
            except (OSError, MG400Error) as exc:
                drop()
                payload = {"error": str(exc)}
            self._send(payload)
            return
        self._send({"error": "no existe"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send({"error": "json invalido"}, status=400)
            return

        routes = ("/api/jog", "/api/jog/stop", "/api/stop", "/api/step")
        if self.path not in routes:
            self._send({"error": "no existe"}, status=404)
            return

        if self.path == "/api/jog/stop":
            jog_stop()
            self._send({"ok": True})
            return

        speed = max(MIN_SPEED, min(MAX_SPEED, int(payload.get("speed", 20))))

        try:
            if self.path == "/api/stop":
                jog_stop()
                with _LOCK:
                    link = link_ready(speed)
                    link.stop()
                self._send({"ok": True})
                return

            axis = str(payload.get("axis", ""))

            if self.path == "/api/step":
                if axis not in CARTESIAN:
                    self._send({"error": f"eje desconocido: {axis}"}, status=400)
                    return
                step = abs(float(payload.get("step", 1.0)))
                if step > MAX_STEP_MM:
                    self._send({"error": f"paso maximo {MAX_STEP_MM} mm"}, status=400)
                    return
                jog_stop()
                with _LOCK:
                    link = link_ready(speed)
                    dx, dy, dz, dr = (value * step for value in CARTESIAN[axis])
                    link.rel_movl(dx, dy, dz, dr, speed=speed, acc=speed)
                    body = {"ok": True, "pose": link.pose()}
                self._send(body)
                return

            # /api/jog: arranque o latido del jog en curso.
            if axis not in JOG:
                self._send({"error": f"eje desconocido: {axis}"}, status=400)
                return

            global _JOG_AXIS, _JOG_DEADLINE
            _JOG_DEADLINE = time.monotonic() + JOG_KEEPALIVE_S
            if _JOG_AXIS == axis:
                # Ya está caminando: esto sólo renueva el plazo del vigilante.
                self._send({"ok": True, "jogging": axis})
                return

            if _JOG_AXIS is not None:
                with _LOCK:
                    robot().jog_stop()
            with _LOCK:
                link = link_ready(speed)
                link.jog(JOG[axis])
            _JOG_AXIS = axis
            self._send({"ok": True, "jogging": axis})
        except (OSError, MG400Error) as exc:
            jog_stop()
            drop()
            self._send({"error": str(exc)})

    def log_message(self, *_args: object) -> None:
        pass


def main() -> None:
    global ROBOT_HOST
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=ROBOT_HOST, help="IP del robot")
    parser.add_argument("--port", type=int, default=8010, help="puerto de la pagina")
    args = parser.parse_args()
    ROBOT_HOST = args.host

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"pad listo en http://127.0.0.1:{args.port}  (robot {ROBOT_HOST})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        jog_stop()
        print("cerrado", flush=True)


if __name__ == "__main__":
    main()
