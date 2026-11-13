import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  AlarmClockOff,
  Crosshair,
  Eye,
  Gamepad2,
  Hand,
  Joystick,
  Lock,
  MapPin,
  Pause,
  Play,
  PlugZap,
  Power,
  PowerOff,
  RotateCcw,
  RotateCw,
  Spline,
  Square,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AdminStatus } from '../../lib/api'
import type { AdminActions } from '../../hooks/useAdminActions'
import { useJog } from '../../hooks/useAdminStatus'
import type { PadState, PadTune } from '../../hooks/usePad'
import { JoyStick } from './JoyStick'
import { PadSection } from './PadSection'
import { JOINTS, PLANE } from './stickSpaces'

const STEPS = [0.1, 1, 5, 10]

/** Movimiento manual: joysticks o mando, y debajo las acciones del brazo. */
export function ControlSection({
  status,
  token,
  actions,
  onNotice,
  speed,
  onSpeed,
  pad,
  tune,
  onTune,
}: {
  status: AdminStatus | null
  token: string
  actions: AdminActions
  onNotice: (message: string) => void
  speed: number
  onSpeed: (value: number) => void
  pad: PadState
  tune: PadTune
  onTune: (next: PadTune) => void
}) {
  const [drive, setDrive] = useState<'sticks' | 'pad'>('sticks')
  const [space, setSpace] = useState<'plano' | 'joints'>('plano')
  const [step, setStep] = useState(1)
  const [moveKind, setMoveKind] = useState<'movl' | 'movj' | 'jump'>('movl')
  const [pose, setPose] = useState({ x: '', y: '', z: '', r: '' })
  const [doIndex, setDoIndex] = useState(1)
  const speedRef = useRef(speed)
  useEffect(() => {
    speedRef.current = speed
  }, [speed])
  const busy = Boolean(status?.busy)
  const doBits = status?.do_bits ?? null

  const { hold, stickEpoch, moving } = useJog({
    token,
    getSpeed: () => speedRef.current,
    onError: onNotice,
  })

  const sticks = space === 'plano' ? PLANE : JOINTS
  const live = status?.pose ?? []
  const poseNumbers = {
    x: Number(pose.x),
    y: Number(pose.y),
    z: Number(pose.z),
    r: Number(pose.r),
  }
  const poseReady = Object.values(poseNumbers).every((value) => Number.isFinite(value))
  const j4Label = typeof status?.j4_fixed === 'number' ? status.j4_fixed.toFixed(1) : '-50'

  return (
    <div className="admin-section admin-control">
      <section className="admin-card admin-card--drive">
        <header className="admin-card-head">
          <h3>Cómo mover</h3>
          <div className="admin-segment" role="group" aria-label="Forma de controlar el brazo">
            <button type="button" className={drive === 'sticks' ? 'is-on' : ''} onClick={() => setDrive('sticks')}>
              <Joystick size={15} aria-hidden="true" />
              Joysticks
            </button>
            <button type="button" className={drive === 'pad' ? 'is-on' : ''} onClick={() => setDrive('pad')}>
              <Gamepad2 size={15} aria-hidden="true" />
              Mando
            </button>
          </div>
        </header>

        {drive === 'sticks' ? (
          <>
            <div className="admin-card-head">
              <p className="admin-card-note">
                Mantén el joystick: el brazo sigue hasta que lo sueltas.
                {busy ? ' Está dibujando; el joystick espera a que termine.' : ''}
                {!busy && moving ? ' Moviendo…' : ''}
              </p>
              <div className="admin-segment" role="group" aria-label="Espacio de movimiento">
                <button type="button" className={space === 'plano' ? 'is-on' : ''} onClick={() => setSpace('plano')}>
                  Plano
                </button>
                <button type="button" className={space === 'joints' ? 'is-on' : ''} onClick={() => setSpace('joints')}>
                  Articulaciones
                </button>
              </div>
            </div>
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
            <div className="admin-nudge">
              <div className="admin-nudge-size">
                <span>Un paso</span>
                <div className="admin-segment" role="group" aria-label="Tamaño del paso">
                  {STEPS.map((size) => (
                    <button key={size} type="button" className={step === size ? 'is-on' : ''} onClick={() => setStep(size)}>
                      {size}
                    </button>
                  ))}
                </div>
              </div>
              <div className="admin-nudge-axes">
                {Object.values(sticks)
                  .flatMap((stick) => [stick.axes.up, stick.axes.down, stick.axes.left, stick.axes.right].filter(Boolean))
                  .map((axis) => (
                    <button
                      key={axis}
                      type="button"
                      className="admin-press"
                      disabled={busy}
                      onClick={() => void actions.send({ action: 'step', axis, mm: step, speed })}
                    >
                      {axis}
                    </button>
                  ))}
              </div>
            </div>
          </>
        ) : (
          <PadSection embedded pad={pad} speed={speed} onSpeed={onSpeed} tune={tune} onTune={onTune} />
        )}
      </section>

      <div className="admin-control-grid">
        <div className="admin-control-col">
          <Tile icon={Power} title="Energía" hint="Enciende o apaga los motores.">
            <Press icon={Power} label="Habilitar" onClick={() => void actions.send({ action: 'enable' })} />
            <Press icon={PowerOff} label="Deshabilitar" onClick={() => void actions.send({ action: 'disable' })} />
          </Tile>
          <Tile icon={Pause} title="Flujo" hint="Pausa lo que está haciendo y lo sigue.">
            <Press icon={Pause} label="Pausar" onClick={() => void actions.send({ action: 'pause' })} />
            <Press icon={Play} label="Continuar" onClick={() => void actions.send({ action: 'continue' })} />
          </Tile>
          <Tile icon={Hand} title="Mano guiada" hint="Sujeta el brazo y muévelo a mano.">
            <Press icon={Hand} label="Arrastrar" onClick={() => void actions.send({ action: 'drag', on: true })} />
            <Press icon={Lock} label="Soltar" onClick={() => void actions.send({ action: 'drag', on: false })} />
          </Tile>
          <Tile icon={RotateCw} title="Muñeca" hint="Deja J4 en el ángulo de la hoja.">
            <Press icon={RotateCw} label={`J4 a ${j4Label}`} onClick={() => void actions.send({ action: 'j4home' })} />
          </Tile>
          <Tile icon={AlarmClockOff} title="Diagnóstico" hint="Quita la alarma o reinicia el control.">
            <Press icon={AlarmClockOff} label="Limpiar alarma" onClick={() => void actions.send({ action: 'clear' })} />
            <Press icon={RotateCcw} label="Reiniciar" onClick={() => void actions.send({ action: 'reset' })} />
          </Tile>
        </div>

        <div className="admin-control-col">
          <Tile icon={MapPin} title="Mover a una pose" hint="Escribe X Y Z R y elige cómo llega.">
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
                    ['movj', 'Ir rápido'],
                    ['jump', 'Saltar'],
                  ] as const
                ).map(([kind, label]) => (
                  <button key={kind} type="button" className={moveKind === kind ? 'is-on' : ''} onClick={() => setMoveKind(kind)}>
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
                <Press
                  icon={MapPin}
                  label="¿Tiene solución?"
                  disabled={!poseReady}
                  onClick={() => poseReady && void actions.send({ action: 'inverse', ...poseNumbers })}
                />
                <button type="submit" className="admin-press" disabled={!poseReady || busy}>
                  <MapPin size={16} aria-hidden="true" />
                  Ir aquí
                </button>
                <Press
                  icon={Crosshair}
                  label="Usar pose actual"
                  disabled={live.length < 4}
                  onClick={() =>
                    setPose({
                      x: String(live[0] ?? ''),
                      y: String(live[1] ?? ''),
                      z: String(live[2] ?? ''),
                      r: String(live[3] ?? ''),
                    })
                  }
                />
              </div>
            </form>
          </Tile>

          <Tile icon={PlugZap} title="Salidas" hint="Enciende una salida digital o las de la herramienta.">
            <div className="admin-pose admin-pose--io">
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
                <Press icon={PlugZap} label={`Encender DO${doIndex}`} onClick={() => void actions.send({ action: 'do', index: doIndex, status: 1 })} />
                <Press icon={PowerOff} label={`Apagar DO${doIndex}`} onClick={() => void actions.send({ action: 'do', index: doIndex, status: 0 })} />
                <Press icon={PlugZap} label="ToolDO1 on" onClick={() => void actions.send({ action: 'tooldo', index: 1, status: 1 })} />
                <Press icon={PowerOff} label="ToolDO1 off" onClick={() => void actions.send({ action: 'tooldo', index: 1, status: 0 })} />
                <Press icon={PlugZap} label="ToolDO2 on" onClick={() => void actions.send({ action: 'tooldo', index: 2, status: 1 })} />
                <Press icon={PowerOff} label="ToolDO2 off" onClick={() => void actions.send({ action: 'tooldo', index: 2, status: 0 })} />
              </div>
            </div>
            <p className="admin-card-note">
              {doBits === null
                ? 'Sin estado vivo de salidas (acerca el robot o revisa la conexión).'
                : `DO en vivo: ${[1, 2, 3, 4, 5, 6, 7, 8]
                    .map((i) => `DO${i} ${((doBits >> (i - 1)) & 1) === 1 ? 'on' : 'off'}`)
                    .join(' · ')}`}
            </p>
            <div className="admin-tile-actions">
              <Press icon={Eye} label="Leer DI1–DI4" onClick={() => void actions.readInputs().catch(() => undefined)} />
              <Press icon={Eye} label="Leer ToolDI1" onClick={() => void actions.readToolInput(1)} />
              <Press icon={Eye} label="Leer ToolDI2" onClick={() => void actions.readToolInput(2)} />
            </div>
          </Tile>

          <Tile icon={Square} title="Pruebas" hint="Un trazo corto desde donde está la punta.">
            <Press icon={Square} label="Cuadrado 30 mm" disabled={busy} onClick={() => void actions.send({ action: 'square' })} />
            <Press icon={Spline} label="Arco 40 mm" disabled={busy} onClick={() => void actions.send({ action: 'arc' })} />
          </Tile>
        </div>
      </div>
    </div>
  )
}

function Tile({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: LucideIcon
  title: string
  hint: string
  children: ReactNode
}) {
  return (
    <section className="admin-card admin-tile">
      <header className="admin-tile-head">
        <span className="admin-tile-icon" aria-hidden="true">
          <Icon size={18} />
        </span>
        <div>
          <h3>{title}</h3>
          <p>{hint}</p>
        </div>
      </header>
      <div className="admin-tile-actions">{children}</div>
    </section>
  )
}

function Press({
  icon: Icon,
  label,
  disabled,
  onClick,
}: {
  icon: LucideIcon
  label: string
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button type="button" className="admin-press" disabled={disabled} onClick={onClick}>
      <Icon size={16} aria-hidden="true" />
      {label}
    </button>
  )
}
