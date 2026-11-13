import { useRef, useState } from 'react'
import type { AdminCommand, AdminStatus } from '../../lib/api'
import type { AdminActions } from '../../hooks/useAdminActions'
import { useJog } from '../../hooks/useAdminStatus'
import { JoyStick } from './JoyStick'
import { JOINTS, PLANE } from './stickSpaces'

const STEPS = [0.1, 1, 5, 10]

/** Movimiento manual del MG400: sticks, pasos, acciones agrupadas y MovL. */
export function ControlSection({
  status,
  token,
  actions,
  onNotice,
}: {
  status: AdminStatus | null
  token: string
  actions: AdminActions
  onNotice: (message: string) => void
}) {
  const [space, setSpace] = useState<'plano' | 'joints'>('plano')
  const [step, setStep] = useState(1)
  const [speed, setSpeed] = useState(50)
  const [collision, setCollision] = useState(2)
  const [moveKind, setMoveKind] = useState<'movl' | 'movj' | 'jump'>('movl')
  const [pose, setPose] = useState({ x: '', y: '', z: '', r: '' })
  const [doIndex, setDoIndex] = useState(1)
  const [speedl, setSpeedl] = useState(50)
  const [accl, setAccl] = useState(50)
  const [weight, setWeight] = useState('0')
  const [inertia, setInertia] = useState('0')
  const speedRef = useRef(50)
  const collisionRef = useRef(2)
  const speedlRef = useRef(50)
  const acclRef = useRef(50)
  const busy = Boolean(status?.busy)
  // Bit i-1 de do_bits = DOi. Las ToolDO no tienen bit conocido: solo botones.
  const doBits = status?.do_bits ?? null

  const { hold, stickEpoch, moving } = useJog({
    token,
    getSpeed: () => speedRef.current,
    onError: onNotice,
  })

  const sticks = space === 'plano' ? PLANE : JOINTS
  const live = status?.pose ?? []

  async function readInputs() {
    await actions.readInputs().catch(() => undefined)
  }

  const poseNumbers = {
    x: Number(pose.x),
    y: Number(pose.y),
    z: Number(pose.z),
    r: Number(pose.r),
  }
  const poseReady = Object.values(poseNumbers).every((value) => Number.isFinite(value))

  const groups: { title: string; disabled?: boolean; actions: { label: string; command: AdminCommand }[] }[] = [
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
    {
      title: 'Pruebas',
      // El backend las bloquea dibujando: el botón avisa antes de intentarlo.
      disabled: busy,
      actions: [
        { label: 'Cuadrado 30 mm', command: { action: 'square' } },
        { label: 'Arco 40 mm', command: { action: 'arc' } },
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
          {!busy && moving ? ' Moviendo…' : ''}
          {status?.source === 'feedback'
            ? ' Estado en vivo (feedback).'
            : ' Estado por sondeo.'}
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
                  onClick={() => void actions.send({ action: 'step', axis, mm: step, speed })}
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
                      disabled={group.disabled}
                      onClick={() => void actions.send(command)}
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
                <button type="button" className="admin-press" onClick={() => void actions.readToolInput(1)}>
                  Leer ToolDI1
                </button>
                <button type="button" className="admin-press" onClick={() => void actions.readToolInput(2)}>
                  Leer ToolDI2
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
                onPointerUp={() => void actions.send({ action: 'speed', value: speedRef.current })}
                onBlur={() => void actions.send({ action: 'speed', value: speedRef.current })}
              />
            </label>
            <label>
              Vel. lineal (SpeedL)
              <strong>{speedl}%</strong>
              <input
                type="range"
                min={1}
                max={100}
                value={speedl}
                onChange={(event) => {
                  const value = Number(event.target.value)
                  speedlRef.current = value
                  setSpeedl(value)
                }}
                onPointerUp={() => void actions.send({ action: 'speedl', value: speedlRef.current })}
                onBlur={() => void actions.send({ action: 'speedl', value: speedlRef.current })}
              />
            </label>
            <label>
              Acel. lineal (AccL)
              <strong>{accl}%</strong>
              <input
                type="range"
                min={1}
                max={100}
                value={accl}
                onChange={(event) => {
                  const value = Number(event.target.value)
                  acclRef.current = value
                  setAccl(value)
                }}
                onPointerUp={() => void actions.send({ action: 'accl', value: acclRef.current })}
                onBlur={() => void actions.send({ action: 'accl', value: acclRef.current })}
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
                onPointerUp={() => void actions.send({ action: 'collision', value: collisionRef.current })}
                onBlur={() => void actions.send({ action: 'collision', value: collisionRef.current })}
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
              if (poseReady) void actions.send({ action: moveKind, ...poseNumbers, speed })
            }}
          >
            <div className="admin-segment" role="group" aria-label="Tipo de movimiento">
              {(
                [
                  ['movl', 'MovL'],
                  ['movj', 'Ir rápido (MovJ)'],
                  ['jump', 'Saltar (Jump)'],
                ] as const
              ).map(([kind, label]) => (
                <button
                  key={kind}
                  type="button"
                  className={moveKind === kind ? 'is-on' : ''}
                  onClick={() => setMoveKind(kind)}
                >
                  {label}
                </button>
              ))}
            </div>
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
                onClick={() => poseReady && void actions.send({ action: 'inverse', ...poseNumbers })}
              >
                ¿Tiene solución?
              </button>
              <button type="submit" className="admin-press" disabled={!poseReady || busy}>
                Ir aquí
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

        <section className="admin-card">
          <h3>Salidas</h3>
          <div className="admin-pose">
            <label>
              DO (1–24)
              <input
                inputMode="numeric"
                value={String(doIndex)}
                onChange={(event) => {
                  const value = Math.trunc(Number(event.target.value))
                  if (Number.isFinite(value)) setDoIndex(Math.min(24, Math.max(1, value)))
                }}
              />
            </label>
            <div className="admin-pose-actions">
              <button
                type="button"
                className="admin-press"
                onClick={() => void actions.send({ action: 'do', index: doIndex, status: 1 })}
              >
                Encender DO{doIndex}
              </button>
              <button
                type="button"
                className="admin-press"
                onClick={() => void actions.send({ action: 'do', index: doIndex, status: 0 })}
              >
                Apagar DO{doIndex}
              </button>
              <button
                type="button"
                className="admin-press"
                onClick={() => void actions.send({ action: 'tooldo', index: 1, status: 1 })}
              >
                ToolDO1 on
              </button>
              <button
                type="button"
                className="admin-press"
                onClick={() => void actions.send({ action: 'tooldo', index: 1, status: 0 })}
              >
                ToolDO1 off
              </button>
              <button
                type="button"
                className="admin-press"
                onClick={() => void actions.send({ action: 'tooldo', index: 2, status: 1 })}
              >
                ToolDO2 on
              </button>
              <button
                type="button"
                className="admin-press"
                onClick={() => void actions.send({ action: 'tooldo', index: 2, status: 0 })}
              >
                ToolDO2 off
              </button>
            </div>
          </div>
          <p className="admin-card-note">
            {doBits === null
              ? 'Sin estado vivo de salidas (acerca el robot o revisa la conexión).'
              : `DO en vivo: ${[1, 2, 3, 4, 5, 6, 7, 8]
                  .map((i) => `DO${i} ${((doBits >> (i - 1)) & 1) === 1 ? 'on' : 'off'}`)
                  .join(' · ')}`}
          </p>
        </section>

        <section className="admin-card">
          <h3>Carga de la herramienta</h3>
          <form
            className="admin-pose"
            onSubmit={(event) => {
              event.preventDefault()
              const w = Number(weight)
              const inertiaValue = Number(inertia)
              if (Number.isFinite(w) && Number.isFinite(inertiaValue)) {
                void actions.send({ action: 'payload', weight: w, inertia: inertiaValue })
              }
            }}
          >
            <label>
              Peso kg (0–5)
              <input inputMode="decimal" value={weight} onChange={(event) => setWeight(event.target.value)} />
            </label>
            <label>
              Inercia (0–1)
              <input inputMode="decimal" value={inertia} onChange={(event) => setInertia(event.target.value)} />
            </label>
            <div className="admin-pose-actions">
              <button type="submit" className="admin-press">
                Fijar carga
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  )
}
