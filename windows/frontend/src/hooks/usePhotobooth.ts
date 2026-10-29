import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type Webcam from 'react-webcam'
import { getJob, getLastSketchId, postJob, cancelActiveJob } from '../lib/api'
import { generateSketchDetail, type SketchDetail, type SketchStroke } from '../lib/sketch'
import { EMPTY_TRAITS, selectedTraitIds, toggleTrait } from '../lib/traits'
import type { TraitGroup, TraitSelection } from '../lib/traits'
import { DEFAULT_STYLE, isDrawingStyle } from '../lib/drawingStyles'
import type { DrawingStyleId } from '../lib/drawingStyles'

/**
 * Wizard de la cabina, conectado al backend de main.
 *
 *   attract → camera → countdown → capture → review → style
 *        → reveal → confirm → drawing → thanks → attract
 *                                     ↘ robotError → drawing | attract
 *
 * La foto se muestra antes de gastar un token. La IA corre al salir de
 * style, con los rasgos elegidos. Al pulsar ¡SÍ! se crea el trabajo del robot.
 */

export type PhotoboothStatus =
  | 'attract'
  | 'camera'
  | 'countdown'
  | 'capture'
  | 'review'
  | 'style'
  | 'reveal'
  | 'confirm'
  | 'drawing'
  | 'thanks'
  | 'robotError'

export interface ToastData {
  id: number
  kind: 'success' | 'info'
  message: string
}

/** Trabajo de dibujo del robot, tal como lo reporta el backend. */
export interface RobotJob {
  jobId: string
  status: 'queued' | 'drawing' | 'done' | 'error'
  progress: number
  etaSeconds: number
  error: string | null
}

interface PhotoboothState {
  status: PhotoboothStatus
  countdown: number
  photo: string | null
  traits: TraitSelection
  styleId: DrawingStyleId
  sketch: string | null
  /** Trazos del boceto, para ir pintándolos mientras el robot dibuja. */
  strokes: SketchStroke[]
  /** Progreso 0..1 del reveal (iris + transformación a sketch). */
  progress: number
  toast: ToastData | null
  celebrationId: number
}

type Action =
  | { type: 'BEGIN' }
  | { type: 'START' }
  | { type: 'RELEASE' }
  | { type: 'TICK' }
  | { type: 'CAPTURED'; photo: string }
  | { type: 'REVIEW' }
  | { type: 'LIKE' }
  | { type: 'TOGGLE'; group: TraitGroup; id: string }
  | { type: 'STYLE'; id: DrawingStyleId }
  | { type: 'CONTINUE' }
  | { type: 'PROGRESS'; value: number }
  | { type: 'REVEALED'; sketch: string; strokes: SketchStroke[] }
  | { type: 'DRAW' }
  | { type: 'ROBOT_FAILED' }
  | { type: 'THANKS' }
  | { type: 'RETAKE' }
  | { type: 'TIMEOUT' }
  | { type: 'ATTRACT'; toast?: ToastData }
  | { type: 'TOAST'; toast: ToastData }
  | { type: 'DISMISS_TOAST'; id: number }

export const COUNTDOWN_FROM = 3
export const FLASH_MS = 550
export const IRIS_MS = 900
export const SKETCH_MS = 3200
export const REVEAL_MS = IRIS_MS + SKETCH_MS
export const IRIS_SHARE = IRIS_MS / REVEAL_MS
/**
 * Hasta dónde llega el reveal mientras falta el dibujo. La IA tarda ~12 s y
 * la animación dura 4 s: sin este tope la pantalla se quedaba quieta con el
 * dibujo a medio formar. Nunca se cierra antes de que el dibujo exista.
 */
export const REVEAL_HOLD = 0.94
/** Cierre suave del reveal cuando el dibujo llega tarde. */
export const REVEAL_SETTLE_MS = 260
/** Si el backend no acepta el trabajo, el dibujo en pantalla dura esto. */
export const DRAWING_MS = 3000
export const THANKS_MS = 8000
export const SECTION_TIMEOUT_MS = 3 * 60 * 1000
export const TOAST_MS = 3200

const CAMERA_FLOW: PhotoboothStatus[] = [
  'camera',
  'countdown',
  'capture',
  'review',
  'style',
  'reveal',
  'confirm',
]

/** Pantallas que esperan una decisión. Ahí se ve el anillo. */
const WAITING: PhotoboothStatus[] = ['camera', 'review', 'style', 'confirm']

const initialState: PhotoboothState = {
  status: 'attract',
  countdown: COUNTDOWN_FROM,
  photo: null,
  traits: EMPTY_TRAITS,
  styleId: DEFAULT_STYLE,
  sketch: null,
  strokes: [],
  progress: 0,
  toast: null,
  celebrationId: 0,
}

function cleared(status: PhotoboothStatus, extra?: Partial<PhotoboothState>): PhotoboothState {
  return {
    ...initialState,
    status,
    celebrationId: extra?.celebrationId ?? 0,
    toast: extra?.toast ?? null,
  }
}

function reducer(state: PhotoboothState, action: Action): PhotoboothState {
  switch (action.type) {
    case 'BEGIN':
      return cleared('camera', { celebrationId: state.celebrationId })
    case 'START':
      return { ...state, status: 'countdown', countdown: COUNTDOWN_FROM }
    case 'RELEASE':
      if (state.status !== 'countdown') return state
      return { ...state, status: 'camera', countdown: COUNTDOWN_FROM }
    case 'TICK':
      return { ...state, countdown: state.countdown - 1 }
    case 'CAPTURED':
      return {
        ...state,
        status: 'capture',
        photo: action.photo,
        traits: EMPTY_TRAITS,
        styleId: DEFAULT_STYLE,
        sketch: null,
        strokes: [],
        progress: 0,
      }
    case 'REVIEW':
      return { ...state, status: 'review' }
    case 'LIKE':
      if (state.status !== 'review') return state
      return { ...state, status: 'style' }
    case 'TOGGLE': {
      if (state.status !== 'style') return state
      // toggleTrait retira lo que se encimaría: bombero ya lleva casco.
      return { ...state, traits: toggleTrait(state.traits, action.group, action.id) }
    }
    case 'STYLE':
      if (state.status !== 'style' || !isDrawingStyle(action.id)) return state
      return { ...state, styleId: action.id }
    case 'CONTINUE':
      if (state.status !== 'style') return state
      return { ...state, status: 'reveal', sketch: null, strokes: [], progress: 0 }
    case 'PROGRESS':
      return { ...state, progress: action.value }
    case 'REVEALED':
      return { ...state, status: 'confirm', sketch: action.sketch, strokes: action.strokes, progress: 1 }
    case 'DRAW':
      if (state.status !== 'confirm' && state.status !== 'robotError') return state
      return { ...state, status: 'drawing' }
    case 'ROBOT_FAILED':
      if (state.status !== 'drawing') return state
      return { ...state, status: 'robotError' }
    case 'THANKS':
      return { ...state, status: 'thanks', celebrationId: state.celebrationId + 1 }
    case 'RETAKE':
      return cleared('camera', { celebrationId: state.celebrationId })
    case 'TIMEOUT':
    case 'ATTRACT':
      return cleared('attract', {
        celebrationId: state.celebrationId,
        toast: action.type === 'ATTRACT' ? action.toast : null,
      })
    case 'TOAST':
      return { ...state, toast: action.toast }
    case 'DISMISS_TOAST':
      return state.toast?.id === action.id ? { ...state, toast: null } : state
    default:
      return state
  }
}

function makeToast(kind: ToastData['kind'], message: string): ToastData {
  return { id: Date.now(), kind, message }
}

export function usePhotobooth(webcamRef: RefObject<Webcam | null>) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const [robotJob, setRobotJob] = useState<RobotJob | null>(null)
  const robotTimer = useRef<number | null>(null)

  const stopRobotPolling = useCallback(() => {
    if (robotTimer.current !== null) {
      window.clearInterval(robotTimer.current)
      robotTimer.current = null
    }
  }, [])
  const skipRobotError = useRef(false)

  useEffect(() => stopRobotPolling, [stopRobotPolling])

  useEffect(() => {
    if (state.status !== 'countdown') return

    if (state.countdown <= 0) {
      const photo = webcamRef.current?.getScreenshot() ?? null
      if (photo) {
        dispatch({ type: 'CAPTURED', photo })
      } else {
        dispatch({
          type: 'ATTRACT',
          toast: makeToast('info', 'No pudimos leer la cámara. Inténtalo de nuevo.'),
        })
      }
      return
    }

    const timer = setTimeout(() => dispatch({ type: 'TICK' }), 1000)
    return () => clearTimeout(timer)
  }, [state.status, state.countdown, webcamRef])

  useEffect(() => {
    if (state.status !== 'capture') return
    const timer = setTimeout(() => dispatch({ type: 'REVIEW' }), FLASH_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  useEffect(() => {
    if (state.status !== 'reveal' || !state.photo) return

    let cancelled = false
    let sketchResult: SketchDetail | null = null
    let sketchReady = false
    let progressDone = false

    const maybeFinish = () => {
      if (!cancelled && sketchReady && progressDone && sketchResult) {
        dispatch({ type: 'REVEALED', sketch: sketchResult.image, strokes: sketchResult.strokes })
      }
    }

    // La IA corre aquí, ya con la foto aceptada y los rasgos. Si el backend
    // no está, generateSketchDetail dibuja en local (sin trazos).
    generateSketchDetail(state.photo, selectedTraitIds(state.traits), state.styleId)
      .then((sketch) => {
        sketchResult = sketch
        sketchReady = true
        maybeFinish()
      })
      .catch(() => {
        if (!cancelled) {
          dispatch({
            type: 'ATTRACT',
            toast: makeToast('info', 'Algo salió mal al dibujar. Probemos otra vez.'),
          })
        }
      })

    const startedAt = performance.now()
    let current = 0
    let settleStart: number | null = null
    let raf = 0
    const step = () => {
      if (cancelled) return
      const now = performance.now()
      const elapsed = now - startedAt
      let value: number
      if (elapsed <= REVEAL_MS) {
        // Con el dibujo en mano el reveal dura lo de siempre; sin él se frena
        // antes del final para no cerrar una transformación que no existe.
        value = sketchReady ? elapsed / REVEAL_MS : (elapsed / REVEAL_MS) * REVEAL_HOLD
      } else if (sketchReady) {
        // Llegó tarde: los últimos puntos se completan en REVEAL_SETTLE_MS.
        if (settleStart === null) settleStart = now
        const settle = Math.min(1, (now - settleStart) / REVEAL_SETTLE_MS)
        value = current + (1 - current) * settle
      } else {
        // Sigue avanzando, cada vez más despacio: la pantalla nunca se congela.
        const late = elapsed - REVEAL_MS
        value = REVEAL_HOLD + (1 - REVEAL_HOLD) * 0.4 * (1 - Math.exp(-late / 2400))
      }
      current = value
      dispatch({ type: 'PROGRESS', value })
      if (value < 1) {
        raf = requestAnimationFrame(step)
      } else {
        progressDone = true
        maybeFinish()
      }
    }
    raf = requestAnimationFrame(step)

    return () => {
      cancelled = true
      cancelAnimationFrame(raf)
    }
  }, [state.status, state.photo, state.traits, state.styleId])

  /**
   * Pantalla de dibujo: si hay un trabajo del robot, espera a que termine.
   * Si no hay backend, cierra a los 3 s. Un trabajo con error se queda en
   * robotError: no se le dice a la persona que se lleve un dibujo a medias.
   */
  useEffect(() => {
    if (state.status !== 'drawing') return
    if (robotJob && robotJob.status !== 'done') return

    const delay = robotJob ? 600 : DRAWING_MS
    const timer = setTimeout(() => dispatch({ type: 'THANKS' }), delay)
    return () => clearTimeout(timer)
  }, [state.status, robotJob])

  useEffect(() => {
    if (state.status !== 'thanks') return
    const timer = setTimeout(() => dispatch({ type: 'TIMEOUT' }), THANKS_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  // Reloj de inactividad. La hora de arranque se toma dentro del efecto, que
  // solo programa el tic; el estado se escribe desde el propio tic y no desde
  // el cuerpo del efecto. Al cambiar de sección el plazo se recalcula.
  const [idleBump, setIdleBump] = useState(0)
  const [idleLeftMs, setIdleLeftMs] = useState(SECTION_TIMEOUT_MS)
  const waiting = WAITING.includes(state.status)

  useEffect(() => {
    if (!waiting) return
    const deadline = Date.now() + SECTION_TIMEOUT_MS
    const timer = window.setInterval(() => {
      const left = deadline - Date.now()
      setIdleLeftMs(Math.max(0, left))
      if (left <= 0) dispatch({ type: 'TIMEOUT' })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [waiting, state.status, idleBump])

  useEffect(() => {
    if (!state.toast) return
    const id = state.toast.id
    const timer = setTimeout(() => dispatch({ type: 'DISMISS_TOAST', id }), TOAST_MS)
    return () => clearTimeout(timer)
  }, [state.toast])

  /** Manda el boceto aprobado al backend y sigue el progreso del dibujo. */
  const startRobotJob = useCallback(async () => {
    try {
      const job = await postJob(getLastSketchId())
      console.info(`[robot] ${job.job_id} enviado (boceto ${job.sketch_id})`)
      setRobotJob({
        jobId: job.job_id,
        status: 'drawing',
        progress: 0,
        etaSeconds: job.est_seconds,
        error: null,
      })
      skipRobotError.current = false

      stopRobotPolling()
      robotTimer.current = window.setInterval(() => {
        void (async () => {
          try {
            const status = await getJob(job.job_id)
            if (skipRobotError.current) return
            setRobotJob((previous) =>
              previous
                ? {
                    ...previous,
                    status: status.status,
                    progress: status.progress,
                    etaSeconds: status.eta_seconds,
                    error: status.error,
                  }
                : previous,
            )
            if (status.status === 'done') {
              stopRobotPolling()
              console.info(`[robot] ${job.job_id} terminado`)
            } else if (status.status === 'error') {
              stopRobotPolling()
              if (skipRobotError.current || status.error === 'cancelado') return
              console.error(
                `[robot] ${job.job_id} falló al ${Math.round(status.progress * 100)} %:`,
                status.error,
              )
              dispatch({ type: 'ROBOT_FAILED' })
            }
          } catch (error) {
            console.error(`[robot] se perdió el seguimiento de ${job.job_id}`, error)
            stopRobotPolling()
            setRobotJob((previous) =>
              previous ? { ...previous, status: 'error', error: String(error) } : previous,
            )
            dispatch({ type: 'ROBOT_FAILED' })
          }
        })()
      }, 1000)
    } catch (error) {
      // Sin backend (fetch no llega) la cabina sigue como demo. Si el backend
      // contestó con un error, el trabajo no existe y hay que avisar.
      if (error instanceof Error && error.message.startsWith('Backend ')) {
        console.error('[robot] el backend rechazó el trabajo:', error.message)
        dispatch({ type: 'ROBOT_FAILED' })
        return
      }
      console.warn('No se pudo enviar el retrato al robot.', error)
      dispatch({
        type: 'TOAST',
        toast: makeToast('info', 'El robot no está conectado. Mostramos el cierre de la cabina.'),
      })
    }
  }, [stopRobotPolling])

  const begin = useCallback(() => {
    stopRobotPolling()
    setRobotJob(null)
    dispatch({ type: 'BEGIN' })
  }, [stopRobotPolling])

  const start = useCallback(() => dispatch({ type: 'START' }), [])

  /** Sale de la cuenta si la persona se salió de la silueta. */
  const release = useCallback(() => dispatch({ type: 'RELEASE' }), [])

  const accept = useCallback(() => {
    dispatch({ type: 'DRAW' })
    void startRobotJob()
  }, [startRobotJob])

  /** Desde robotError: vuelve a mandar el mismo boceto. */
  const retryRobot = useCallback(() => {
    stopRobotPolling()
    setRobotJob(null)
    dispatch({ type: 'DRAW' })
    void startRobotJob()
  }, [startRobotJob, stopRobotPolling])

  const home = useCallback(() => {
    stopRobotPolling()
    setRobotJob(null)
    dispatch({ type: 'ATTRACT' })
  }, [stopRobotPolling])

  const cancelDrawing = useCallback(async () => {
    skipRobotError.current = true
    stopRobotPolling()
    try {
      await cancelActiveJob()
    } catch (error) {
      console.error('[robot] no se pudo cancelar el dibujo', error)
    }
    setRobotJob(null)
    dispatch({ type: 'ATTRACT' })
  }, [stopRobotPolling])

  const retake = useCallback(() => {
    stopRobotPolling()
    setRobotJob(null)
    dispatch({ type: 'RETAKE' })
  }, [stopRobotPolling])

  const like = useCallback(() => dispatch({ type: 'LIKE' }), [])

  const toggleTrait = useCallback((group: TraitGroup, id: string) => {
    dispatch({ type: 'TOGGLE', group, id })
  }, [])

  const chooseStyle = useCallback((id: DrawingStyleId) => {
    dispatch({ type: 'STYLE', id })
  }, [])

  const proceed = useCallback(() => dispatch({ type: 'CONTINUE' }), [])

  const resetIdle = useCallback(() => setIdleBump((value) => value + 1), [])

  const dismissToast = useCallback(() => {
    dispatch({ type: 'DISMISS_TOAST', id: state.toast?.id ?? -1 })
  }, [state.toast])

  return {
    ...state,
    inCameraFlow: CAMERA_FLOW.includes(state.status),
    idleLeftMs: waiting ? idleLeftMs : null,
    robotJob,
    begin,
    start,
    release,
    accept,
    retryRobot,
    home,
    cancelDrawing,
    retake,
    like,
    toggleTrait,
    chooseStyle,
    proceed,
    resetIdle,
    dismissToast,
  }
}
