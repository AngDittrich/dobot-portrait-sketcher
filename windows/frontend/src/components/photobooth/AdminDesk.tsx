import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { adminCommand, adminStatus, unlockAdmin } from '../../lib/api'
import type { AdminCommand, AdminStatus } from '../../lib/api'

/**
 * Panel de taller del MG400. El PIN se comprueba en el backend; el token
 * no se guarda, así que cerrar el panel vuelve a pedirlo.
 *
 * El joystick manda MoveJog al salir de la zona muerta y MoveJog() al
 * soltar. El brazo sigue en el controlador entre esas dos órdenes, así que
 * no hace falta un websocket para que el movimiento sea continuo.
 */

const STEPS = [0.1, 1, 5, 10]

type Axes = { up: string; down: string; left: string; right: string }
type StickId = 'primary' | 'secondary'

const PLANE: Record<StickId, { title: string; axes: Axes }> = {
  primary: { title: 'Plano XY', axes: { up: 'Y+', down: 'Y-', left: 'X-', right: 'X+' } },
  secondary: { title: 'Altura y muñeca', axes: { up: 'Z+', down: 'Z-', left: 'R-', right: 'R+' } },
}

const JOINTS: Record<StickId, { title: string; axes: Axes }> = {
  primary: { title: 'J1 y J2', axes: { up: 'J1+', down: 'J1-', left: 'J2-', right: 'J2+' } },
  secondary: { title: 'J3 y J4', axes: { up: 'J3+', down: 'J3-', left: 'J4-', right: 'J4+' } },
}

function overlay(node: ReactNode) {
  return createPortal(node, document.body)
}

function format(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number)) return '—'
  return number.toFixed(2)
}

function axisFromOffset(dx: number, dy: number, dead: number, axes: Axes): string | null {
  if (Math.hypot(dx, dy) < dead) return null
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? axes.right : axes.left
  return dy > 0 ? axes.down : axes.up
}

function JoyStick({
  title,
  axes,
  disabled,
  onHold,
}: {
  title: string
  axes: Axes
  disabled: boolean
  onHold: (axis: string | null) => void
}) {
  const well = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const hotRef = useRef<string | null>(null)
  const [knob, setKnob] = useState({ x: 0, y: 0 })
  const [hot, setHot] = useState<string | null>(null)
  const [tracking, setTracking] = useState(false)
  const onHoldRef = useRef(onHold)
  useEffect(() => {
    onHoldRef.current = onHold
  }, [onHold])

  useEffect(() => {
    return () => {
      if (!dragging.current) return
      dragging.current = false
      onHoldRef.current(null)
    }
  }, [])

  useEffect(() => {
    if (!disabled || !dragging.current) return
    dragging.current = false
    hotRef.current = null
    setKnob({ x: 0, y: 0 })
    setHot(null)
    setTracking(false)
    onHoldRef.current(null)
  }, [disabled])

  function sample(event: ReactPointerEvent<HTMLDivElement>) {
    const node = well.current
    if (!node) return null
    const rect = node.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    let dx = event.clientX - cx
    let dy = event.clientY - cy
    const dist = Math.hypot(dx, dy)
    const max = rect.width * 0.32
    if (dist > max && dist > 0) {
      dx = (dx / dist) * max
      dy = (dy / dist) * max
    }
    return { dx, dy, axis: axisFromOffset(dx, dy, rect.width * 0.16, axes) }
  }

  function aim(event: ReactPointerEvent<HTMLDivElement>) {
    const next = sample(event)
    if (!next) return
    setKnob({ x: next.dx, y: next.dy })
    if (next.axis === hotRef.current) return
    hotRef.current = next.axis
    setHot(next.axis)
    onHoldRef.current(next.axis)
  }

  function release() {
    if (!dragging.current) return
    dragging.current = false
    hotRef.current = null
    setTracking(false)
    setHot(null)
    onHoldRef.current(null)
    requestAnimationFrame(() => setKnob({ x: 0, y: 0 }))
  }

  return (
    <div className={`admin-stick-wrap${disabled ? ' is-disabled' : ''}`}>
      <span className="admin-stick-title">{title}</span>
      <div
        ref={well}
        className={`admin-stick${hot ? ' is-live' : ''}${tracking ? ' is-tracking' : ''}`}
        role="application"
        aria-label={title}
        onPointerDown={(event) => {
          if (disabled) return
          event.preventDefault()
          event.currentTarget.setPointerCapture(event.pointerId)
          dragging.current = true
          setTracking(true)
          aim(event)
        }}
        onPointerMove={(event) => {
          if (!dragging.current) return
          aim(event)
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onLostPointerCapture={release}
      >
        <i className={hot === axes.up ? 'is-hot' : ''}>{axes.up}</i>
        <i className={`admin-stick-east ${hot === axes.right ? 'is-hot' : ''}`}>{axes.right}</i>
        <i className={`admin-stick-south ${hot === axes.down ? 'is-hot' : ''}`}>{axes.down}</i>
        <i className={`admin-stick-west ${hot === axes.left ? 'is-hot' : ''}`}>{axes.left}</i>
        <span className="admin-stick-cross" />
        <span
          className="admin-stick-knob"
          style={{ transform: `translate(${knob.x}px, ${knob.y}px)` }}
        />
      </div>
    </div>
  )
}

export function AdminDesk() {
  const [phase, setPhase] = useState<'closed' | 'pin' | 'panel'>('closed')
  const [pin, setPin] = useState('')
  const [wrong, setWrong] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const [status, setStatus] = useState<AdminStatus | null>(null)
  const [notice, setNotice] = useState('')
  const [step, setStep] = useState(1)
  const [space, setSpace] = useState<'plano' | 'joints'>('plano')
  const [pose, setPose] = useState({ x: '', y: '', z: '', r: '' })
  const [speed, setSpeed] = useState(50)
  const [collision, setCollision] = useState(2)
  const [stickEpoch, setStickEpoch] = useState(0)
  const sending = useRef(false)
  const speedRef = useRef(50)
  const collisionRef = useRef(2)
  const jogging = useRef(false)
  const desired = useRef<string | null>(null)
  const applied = useRef<string | null>(null)
  const owner = useRef<StickId | null>(null)
  const chain = useRef(Promise.resolve())
  const tokenRef = useRef<string | null>(null)
  useEffect(() => {
    tokenRef.current = token
  }, [token])

  const sticks = space === 'plano' ? PLANE : JOINTS

  function close() {
    setPhase('closed')
    setToken(null)
    setPin('')
    setWrong(false)
    setNotice('')
    setStatus(null)
  }

  async function submitPin(next: string) {
    if (sending.current || next.length !== 4) return
    sending.current = true
    try {
      const issued = await unlockAdmin(next)
      setToken(issued)
      setPhase('panel')
      setWrong(false)
    } catch {
      setWrong(true)
      setPin('')
    } finally {
      sending.current = false
    }
  }

  useEffect(() => {
    if (phase !== 'panel' || !token) return
    let stop = false
    const tick = async () => {
      try {
        const next = await adminStatus(token)
        if (!stop) setStatus(next)
      } catch (error) {
        if (!stop) setNotice(error instanceof Error ? error.message : 'sin respuesta')
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 800)
    return () => {
      stop = true
      window.clearInterval(timer)
      desired.current = null
      owner.current = null
      const issued = token
      void chain.current.then(() => {
        if (applied.current === null && !jogging.current) return
        applied.current = null
        jogging.current = false
        return adminCommand(issued, { action: 'jog', axis: '' }).catch(() => undefined)
      })
    }
  }, [phase, token])

  function failJog(error: unknown) {
    desired.current = null
    applied.current = null
    owner.current = null
    jogging.current = false
    setStickEpoch((value) => value + 1)
    setNotice(error instanceof Error ? error.message : 'el robot rechazó el movimiento')
  }

  function hold(stick: StickId, axis: string | null) {
    const issued = tokenRef.current
    if (!issued) return
    if (axis === null) {
      if (owner.current !== stick) return
      owner.current = null
    } else {
      owner.current = stick
    }
    desired.current = axis
    chain.current = chain.current
      .then(async () => {
        while (applied.current !== desired.current) {
          const next = desired.current
          await adminCommand(issued, { action: 'jog', axis: next ?? '', speed: next ? speedRef.current : undefined })
          applied.current = next
          jogging.current = next !== null
        }
      })
      .catch((error: unknown) => {
        failJog(error)
      })
  }

  async function readInputs() {
    if (!token) return
    const bits: string[] = []
    for (const index of [1, 2, 3, 4]) {
      try {
        const result = await adminCommand(token, { action: 'di', index })
        bits.push(`DI${index} ${result.value || 'sin valor'}`)
      } catch {
        bits.push(`DI${index} sin respuesta`)
      }
    }
    setNotice(bits.join(' · '))
  }

  async function send(command: AdminCommand) {
    if (!token) return
    try {
      await adminCommand(token, command)
      setNotice('')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'el robot rechazó la orden')
    }
  }

  async function nudge(axis: string) {
    await send({ action: 'step', axis, mm: step, speed })
  }

  const poseNumbers = {
    x: Number(pose.x),
    y: Number(pose.y),
    z: Number(pose.z),
    r: Number(pose.r),
  }
  const poseReady = Object.values(poseNumbers).every((value) => Number.isFinite(value))
  const live = status?.pose ?? []
  const angles = status?.angles ?? []
  const banner =
    status?.alarm_text ||
    notice ||
    (status?.busy
      ? 'El robot está dibujando. El joystick espera a que termine.'
      : status?.connected
        ? 'Mantén el joystick: el brazo sigue hasta que lo sueltas.'
        : status?.detail || 'Conectando…')

  return (
    <>
      <button type="button" className="booth-admin-entry admin-press" onClick={() => setPhase('pin')}>
        Admin
      </button>

      {phase === 'pin' &&
        overlay(
          <div className="admin-veil" role="presentation" onClick={close}>
            <form
              className={`admin-glass admin-pin${wrong ? ' is-wrong' : ''}`}
              role="dialog"
              aria-modal="true"
              aria-labelledby="admin-pin-title"
              onClick={(event) => event.stopPropagation()}
              onSubmit={(event) => {
                event.preventDefault()
                void submitPin(pin)
              }}
            >
              <h2 id="admin-pin-title">Panel del robot</h2>
              <p>PIN de 4 dígitos</p>
              <div className="admin-pin-cells" aria-hidden="true">
                {[0, 1, 2, 3].map((index) => (
                  <span key={index} className={pin.length > index ? 'is-filled' : ''}>
                    {pin[index] ? '•' : ''}
                  </span>
                ))}
              </div>
              <input
                autoFocus
                inputMode="numeric"
                autoComplete="off"
                aria-label="PIN de 4 dígitos"
                value={pin}
                onChange={(event) => {
                  const next = event.target.value.replace(/\D/g, '').slice(0, 4)
                  setWrong(false)
                  setPin(next)
                  if (next.length === 4) void submitPin(next)
                }}
              />
            </form>
          </div>,
        )}

      {phase === 'panel' &&
        token &&
        overlay(
          <div className="admin-veil" role="presentation">
            <section className="admin-glass admin-panel" role="dialog" aria-modal="true" aria-labelledby="admin-panel-title">
              <header className="admin-panel-head">
                <div>
                  <h2 id="admin-panel-title">Robot MG400</h2>
                  <p>
                    <span className={`admin-dot${status?.connected ? ' is-on' : ''}`} />
                    {status?.connected
                      ? `${status.mode_label || 'conectado'}`
                      : 'sin enlace'}
                    {status?.busy ? ' · dibujando' : ''}
                  </p>
                </div>
                <div className="admin-segment" role="group" aria-label="Espacio de movimiento">
                  <button
                    type="button"
                    className={space === 'plano' ? 'is-on' : ''}
                    onClick={() => setSpace('plano')}
                  >
                    Plano
                  </button>
                  <button
                    type="button"
                    className={space === 'joints' ? 'is-on' : ''}
                    onClick={() => setSpace('joints')}
                  >
                    Articulaciones
                  </button>
                </div>
                <button type="button" className="admin-text admin-press" onClick={close}>
                  Cerrar
                </button>
              </header>

              <div className="admin-readout">
                <span>X {format(live[0])}</span>
                <span>Y {format(live[1])}</span>
                <span>Z {format(live[2])}</span>
                <span>R {format(live[3])}</span>
                {[0, 1, 2, 3].map((index) => (
                  <span key={index}>
                    J{index + 1} {format(angles[index])}
                  </span>
                ))}
              </div>
              <p className={`admin-banner${status?.alarm_text || notice ? ' is-alert' : ''}`}>{banner}</p>

              <div className="admin-panel-body">
                <div className="admin-stage">
                  <div className="admin-drive">
                    <div className="admin-sticks">
                      <JoyStick
                        key={`${space}-primary-${stickEpoch}`}
                        title={sticks.primary.title}
                        axes={sticks.primary.axes}
                        disabled={Boolean(status?.busy)}
                        onHold={(axis) => hold('primary', axis)}
                      />
                      <JoyStick
                        key={`${space}-secondary-${stickEpoch}`}
                        title={sticks.secondary.title}
                        axes={sticks.secondary.axes}
                        disabled={Boolean(status?.busy)}
                        onHold={(axis) => hold('secondary', axis)}
                      />
                    </div>

                    <div className="admin-nudge">
                      <span>Un paso</span>
                      <div className="admin-segment" role="group" aria-label="Tamaño del paso">
                        {STEPS.map((size) => (
                          <button
                            key={size}
                            type="button"
                            className={step === size ? 'is-on' : ''}
                            onClick={() => setStep(size)}
                          >
                            {size}
                          </button>
                        ))}
                      </div>
                      <div className="admin-nudge-axes">
                        {Object.values(sticks).flatMap((stick) =>
                          [stick.axes.up, stick.axes.down, stick.axes.left, stick.axes.right].map((axis) => (
                            <button
                              key={axis}
                              type="button"
                              className="admin-press"
                              disabled={Boolean(status?.busy)}
                              onClick={() => void nudge(axis)}
                            >
                              {axis}
                            </button>
                          )),
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="admin-side">
                    <div className="admin-actions">
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'enable' })}>
                        Habilitar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'disable' })}>
                        Deshabilitar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'clear' })}>
                        Limpiar alarma
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'continue' })}>
                        Continuar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'pause' })}>
                        Pausar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'drag', on: true })}>
                        Arrastrar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'drag', on: false })}>
                        Soltar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void send({ action: 'reset' })}>
                        Reiniciar
                      </button>
                      <button type="button" className="admin-press" onClick={() => void readInputs()}>
                        Entradas
                      </button>
                      <button type="button" className="admin-press is-stop" onClick={() => void send({ action: 'estop' })}>
                        Paro
                      </button>
                    </div>

                    <div className="admin-sliders">
                      <label>
                        Velocidad
                        <strong>{speed}%</strong>
                        <input
                          type="range"
                          min={1}
                          max={100}
                          value={speed}
                          onChange={(event) => {
                            const value = Number(event.target.value)
                            speedRef.current = value
                            setSpeed(value)
                          }}
                          onPointerUp={() => void send({ action: 'speed', value: speedRef.current })}
                          onBlur={() => void send({ action: 'speed', value: speedRef.current })}
                        />
                      </label>
                      <label>
                        Colisión
                        <strong>{collision}</strong>
                        <input
                          type="range"
                          min={0}
                          max={5}
                          step={1}
                          value={collision}
                          onChange={(event) => {
                            const value = Number(event.target.value)
                            collisionRef.current = value
                            setCollision(value)
                          }}
                          onPointerUp={() => void send({ action: 'collision', value: collisionRef.current })}
                          onBlur={() => void send({ action: 'collision', value: collisionRef.current })}
                        />
                      </label>
                    </div>

                    <form
                      className="admin-pose"
                      onSubmit={(event) => {
                        event.preventDefault()
                        if (poseReady) void send({ action: 'movl', ...poseNumbers, speed })
                      }}
                    >
                      {(['x', 'y', 'z', 'r'] as const).map((key) => (
                        <label key={key}>
                          {key.toUpperCase()}
                          <input
                            inputMode="decimal"
                            value={pose[key]}
                            onChange={(event) => setPose((current) => ({ ...current, [key]: event.target.value }))}
                          />
                        </label>
                      ))}
                      <button
                        type="button"
                        className="admin-press"
                        disabled={!poseReady}
                        onClick={() => poseReady && void send({ action: 'inverse', ...poseNumbers })}
                      >
                        ¿Tiene solución?
                      </button>
                      <button type="submit" className="admin-press" disabled={!poseReady || status?.busy}>
                        Mover aquí
                      </button>
                      <button
                        type="button"
                        className="admin-press"
                        disabled={live.length < 4}
                        onClick={() =>
                          setPose({
                            x: String(live[0] ?? ''),
                            y: String(live[1] ?? ''),
                            z: String(live[2] ?? ''),
                            r: String(live[3] ?? ''),
                          })
                        }
                      >
                        Usar pose actual
                      </button>
                    </form>
                    <p className="admin-hint">
                      Hoja {format(Number(status?.frame?.origin_x))} , {format(Number(status?.frame?.origin_y))}
                      {' · '}Z {format(Number(status?.frame?.z_draw))} / {format(Number(status?.frame?.z_travel))}
                      {' · '}R {format(Number(status?.frame?.r))} → {format(Number(status?.frame?.r_far))}
                    </p>
                  </div>
                </div>
              </div>
            </section>
          </div>,
        )}
    </>
  )
}
