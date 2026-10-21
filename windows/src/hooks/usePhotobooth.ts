import { useCallback, useEffect, useReducer } from 'react'
import type { RefObject } from 'react'
import type Webcam from 'react-webcam'
import { generateSketch } from '../lib/sketch'

/**
 * Wizard de la Cabina de Retratos.
 *
 *   attract → camera → countdown → capture → reveal → confirm
 *        → drawing → thanks → attract
 *
 * "TOMAR OTRA" vuelve a `camera`. Si una sección que espera al usuario
 * no cambia en 3 minutos, todo regresa a `attract`.
 */

export type PhotoboothStatus =
  | 'attract'
  | 'camera'
  | 'countdown'
  | 'capture'
  | 'reveal'
  | 'confirm'
  | 'drawing'
  | 'thanks'

export interface ToastData {
  id: number
  kind: 'success' | 'info'
  message: string
}

interface PhotoboothState {
  status: PhotoboothStatus
  countdown: number
  photo: string | null
  sketch: string | null
  /** Progreso 0..1 del reveal (iris + transformación a sketch). */
  progress: number
  toast: ToastData | null
  celebrationId: number
}

type Action =
  | { type: 'BEGIN' }
  | { type: 'START' }
  | { type: 'TICK' }
  | { type: 'CAPTURED'; photo: string }
  | { type: 'REVEAL' }
  | { type: 'PROGRESS'; value: number }
  | { type: 'REVEALED'; sketch: string }
  | { type: 'DRAW' }
  | { type: 'THANKS' }
  | { type: 'RETAKE' }
  | { type: 'TIMEOUT' }
  | { type: 'ATTRACT'; toast?: ToastData }
  | { type: 'DISMISS_TOAST'; id: number }

export const COUNTDOWN_FROM = 3
export const FLASH_MS = 550
/** Iris de entrada de la foto, antes de que empiece el grafito. */
export const IRIS_MS = 900
/** Transformación foto → sketch. */
export const SKETCH_MS = 3200
export const REVEAL_MS = IRIS_MS + SKETCH_MS
/** Fracción del reveal que corresponde al iris. */
export const IRIS_SHARE = IRIS_MS / REVEAL_MS
/** El robot "dibuja" este tiempo antes del cierre. */
export const DRAWING_MS = 3000
/** El agradecimiento vuelve solo a la bienvenida. */
export const THANKS_MS = 8000
/** Misma sección sin avanzar: reinicio completo. */
export const SECTION_TIMEOUT_MS = 3 * 60 * 1000
export const TOAST_MS = 3200

const CAMERA_FLOW: PhotoboothStatus[] = ['camera', 'countdown', 'capture', 'reveal', 'confirm']

const initialState: PhotoboothState = {
  status: 'attract',
  countdown: COUNTDOWN_FROM,
  photo: null,
  sketch: null,
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
    case 'TICK':
      return { ...state, countdown: state.countdown - 1 }
    case 'CAPTURED':
      return { ...state, status: 'capture', photo: action.photo, sketch: null, progress: 0 }
    case 'REVEAL':
      return { ...state, status: 'reveal', progress: 0 }
    case 'PROGRESS':
      return { ...state, progress: action.value }
    case 'REVEALED':
      return { ...state, status: 'confirm', sketch: action.sketch, progress: 1 }
    case 'DRAW':
      return { ...state, status: 'drawing' }
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

  /* Cuenta regresiva: al llegar a 0 se congela el frame. */
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

  /* Flash breve y arranca el reveal. */
  useEffect(() => {
    if (state.status !== 'capture') return
    const timer = setTimeout(() => dispatch({ type: 'REVEAL' }), FLASH_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  /* Reveal: iris + sketch en paralelo con el progreso visual. */
  useEffect(() => {
    if (state.status !== 'reveal' || !state.photo) return

    let cancelled = false
    let sketchResult: string | null = null
    let sketchReady = false
    let progressDone = false

    const maybeFinish = () => {
      if (!cancelled && sketchReady && progressDone && sketchResult) {
        dispatch({ type: 'REVEALED', sketch: sketchResult })
      }
    }

    // TODO(BACKEND): sustituir la simulación local por POST /api/sketch.
    generateSketch(state.photo)
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
    let raf = 0
    const step = () => {
      if (cancelled) return
      const value = Math.min(1, (performance.now() - startedAt) / REVEAL_MS)
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
  }, [state.status, state.photo])

  /* El robot dibuja 3 s y pasa al cierre. */
  useEffect(() => {
    if (state.status !== 'drawing') return
    const timer = setTimeout(() => dispatch({ type: 'THANKS' }), DRAWING_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  /* El agradecimiento regresa solo a la bienvenida. */
  useEffect(() => {
    if (state.status !== 'thanks') return
    const timer = setTimeout(() => dispatch({ type: 'TIMEOUT' }), THANKS_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  /**
   * Misma sección 3 minutos → bienvenida.
   * `drawing` y `thanks` tienen su propio delay corto.
   */
  useEffect(() => {
    if (state.status === 'drawing' || state.status === 'thanks') return
    const timer = setTimeout(() => dispatch({ type: 'TIMEOUT' }), SECTION_TIMEOUT_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  useEffect(() => {
    if (!state.toast) return
    const id = state.toast.id
    const timer = setTimeout(() => dispatch({ type: 'DISMISS_TOAST', id }), TOAST_MS)
    return () => clearTimeout(timer)
  }, [state.toast])

  const begin = useCallback(() => dispatch({ type: 'BEGIN' }), [])
  const start = useCallback(() => dispatch({ type: 'START' }), [])

  const accept = useCallback(() => {
    // TODO(BACKEND/ROBOT): POST /api/jobs con el sketch aprobado para que el Dobot lo trace.
    dispatch({ type: 'DRAW' })
  }, [])

  const retake = useCallback(() => dispatch({ type: 'RETAKE' }), [])

  const dismissToast = useCallback(() => {
    dispatch({ type: 'DISMISS_TOAST', id: state.toast?.id ?? -1 })
  }, [state.toast])

  return {
    ...state,
    inCameraFlow: CAMERA_FLOW.includes(state.status),
    begin,
    start,
    accept,
    retake,
    dismissToast,
  }
}
