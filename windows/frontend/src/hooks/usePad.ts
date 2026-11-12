import { useCallback, useEffect, useRef, useState } from 'react'
import { adminCommand } from '../lib/api'

const CROSS = 0
const CIRCLE = 1
const SQUARE = 2
const TRIANGLE = 3
const L1 = 4
const R1 = 5
const L2 = 6
const R2 = 7
const OPTIONS = 9
const L3 = 10
// Frente al robot, +Y es la derecha de quien opera y -X es alejarse.
const DPAD = [
  { index: 12, x: -1, y: 0 },
  { index: 13, x: 1, y: 0 },
  { index: 14, x: 0, y: -1 },
  { index: 15, x: 0, y: 1 },
] as const

export type PadTune = {
  deadzone: number
  invertX: boolean
  invertY: boolean
  invertJ4: boolean
}

export const DEFAULT_PAD_TUNE: PadTune = {
  deadzone: 0.15,
  invertX: false,
  invertY: false,
  invertJ4: false,
}

export type PadState = {
  /** Nombre corto del mando, si el navegador lo mapea como estándar. */
  name: string | null
  armed: boolean
  /** Hay un mando, pero sin el mapa estándar: no se mueve el brazo. */
  unsupported: boolean
  arm: (next: boolean) => void
}

type PadOptions = {
  token: string
  speed: number
  setSpeed: (value: number | ((current: number) => number)) => void
  busy: boolean
  drag: boolean
  tune: PadTune
  onClearLogs: () => void
  onNotice: (message: string) => void
}

function applyDead(value: number, zone: number): number {
  if (!Number.isFinite(value) || Math.abs(value) < zone) return 0
  return Math.max(-1, Math.min(1, value))
}

/** Lo que el brazo recibiría: zona muerta e inversiones ya aplicadas.
 *
 * Quien opera está frente al robot. Ahí +Y queda a su derecha, así que la
 * palanca horizontal va a Y. Arriba en la palanca se aleja: eso es -X.
 */
export function driveFrom(pad: Gamepad, tune: PadTune): { x: number; y: number; z: number; j4: number } {
  const zone = Math.min(0.6, Math.max(0.02, tune.deadzone))
  let right = applyDead(pad.axes[0] ?? 0, zone)
  let forward = applyDead(-(pad.axes[1] ?? 0), zone)
  let j4 = applyDead(pad.axes[2] ?? 0, zone)
  if (tune.invertX) right = -right
  if (tune.invertY) forward = -forward
  if (tune.invertJ4) j4 = -j4
  const z = applyDead(trigger(pad, R2, 5) - trigger(pad, L2, 4), zone)
  return { x: -forward, y: right, z, j4 }
}

/** Gatillo de 0 a 1. Si el botón no trae analógico, se usa el eje (reposo en -1). */
function trigger(pad: Gamepad, button: number, axis: number): number {
  const fromButton = pad.buttons[button]?.value ?? 0
  if (fromButton > 0.05) return Math.min(1, fromButton)
  const raw = pad.axes[axis]
  if (typeof raw !== 'number') return 0
  const scaled = (raw + 1) / 2
  return scaled > 0.05 ? Math.min(1, scaled) : 0
}

function labelOf(id: string): string {
  const cut = id.split('(')[0]?.trim()
  return cut || 'Control'
}

export type PadSample = {
  name: string | null
  unsupported: boolean
  lx: number
  ly: number
  rx: number
  ry: number
  l2: number
  r2: number
  sent: { x: number; y: number; z: number; j4: number }
  down: boolean[]
}

const QUIET: PadSample = {
  name: null,
  unsupported: false,
  lx: 0,
  ly: 0,
  rx: 0,
  ry: 0,
  l2: 0,
  r2: 0,
  sent: { x: 0, y: 0, z: 0, j4: 0 },
  down: [],
}

/** Lectura en vivo para el dibujo del mando. No manda nada al robot. */
export function samplePad(tune: PadTune): PadSample {
  const list = navigator.getGamepads ? Array.from(navigator.getGamepads()) : []
  const connected = list.filter((pad): pad is Gamepad => pad !== null && pad.connected)
  const pad = connected.find((item) => item.mapping === 'standard')
  if (!pad) return { ...QUIET, unsupported: connected.length > 0 }
  return {
    name: labelOf(pad.id),
    unsupported: false,
    lx: pad.axes[0] ?? 0,
    ly: pad.axes[1] ?? 0,
    rx: pad.axes[2] ?? 0,
    ry: pad.axes[3] ?? 0,
    l2: trigger(pad, L2, 4),
    r2: trigger(pad, R2, 5),
    sent: driveFrom(pad, tune),
    down: pad.buttons.map((button) => button.pressed),
  }
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'el control no pudo mover el robot'
}

/**
 * DualShock (o un mando con mapa estándar) por USB. Nace desarmado: Options
 * arma y desarma. Un envío a la vez; al soltar, Stop(). No devuelve J4 a -50.
 */
export function usePad(options: PadOptions): PadState {
  const [name, setName] = useState<string | null>(null)
  const [armed, setArmed] = useState(false)
  const [unsupported, setUnsupported] = useState(false)
  const opts = useRef(options)
  useEffect(() => {
    opts.current = options
  })

  const armedRef = useRef(false)
  const want = useRef(false)
  const moving = useRef(false)
  const pumping = useRef(false)
  const skipStop = useRef(false)
  const prev = useRef<boolean[]>([])
  const sample = useRef({ x: 0, y: 0, z: 0, j4: 0 })
  const tail = useRef(Promise.resolve())
  const reported = useRef<{ name: string | null; unsupported: boolean }>({
    name: null,
    unsupported: false,
  })

  const arm = useCallback((next: boolean) => {
    armedRef.current = next
    setArmed(next)
    if (!next) want.current = false
  }, [])

  useEffect(() => {
    let alive = true

    const enqueue = (job: () => Promise<void>) => {
      tail.current = tail.current.then(job).catch(() => undefined)
    }

    const fail = (error: unknown) => {
      opts.current.onNotice(message(error))
    }

    const pump = () => {
      if (pumping.current) return
      pumping.current = true
      enqueue(async () => {
        try {
          while (want.current && armedRef.current && !opts.current.busy && !opts.current.drag) {
            const sent = sample.current
            await adminCommand(opts.current.token, {
              action: 'pad',
              x: sent.x,
              y: sent.y,
              z: sent.z,
              j4: sent.j4,
              speed: opts.current.speed,
            })
            moving.current = true
          }
        } catch (error) {
          want.current = false
          fail(error)
        } finally {
          const shouldStop = moving.current && !skipStop.current
          moving.current = false
          skipStop.current = false
          pumping.current = false
          if (shouldStop) {
            try {
              await adminCommand(opts.current.token, { action: 'padstop' })
            } catch {
              // Si el paro no entra, el último paso ya se quedó corto.
            }
          }
        }
      })
    }

    const after = (job: () => Promise<unknown>) => {
      want.current = false
      enqueue(async () => {
        if (moving.current) {
          moving.current = false
          try {
            await adminCommand(opts.current.token, { action: 'padstop' })
          } catch {
            // El paro va antes de la acción; si falla, igual se intenta la acción.
          }
        }
        try {
          await job()
        } catch (error) {
          fail(error)
        }
      })
    }

    const edge = (index: number, pressed: boolean[]) => pressed[index] && !prev.current[index]

    const tick = () => {
      if (!alive) return
      const list = navigator.getGamepads ? Array.from(navigator.getGamepads()) : []
      const connected = list.filter((pad): pad is Gamepad => pad !== null && pad.connected)
      const pad = connected.find((item) => item.mapping === 'standard')
      const nextName = pad ? labelOf(pad.id) : null
      const nextUnsupported = !pad && connected.length > 0
      if (
        reported.current.name !== nextName ||
        reported.current.unsupported !== nextUnsupported
      ) {
        reported.current = { name: nextName, unsupported: nextUnsupported }
        setName(nextName)
        setUnsupported(nextUnsupported)
      }

      if (!pad) {
        if (want.current || moving.current) {
          want.current = false
          if (!pumping.current && moving.current) {
            moving.current = false
            enqueue(async () => {
              try {
                await adminCommand(opts.current.token, { action: 'padstop' })
              } catch {
                // El mando ya no está; el paro es por si quedó un paso en camino.
              }
            })
          }
        }
        prev.current = []
        return
      }

      const pressed = pad.buttons.map((button) => button.pressed)
      if (edge(OPTIONS, pressed)) {
        armedRef.current = !armedRef.current
        setArmed(armedRef.current)
        if (!armedRef.current) want.current = false
      }
      if (edge(CIRCLE, pressed)) {
        if (pumping.current || moving.current) skipStop.current = true
        armedRef.current = false
        setArmed(false)
        want.current = false
        void adminCommand(opts.current.token, { action: 'estop' }).catch(fail)
      }
      if (edge(SQUARE, pressed)) opts.current.onClearLogs()

      const armedNow = armedRef.current
      const blocked = opts.current.busy || opts.current.drag
      if (armedNow && edge(L1, pressed)) {
        opts.current.setSpeed((current) => Math.min(100, Math.max(1, current - 10)))
      }
      if (armedNow && edge(R1, pressed)) {
        opts.current.setSpeed((current) => Math.min(100, Math.max(1, current + 10)))
      }
      if (armedNow && !opts.current.busy && edge(TRIANGLE, pressed)) {
        after(() => adminCommand(opts.current.token, { action: 'drag', on: true }))
      }
      if (armedNow && !opts.current.busy && edge(CROSS, pressed)) {
        after(() => adminCommand(opts.current.token, { action: 'drag', on: false }))
      }
      if (armedNow && !opts.current.busy && edge(L3, pressed)) {
        after(() => adminCommand(opts.current.token, { action: 'j4home' }))
      }
      if (armedNow && !blocked && !want.current && !pumping.current) {
        const dpad = DPAD.find((item) => edge(item.index, pressed))
        if (dpad) {
          const stepX = opts.current.tune.invertY ? -dpad.x : dpad.x
          const stepY = opts.current.tune.invertX ? -dpad.y : dpad.y
          enqueue(async () => {
            try {
              await adminCommand(opts.current.token, {
                action: 'pad',
                x: stepX,
                y: stepY,
                z: 0,
                j4: 0,
                speed: opts.current.speed,
                mm: 1,
              })
            } catch (error) {
              fail(error)
            }
          })
        }
      }
      prev.current = pressed

      if (!armedNow || blocked) {
        want.current = false
        return
      }
      const sent = driveFrom(pad, opts.current.tune)
      const { x, y, z, j4 } = sent
      sample.current = sent
      if (x === 0 && y === 0 && z === 0 && j4 === 0) {
        want.current = false
        return
      }
      want.current = true
      pump()
    }

    let frame = 0
    const loop = () => {
      tick()
      if (alive) frame = window.requestAnimationFrame(loop)
    }
    frame = window.requestAnimationFrame(loop)

    const onHide = () => {
      if (document.hidden) want.current = false
    }
    document.addEventListener('visibilitychange', onHide)

    return () => {
      alive = false
      want.current = false
      window.cancelAnimationFrame(frame)
      document.removeEventListener('visibilitychange', onHide)
      if (moving.current && !skipStop.current) {
        moving.current = false
        void adminCommand(opts.current.token, { action: 'padstop' }).catch(() => undefined)
      }
    }
  }, [])

  return { name, armed, unsupported, arm }
}
