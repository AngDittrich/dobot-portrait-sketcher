import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type Webcam from 'react-webcam'
import { getJob, getLastSketchId, postJob } from '../lib/api'
import { generateSketch } from '../lib/sketch'

/**
 * Wizard de la cabina, conectado al backend de main.
 *
 *   attract → camera → countdown → capture → reveal → confirm
 *        → drawing → thanks → attract
 *
 * El boceto sale de POST /api/sketch (con respaldo local). Al pulsar ¡SÍ!
 * se crea el trabajo del robot y la pantalla de dibujo sigue su progreso.
 * Si el backend no responde, el dibujo dura 3 s y sigue el cierre.
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

/** Trabajo de dibujo del robot, tal como lo reporta el backend. */
export interface RobotJob {
  jobId: string
  status: 'queued' | 'drawing' | 'done' | 'error'
  progress: number
  etaSeconds: number
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
  | { type: 'TOAST'; toast: ToastData }
  | { type: 'DISMISS_TOAST'; id: number }

export const COUNTDOWN_FROM = 3
export const FLASH_MS = 550
export const IRIS_MS = 900
export const SKETCH_MS = 3200
export const REVEAL_MS = IRIS_MS + SKETCH_MS
export const IRIS_SHARE = IRIS_MS / REVEAL_MS
/** Si el backend no acepta el trabajo, el dibujo en pantalla dura esto. */
export const DRAWING_MS = 3000
export const THANKS_MS = 8000
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
    const timer = setTimeout(() => dispatch({ type: 'REVEAL' }), FLASH_MS)
    return () => clearTimeout(timer)
  }, [state.status])

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

    // generateSketch llama a POST /api/sketch y, si el backend no está, dibuja en local.
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

  /**
   * Pantalla de dibujo: si hay un trabajo del robot, espera a que termine.
   * Si no hay backend, cierra a los 3 s.
   */
  useEffect(() => {
    if (state.status !== 'drawing') return
    const waiting = robotJob && (robotJob.status === 'queued' || robotJob.status === 'drawing')
    if (waiting) return

    const delay = robotJob?.status === 'done' ? 600 : robotJob ? 1600 : DRAWING_MS
    const timer = setTimeout(() => dispatch({ type: 'THANKS' }), delay)
    return () => clearTimeout(timer)
  }, [state.status, robotJob])

  useEffect(() => {
    if (state.status !== 'thanks') return
    const timer = setTimeout(() => dispatch({ type: 'TIMEOUT' }), THANKS_MS)
    return () => clearTimeout(timer)
  }, [state.status])

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

  /** Manda el boceto aprobado al backend y sigue el progreso del dibujo. */
  const startRobotJob = useCallback(async () => {
    try {
      const job = await postJob(getLastSketchId())
      setRobotJob({
        jobId: job.job_id,
        status: 'drawing',
        progress: 0,
        etaSeconds: job.est_seconds,
      })

      stopRobotPolling()
      robotTimer.current = window.setInterval(() => {
        void (async () => {
          try {
            const status = await getJob(job.job_id)
            setRobotJob((previous) =>
              previous
                ? {
                    ...previous,
                    status: status.status,
                    progress: status.progress,
                    etaSeconds: status.eta_seconds,
                  }
                : previous,
            )
            if (status.status === 'done' || status.status === 'error') {
              stopRobotPolling()
              if (status.status === 'error') {
                dispatch({
                  type: 'TOAST',
                  toast: makeToast('info', 'El robot no pudo terminar el dibujo.'),
                })
              }
            }
          } catch (error) {
            console.warn('Se perdió el seguimiento del trabajo.', error)
            stopRobotPolling()
            setRobotJob((previous) => (previous ? { ...previous, status: 'error' } : previous))
          }
        })()
      }, 1000)
    } catch (error) {
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

  const accept = useCallback(() => {
    dispatch({ type: 'DRAW' })
    void startRobotJob()
  }, [startRobotJob])

  const retake = useCallback(() => {
    stopRobotPolling()
    setRobotJob(null)
    dispatch({ type: 'RETAKE' })
  }, [stopRobotPolling])

  const dismissToast = useCallback(() => {
    dispatch({ type: 'DISMISS_TOAST', id: state.toast?.id ?? -1 })
  }, [state.toast])

  return {
    ...state,
    inCameraFlow: CAMERA_FLOW.includes(state.status),
    robotJob,
    begin,
    start,
    accept,
    retake,
    dismissToast,
  }
}
