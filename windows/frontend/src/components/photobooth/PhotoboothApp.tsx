import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type Webcam from 'react-webcam'
import { useFraming } from '../../hooks/useFraming'
import { usePhotobooth } from '../../hooks/usePhotobooth'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'
import { BoothControls } from './BoothControls'
import { CameraStage } from './CameraStage'
import { ConfettiCanvas } from './ConfettiCanvas'
import { DrawingScreen } from './DrawingScreen'
import { ThanksScreen } from './ThanksScreen'
import { Toast } from './Toast'
import { WelcomeScreen } from './WelcomeScreen'
import {
  actualCaptureSize,
  decideStepUp,
} from '../../lib/cameraResolution'
import { calibrateExposure } from '../../lib/exposure'

const BASE_CONSTRAINTS: MediaTrackConstraints = {
  width: { ideal: 2560 },
  height: { ideal: 1440 },
  facingMode: 'user',
}

const HEADINGS: Partial<Record<PhotoboothStatus, string>> = {
  camera: 'Encuadre tu retrato',
  countdown: 'Mantén la pose…',
  capture: '¡Perfecta!',
  reveal: 'De foto a lápiz',
  confirm: '¿Listo para ser dibujado?',
}

const STATUS_MESSAGES: Record<PhotoboothStatus, string> = {
  attract: 'Bienvenida. Pulsa COMENZAR para tomar tu foto.',
  camera: 'Cámara lista. Pulsa Tomar Foto.',
  countdown: 'Cuenta regresiva en curso.',
  capture: 'Foto capturada.',
  reveal: 'Convirtiendo tu foto en un dibujo.',
  confirm: 'Retrato listo. Elige TOMAR OTRA o SÍ.',
  drawing: 'El robot está dibujando tu imagen ahora.',
  thanks: 'Listo. Toma tu dibujo. SYSCOM agradece tu visita.',
}

const headingAnimation = {
  initial: { opacity: 0, y: 10, filter: 'blur(4px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  exit: { opacity: 0, y: -8, filter: 'blur(4px)' },
  transition: { duration: 0.28, ease: [0.4, 0, 0.2, 1] },
} as const

/**
 * Wizard de una sola pantalla sobre el backend de main:
 * el boceto y el trabajo del robot siguen saliendo de /api.
 */
export function PhotoboothApp() {
  const webcamRef = useRef<Webcam>(null)
  const booth = usePhotobooth(webcamRef)
  const [cameraError, setCameraError] = useState(false)
  const watching = !cameraError && (booth.status === 'camera' || booth.status === 'countdown')
  const pose = useFraming(webcamRef, watching)
  const autoShot = useRef(false)

  // Silueta verde → la cuenta de 3 empieza sola. Si se sale, se cancela.
  const { status, start, release } = booth
  useEffect(() => {
    if (status === 'camera' && pose === 'ready') {
      autoShot.current = true
      start()
    } else if (status === 'countdown' && pose === 'off' && autoShot.current) {
      autoShot.current = false
      release()
    }
  }, [status, pose, start, release])
  const [webcamKey, setWebcamKey] = useState(0)
  const [videoConstraints, setVideoConstraints] =
    useState<MediaTrackConstraints>(BASE_CONSTRAINTS)
  /** El step-up de resolución se intenta una sola vez por montaje. */
  const steppedUp = useRef(false)
  /** La calibración de exposición se intenta una sola vez por montaje. */
  const exposureTuned = useRef(false)

  const handleCameraReady = useCallback(() => {
    setCameraError(false)
    const video = webcamRef.current?.video ?? null
    const track = (video?.srcObject as MediaStream | null)
      ?.getVideoTracks?.()
      ?.[0] ?? null
    if (!video || !track) return
    if (!steppedUp.current) {
      const actual = actualCaptureSize(video)
      const caps = (
        track.getCapabilities as (() => { width?: { max?: number } }) | undefined
      )?.call(track)
      const next = decideStepUp(actual, caps)
      if (next !== null) {
        steppedUp.current = true
        setVideoConstraints(next)
        setWebcamKey((key) => key + 1)
        // El remonte dispara onCameraReady de nuevo: ahí se calibra.
        return
      }
    }
    if (exposureTuned.current) return
    exposureTuned.current = true
    // Deja que el auto-exposure se asiente antes de muestrear la luz.
    window.setTimeout(() => {
      void calibrateExposure(video, track)
    }, 600)
  }, [webcamRef])
  const handleCameraError = useCallback(() => setCameraError(true), [])
  const retryCamera = useCallback(() => {
    setCameraError(false)
    setWebcamKey((key) => key + 1)
  }, [])

  const heading = HEADINGS[booth.status]

  return (
    <div className="booth-shell">
      <div className="booth-ambient" aria-hidden="true">
        <span className="booth-aurora booth-aurora--a" />
        <span className="booth-aurora booth-aurora--b" />
        <span className="booth-noise" />
      </div>

      <header className="booth-brandbar">
        <div className="booth-brandbar-inner">
          <img
            src="/brand/syscomLargeLogo.webp"
            alt="SYSCOM"
            className="booth-logo"
            draggable={false}
          />
          <span className="booth-brand-divider" aria-hidden="true" />
          <span className="booth-product">Robot Dobot</span>
          <span className="booth-demo-note">Conectado al backend del robot</span>
        </div>
      </header>

      <main className="booth-main">
        <AnimatePresence mode="wait">
          {booth.status === 'attract' && <WelcomeScreen key="attract" onBegin={booth.begin} />}

          {booth.inCameraFlow && (
            <motion.div
              key="camera-flow"
              className="booth-flow"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            >
              <div className="booth-heading">
                <AnimatePresence mode="wait">
                  {heading && (
                    <motion.h1 key={booth.status} className="booth-title" {...headingAnimation}>
                      {heading}
                    </motion.h1>
                  )}
                </AnimatePresence>
              </div>

              <div className="booth-stage-wrap">
                <CameraStage
                  webcamRef={webcamRef}
                  webcamKey={webcamKey}
                  status={booth.status}
                  countdown={booth.countdown}
                  photo={booth.photo}
                  sketch={booth.sketch}
                  progress={booth.progress}
                  cameraError={cameraError}
                  videoConstraints={videoConstraints}
                  pose={pose ?? 'off'}
                  onCameraReady={handleCameraReady}
                  onCameraError={handleCameraError}
                  onRetryCamera={retryCamera}
                >
                  <BoothControls
                    status={booth.status}
                    countdown={booth.countdown}
                    progress={booth.progress}
                    cameraError={cameraError}
                    onStart={() => {
                      autoShot.current = false
                      booth.start()
                    }}
                  />
                </CameraStage>
              </div>
            </motion.div>
          )}

          {booth.status === 'drawing' && <DrawingScreen key="drawing" job={booth.robotJob} />}
          {booth.status === 'thanks' && <ThanksScreen key="thanks" />}
        </AnimatePresence>
      </main>

      <AnimatePresence>
        {booth.status === 'confirm' && (
          <motion.div
            key="choices"
            className="booth-choices"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ type: 'spring', stiffness: 280, damping: 24 }}
          >
            <button type="button" className="btn booth-choice booth-choice--no" onClick={booth.retake}>
              TOMAR OTRA
            </button>
            <button type="button" className="btn booth-choice booth-choice--yes" onClick={booth.accept}>
              ¡SÍ!
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <Toast toast={booth.toast} onDismiss={booth.dismissToast} />
      <ConfettiCanvas trigger={booth.celebrationId} />

      <p className="sr-only" aria-live="polite">
        {booth.status === 'camera'
          ? pose === 'ready'
            ? 'Encuadre listo. La foto se toma en 3 segundos.'
            : 'Colócate dentro de la silueta.'
          : STATUS_MESSAGES[booth.status]}
        {booth.status === 'countdown' && booth.countdown > 0 ? ` ${booth.countdown}` : ''}
      </p>
    </div>
  )
}
