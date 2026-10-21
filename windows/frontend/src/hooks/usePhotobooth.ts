import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import type { RefObject } from 'react'
import type Webcam from 'react-webcam'
import { getJob, getLastSketchId, postJob } from '../lib/api'
import { generateSketch } from '../lib/sketch'

/**
 * Máquina de estados de la Cabina de Retratos.
 *
 *   idle → countdown → capture → processing → review → (idle)
 *
 * Toda la orquestación de timers (cuenta regresiva, flash, progreso del
 * "dibujo") vive aquí para que los componentes sean puramente visuales.
 */

export type PhotoboothStatus = 'idle' | 'countdown' | 'capture' | 'processing' | 'review'

export interface ToastData {
  id: number
  kind: 'success' | 'info'
  message: string
}

/** Trabajo de dibujo del robot (simulado por ahora). */
export interface RobotJob {
  jobId: string
  status: 'queued' | 'drawing' | 'done' | 'error'
  progress: number
  etaSeconds: number
}

interface PhotoboothState {
  status: PhotoboothStatus
  /** Valor visible de la cuenta regresiva (3..1). */
  countdown: number
  /** Frame congelado (dataURL) tal cual salió de la webcam. */
  photo: string | null
  /** Retrato final en estilo sketch (dataURL). */
  sketch: string | null
  /** Progreso 0..1 de la "transformación" a sketch. */
  progress: number
  toast: ToastData | null
  /** Se incrementa para disparar una ráfaga de confetti. */
  celebrationId: number
}

type Action =
  | { type: 'START' }
  | { type: 'TICK' }
  | { type: 'CAPTURED'; photo: string }
  | { type: 'PROCESSING' }
  | { type: 'PROGRESS'; value: number }
  | { type: 'PROCESSED'; sketch: string }
  | { type: 'RESET'; toast?: ToastData; celebrate?: boolean }
  | { type: 'TOAST'; toast: ToastData }
  | { type: 'DISMISS_TOAST'; id: number }

export const COUNTDOWN_FROM = 3
/** Duración del flash de cámara antes de pasar a processing. */
export const FLASH_MS = 550
/** Duración total (mínima) de la animación de "dibujo". */
export const PROCESSING_MS = 2800
/** Tiempo visible de un toast. */
export const TOAST_MS = 3200

const initialState: PhotoboothState = {
  status: 'idle',
  countdown: COUNTDOWN_FROM,
  photo: null,
  sketch: null,
  progress: 0,
  toast: null,
  celebrationId: 0,
}

function reducer(state: PhotoboothState, action: Action): PhotoboothState {
  switch (action.type) {
    case 'START':
      return {
        ...initialState,
        status: 'countdown',
        celebrationId: state.celebrationId,
      }
    case 'TICK':
      return { ...state, countdown: state.countdown - 1 }
    case 'CAPTURED':
      return { ...state, status: 'capture', photo: action.photo }
    case 'PROCESSING':
      return { ...state, status: 'processing', progress: 0 }
    case 'PROGRESS':
      return { ...state, progress: action.value }
    case 'PROCESSED':
      return { ...state, status: 'review', sketch: action.sketch, progress: 1 }
    case 'RESET':
      return {
        ...initialState,
        toast: action.toast ?? null,
        celebrationId: action.celebrate ? state.celebrationId + 1 : state.celebrationId,
      }
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
  /** Trabajo de dibujo en curso (null si no hay ninguno). */
  const [robotJob, setRobotJob] = useState<RobotJob | null>(null)
  const robotTimer = useRef<number | null>(null)

  /* --- countdown: ticks de 1s; al llegar a 0 se congela el frame --- */
  useEffect(() => {
    if (state.status !== 'countdown') return

    if (state.countdown <= 0) {
      const photo = webcamRef.current?.getScreenshot() ?? null
      if (photo) {
        dispatch({ type: 'CAPTURED', photo })
      } else {
        dispatch({
          type: 'RESET',
          toast: makeToast('info', 'No pudimos leer la cámara. Inténtalo de nuevo.'),
        })
      }
      return
    }

    const timer = setTimeout(() => dispatch({ type: 'TICK' }), 1000)
    return () => clearTimeout(timer)
  }, [state.status, state.countdown, webcamRef])

  /* --- capture: el flash permanece un instante y arranca el "dibujo" --- */
  useEffect(() => {
    if (state.status !== 'capture') return
    const timer = setTimeout(() => dispatch({ type: 'PROCESSING' }), FLASH_MS)
    return () => clearTimeout(timer)
  }, [state.status])

  /* --- processing: progreso animado + generación del sketch en paralelo --- */
  useEffect(() => {
    if (state.status !== 'processing' || !state.photo) return

    let cancelled = false
    let sketchResult: string | null = null
    let sketchReady = false
    let progressDone = false

    const maybeFinish = () => {
      if (!cancelled && sketchReady && progressDone && sketchResult) {
        dispatch({ type: 'PROCESSED', sketch: sketchResult })
      }
    }

    // El boceto real lo calcula el backend (POST /api/sketch); si no está
    // levantado, `generateSketch` cae al sketch local del navegador.
    generateSketch(state.photo)
      .then((sketch) => {
        sketchResult = sketch
        sketchReady = true
        maybeFinish()
      })
      .catch(() => {
        if (!cancelled) {
          dispatch({
            type: 'RESET',
            toast: makeToast('info', 'Algo salió mal al dibujar. Probemos otra vez.'),
          })
        }
      })

    const startedAt = performance.now()
    let raf = 0
    const step = () => {
      if (cancelled) return
      const value = Math.min(1, (performance.now() - startedAt) / PROCESSING_MS)
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

  /* --- toast: auto-dismiss --- */
  useEffect(() => {
    if (!state.toast) return
    const id = state.toast.id
    const timer = setTimeout(() => dispatch({ type: 'DISMISS_TOAST', id }), TOAST_MS)
    return () => clearTimeout(timer)
  }, [state.toast])

  /* --- robot: envío del boceto y seguimiento del trabajo de dibujo --- */

  const stopRobotPolling = useCallback(() => {
    if (robotTimer.current !== null) {
      window.clearInterval(robotTimer.current)
      robotTimer.current = null
    }
  }, [])

  useEffect(() => stopRobotPolling, [stopRobotPolling])

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
      dispatch({ type: 'TOAST', toast: makeToast('info', 'El robot está dibujando tu retrato.') })

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
            if (status.status === 'done') {
              stopRobotPolling()
              dispatch({
                type: 'TOAST',
                toast: makeToast('success', '¡Listo! Tu retrato ya está en el papel.'),
              })
            } else if (status.status === 'error') {
              stopRobotPolling()
              dispatch({
                type: 'TOAST',
                toast: makeToast('info', 'El robot no pudo terminar el dibujo.'),
              })
            }
          } catch (error) {
            console.warn('Se perdió el seguimiento del trabajo.', error)
            stopRobotPolling()
          }
        })()
      }, 1000)
    } catch (error) {
      console.warn('No se pudo enviar el retrato al robot.', error)
      dispatch({
        type: 'TOAST',
        toast: makeToast('info', 'No se pudo enviar el retrato al robot.'),
      })
    }
  }, [stopRobotPolling])

  /** idle → countdown (CTA "¡Tomar Foto!"). */
  const start = useCallback(() => dispatch({ type: 'START' }), [])

  /** review → idle conservando nada; celebración con confetti + envío al robot. */
  const accept = useCallback(() => {
    dispatch({
      type: 'RESET',
      celebrate: true,
      toast: makeToast('success', '¡Retrato aprobado! Enviándolo al robot…'),
    })
    void startRobotJob()
  }, [startRobotJob])

  /** review → idle descartando la foto. */
  const retake = useCallback(() => {
    dispatch({
      type: 'RESET',
      toast: makeToast('info', 'Sin problema — ¡vamos por una mejor toma!'),
    })
  }, [])

  const dismissToast = useCallback(() => {
    dispatch({ type: 'DISMISS_TOAST', id: state.toast?.id ?? -1 })
  }, [state.toast])

  return {
    ...state,
    isBusy: state.status !== 'idle' && state.status !== 'review',
    robotJob,
    start,
    accept,
    retake,
    dismissToast,
  }
}
