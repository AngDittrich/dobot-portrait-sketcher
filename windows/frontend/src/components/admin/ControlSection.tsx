import { useRef, useState } from 'react'
import { adminCommand } from '../../lib/api'
import type { AdminCommand, AdminStatus } from '../../lib/api'
import { useJog } from '../../hooks/useAdminStatus'
import { JoyStick } from './JoyStick'
import { JOINTS, PLANE } from './stickSpaces'

const STEPS = [0.1, 1, 5, 10]

/** Movimiento manual del MG400: sticks, pasos, acciones agrupadas y MovL. */
export function ControlSection({
  status,
  token,
  send,
  onNotice,
}: {
  status: AdminStatus | null
  token: string
  send: (command: AdminCommand) => Promise<void>
  onNotice: (message: string) => void
}) {
  const [space, setSpace] = useState<'plano' | 'joints'>('plano')
  const [step, setStep] = useState(1)
  const [speed, setSpeed] = useState(50)
  const [collision, setCollision] = useState(2)
  const [pose, setPose] = useState({ x: '', y: '', z: '', r: '' })
  const speedRef = useRef(50)
  const collisionRef = useRef(2)
  const busy = Boolean(status?.busy)

  const { hold, stickEpoch } = useJog({
    token,
    getSpeed: () => speedRef.current,
    onError: onNotice,
  })

  const sticks = space === 'plano' ? PLANE : JOINTS
  const live = status?.pose ?? []

  async function readInputs() {
    const bits: string[] = []
    for (const index of [1, 2, 3, 4]) {
      try {
        const result = await adminCommand(token, { action: 'di', index })
        bits.push(`DI${index} ${result.value || 'sin valor'}`)
      } catch {
        bits.push(`DI${index} sin respuesta`)
      }
    }
    onNotice(bits.join(' · '))
  }

  const poseNumbers = {
    x: Number(pose.x),
    y: Number(pose.y),
    z: Number(pose.z),
    r: Number(pose.r),
  }
  const poseReady = Object.values(poseNumbers).every((value) => Number.isFinite(value))

  const groups: { title: string; actions: { label: string; command: AdminCommand }[] }[] = [
    {
      title: 'Energía',
      actions: [
        { label: 'Habilitar', command: { action: 'enable' } },
        { label: 'Deshabilitar', command: { action: 'disable' } },
      ],
    },
    {
      title: 'Flujo',
      actions: [
        { label: 'Pausar', command: { action: 'pause' } },
        { label: 'Continuar', command: { action: 'continue' } },
      ],
    },
    {
      title: 'Mano guiada',
      actions: [
        { label: 'Arrastrar', command: { action: 'drag', on: true } },
        { label: 'Soltar', command: { action: 'drag', on: false } },
      ],
    },
    {
      title: 'Muñeca',
      actions: [{ label: 'J4 a -50', command: { action: 'j4home' } }],
    },
    {
      title: 'Diagnóstico',
      actions: [
        { label: 'Limpiar alarma', command: { action: 'clear' } },
        { label: 'Reiniciar', command: { action: 'reset' } },
      ],
    },
  ]

  return (
    <div className="admin-section admin-control">
      <section className="admin-card admin-card--drive">
        <header className="admin-card-head">
          <h3>Movimiento manual</h3>
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
        </header>

        <div className="admin-sticks">
          <JoyStick
            key={`${space}-primary-${stickEpoch}`}
            title={sticks.primary.title}
            axes={sticks.primary.axes}
            disabled={busy}
            onHold={(axis) => hold('primary', axis)}
          />
          <JoyStick
            key={`${space}-secondary-${stickEpoch}`}
            title={sticks.secondary.title}
            axes={sticks.secondary.axes}
            disabled={busy}
            onHold={(axis) => hold('secondary', axis)}
          />
        </div>
        <p className="admin-card-note">
          Mantén el joystick: el brazo sigue hasta que lo sueltas.
          {busy ? ' Está dibujando; el joystick espera a que termine.' : ''}
        </p>

        <div className="admin-nudge">
          <div className="admin-nudge-size">
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
          </div>
          <div className="admin-nudge-axes">
            {Object.values(sticks).flatMap((stick) =>
              [stick.axes.up, stick.axes.down, stick.axes.left, stick.axes.right].filter(Boolean).map((axis) => (
                <button
                  key={axis}
                  type="button"
                  className="admin-press"
                  disabled={busy}
                  onClick={() => void send({ action: 'step', axis, mm: step, speed })}
                >
                  {axis}
                </button>
              )),
            )}
          </div>
        </div>
      </section>

      <div className="admin-control-side">
        <section className="admin-card">
          <h3>Acciones</h3>
          <div className="admin-action-groups">
            {groups.map((group) => (
              <div key={group.title} className="admin-action-group">
                <span>{group.title}</span>
                <div>
                  {group.actions.map(({ label, command }) => (
                    <button
                      key={label}
                      type="button"
                      className="admin-press"
                      onClick={() => void send(command)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className="admin-action-group">
              <span>Entradas</span>
              <div>
                <button type="button" className="admin-press" onClick={() => void readInputs()}>
                  Leer DI1–DI4
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="admin-card">
          <h3>Velocidad y colisión</h3>
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
        </section>

        <section className="admin-card">
          <h3>Mover a una pose</h3>
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
            <div className="admin-pose-actions">
              <button
                type="button"
                className="admin-press"
                disabled={!poseReady}
                onClick={() => poseReady && void send({ action: 'inverse', ...poseNumbers })}
              >
                ¿Tiene solución?
              </button>
              <button type="submit" className="admin-press" disabled={!poseReady || busy}>
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
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
