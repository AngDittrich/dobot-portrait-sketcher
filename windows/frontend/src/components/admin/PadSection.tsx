import { useEffect, useState } from 'react'
import { samplePad } from '../../hooks/usePad'
import type { PadState, PadTune } from '../../hooks/usePad'

const TRAVEL = 22

function signed(value: number): string {
  const shown = value.toFixed(2)
  return value > 0 ? `+${shown}` : shown
}

function Knob({
  x,
  y,
  deadzone,
  label,
}: {
  x: number
  y: number
  deadzone: number
  label: string
}) {
  const ring = Math.min(78, Math.max(12, deadzone * 100))
  return (
    <div className="mando-well" aria-label={label}>
      <span className="mando-ring" style={{ width: `${ring}%`, height: `${ring}%` }} />
      <span
        className="mando-knob"
        style={{ transform: `translate(${x * TRAVEL}px, ${y * TRAVEL}px)` }}
      />
    </div>
  )
}

function FaceButton({
  symbol,
  className,
  down,
}: {
  symbol: string
  className: string
  down: boolean
}) {
  return (
    <span className={`mando-face ${className}${down ? ' is-down' : ''}`} aria-hidden="true">
      {symbol}
    </span>
  )
}

/** Dibujo en vivo del DualShock y los ajustes que cambian cómo se mueve el brazo. */
export function PadSection({
  pad,
  speed,
  onSpeed,
  tune,
  onTune,
  embedded = false,
}: {
  pad: PadState
  speed: number
  onSpeed: (value: number) => void
  tune: PadTune
  onTune: (next: PadTune) => void
  /** Dentro de Control, junto al interruptor de joysticks. */
  embedded?: boolean
}) {
  const [live, setLive] = useState(() => samplePad(tune))

  useEffect(() => {
    let timer = 0
    let last = ''
    const tick = () => {
      const next = samplePad(tune)
      const key = [
        next.name,
        next.unsupported,
        next.lx.toFixed(2),
        next.ly.toFixed(2),
        next.rx.toFixed(2),
        next.ry.toFixed(2),
        next.l2.toFixed(2),
        next.r2.toFixed(2),
        next.sent.x.toFixed(2),
        next.sent.y.toFixed(2),
        next.sent.z.toFixed(2),
        next.sent.j4.toFixed(2),
        next.down.map((item) => (item ? '1' : '0')).join(''),
      ].join('|')
      if (key !== last) {
        last = key
        setLive(next)
      }
      timer = window.setTimeout(tick, 32)
    }
    timer = window.setTimeout(tick, 32)
    return () => window.clearTimeout(timer)
  }, [tune])

  const down = (index: number) => Boolean(live.down[index])
  const present = live.name !== null
  const headline = live.unsupported
    ? 'Hay un control, pero el navegador no lo reconoce como mando estándar.'
    : present
      ? live.name
      : 'Conecta el DualShock por USB'

  return (
    <div className={embedded ? 'admin-mando admin-mando--embedded' : 'admin-section admin-mando'}>
      <section className={`mando-stage${present ? '' : ' is-off'}${pad.armed ? ' is-armed' : ''}`}>
        <div className="mando-triggers" aria-hidden="true">
          <span className={`mando-trigger${live.l2 > 0.05 ? ' is-down' : ''}`}>
            <i style={{ height: `${Math.round(live.l2 * 100)}%` }} />
            <b>L2</b>
          </span>
          <span className={`mando-bumper${down(4) ? ' is-down' : ''}`}>L1</span>
          <span className={`mando-bumper${down(5) ? ' is-down' : ''}`}>R1</span>
          <span className={`mando-trigger${live.r2 > 0.05 ? ' is-down' : ''}`}>
            <i style={{ height: `${Math.round(live.r2 * 100)}%` }} />
            <b>R2</b>
          </span>
        </div>

        <div className="mando-shell">
          <div className="mando-side">
            <Knob x={live.lx} y={live.ly} deadzone={tune.deadzone} label="Palanca izquierda" />
            <span className={`mando-dpad${down(12) || down(13) || down(14) || down(15) ? ' is-down' : ''}`}>
              <i className={down(12) ? 'is-down' : ''} />
              <i className={down(15) ? 'is-down' : ''} />
              <i className={down(13) ? 'is-down' : ''} />
              <i className={down(14) ? 'is-down' : ''} />
            </span>
          </div>

          <div className="mando-heart">
            <p>{headline}</p>
            <strong>{pad.armed ? 'Armado: el brazo obedece' : 'Solo revisión: el brazo no se mueve'}</strong>
            <div className="mando-center-keys" aria-hidden="true">
              <span className={down(8) ? 'is-down' : ''}>Share</span>
              <span className={down(9) ? 'is-down' : ''}>Options</span>
            </div>
          </div>

          <div className="mando-side mando-side--right">
            <div className="mando-diamond" aria-hidden="true">
              <FaceButton symbol="△" className="is-n" down={down(3)} />
              <FaceButton symbol="□" className="is-w" down={down(2)} />
              <FaceButton symbol="○" className="is-e" down={down(1)} />
              <FaceButton symbol="✕" className="is-s" down={down(0)} />
            </div>
            <Knob x={live.rx} y={live.ry} deadzone={tune.deadzone} label="Palanca derecha" />
          </div>
        </div>

        <dl className="mando-sent">
          {(
            [
              ['X', live.sent.x],
              ['Y', live.sent.y],
              ['Z', live.sent.z],
              ['J4', live.sent.j4],
            ] as const
          ).map(([axis, value]) => (
            <div key={axis} className={Math.abs(value) > 0 ? 'is-live' : ''}>
              <dt>{axis}</dt>
              <dd>{signed(value)}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="admin-card mando-config">
        <h3>Ajuste</h3>
        <p className="admin-card-note mando-lead">
          Mueve palancas y gatillos: el dibujo responde aunque el brazo esté quieto. Armar usa estos
          ajustes en el robot.
        </p>

        <div className="admin-sliders">
          <label>
            Zona muerta
            <strong>{Math.round(tune.deadzone * 100)}%</strong>
            <input
              type="range"
              min={5}
              max={40}
              value={Math.round(tune.deadzone * 100)}
              onChange={(event) => onTune({ ...tune, deadzone: Number(event.target.value) / 100 })}
            />
          </label>
          <label>
            Velocidad
            <strong>{speed}%</strong>
            <input
              type="range"
              min={1}
              max={100}
              value={speed}
              onChange={(event) => onSpeed(Number(event.target.value))}
            />
          </label>
        </div>

        <div className="mando-invert" role="group" aria-label="Invertir ejes">
          {(
            [
              ['invertX', 'Izquierda / derecha'],
              ['invertY', 'Adelante / atrás'],
              ['invertJ4', 'Muñeca'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={tune[key] ? 'is-on' : ''}
              aria-pressed={tune[key]}
              onClick={() => onTune({ ...tune, [key]: !tune[key] })}
            >
              {label}
            </button>
          ))}
        </div>

        <button
          type="button"
          className="admin-press admin-press--primary mando-arm"
          onClick={() => pad.arm(!pad.armed)}
        >
          {pad.armed ? 'Desarmar' : 'Armar el brazo'}
        </button>
        <p className="admin-card-note">
          Options también arma. Círculo es el paro. Triángulo arrastra, cruz deja sólido, cuadrado
          borra los logs, L1 y R1 cambian la velocidad, la cruceta da 1 mm y L3 pone J4 en -50.
        </p>
      </section>
    </div>
  )
}
