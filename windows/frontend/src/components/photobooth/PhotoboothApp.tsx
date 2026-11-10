import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type Webcam from 'react-webcam'
import { useFraming } from '../../hooks/useFraming'
import { usePhotobooth } from '../../hooks/usePhotobooth'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'
import { AdminDesk } from './AdminDesk'
import { BoothControls } from './BoothControls'
import { CameraStage } from './CameraStage'
import { CircuitBackdrop } from './CircuitBackdrop'
import { IdleRing } from './IdleRing'
import { ConfettiCanvas } from './ConfettiCanvas'
import { DrawingScreen } from './DrawingScreen'
import { RobotErrorScreen } from './RobotErrorScreen'
import { StylePicker } from './StylePicker'
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
  review: '¿Así te quedó?',
  style: 'Elige tu dibujo',
  reveal: 'De foto a lápiz',
  confirm: '¿Listo para ser dibujado?',
}

const STATUS_MESSAGES: Record<PhotoboothStatus, string> = {
  attract: 'Bienvenida. Pulsa COMENZAR para tomar tu foto.',
  camera: 'Cámara lista. Pulsa Tomar Foto.',
  countdown: 'Cuenta regresiva en curso.',
  capture: 'Foto capturada.',
  review: 'Foto lista. Elige TOMAR OTRA o ME GUSTA.',
  style: 'Elige un estilo, y si quieres una profesión o un accesorio.',
  reveal: 'Convirtiendo tu foto en un dibujo.',
  confirm: 'Retrato listo. Elige TOMAR OTRA o SÍ.',
  drawing: 'El robot está dibujando tu imagen ahora.',
  thanks: 'Listo. Toma tu dibujo. SYSCOM agradece tu visita.',
  robotError: 'El robot se detuvo. Elige REINTENTAR o INICIO.',
}

const headingAnimation = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.22, ease: [0.4, 0, 0.2, 1] },
} as const

/** Una línea de apoyo por paso: qué se espera del visitante, sin numerar pasos. */
const RAIL_HINTS: Partial<Record<PhotoboothStatus, string>> = {
  camera: 'Ponte dentro de la silueta y la foto se toma sola.',
  countdown: 'Quieta, ya casi está.',
  capture: 'Guardando la foto.',
  review: 'Si no te gusta, puedes repetirla.',
  style: 'Un estilo, una profesión y un accesorio. Todo es opcional menos el estilo.',
  reveal: 'Esto tarda unos segundos.',
  confirm: 'Tu retrato está listo. El robot lo pasa al papel.',
}

/**
 * Wizard de una sola pantalla sobre el backend de main:
 * el boceto y el trabajo del robot siguen saliendo de /api.
 */
export function PhotoboothApp({ onOpenAdmin }: { onOpenAdmin: () => void }) {
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
      {booth.status === 'attract' && <CircuitBackdrop />}
      <header className="booth-brandbar">
        <div className="booth-brandbar-inner">
          <div className="booth-brand-lockup">
            <img
              src="/brand/syscomLargeLogo.webp"
              alt="SYSCOM"
              className="booth-logo"
              draggable={false}
            />
            <span className="booth-brand-divider" aria-hidden="true" />
            <span className="booth-product">Robot Dobot</span>
          </div>
          <span className="booth-demo-note">Conectado al backend del robot</span>
          <AdminDesk onOpenAdmin={onOpenAdmin} />
        </div>
      </header>

      <main className="booth-main">
        <AnimatePresence mode="wait">
          {booth.status === 'attract' && <WelcomeScreen key="attract" onBegin={booth.begin} />}

          {booth.inCameraFlow && (
            <motion.div
              key="camera-flow"
              className={`booth-flow booth-flow--${booth.status}`}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            >
              <div className="booth-heading">
                <div className="booth-heading-text">
                  <AnimatePresence mode="wait">
                    {heading && (
                      <motion.h1 key={booth.status} className="booth-title" {...headingAnimation}>
                        {heading}
                      </motion.h1>
                    )}
                  </AnimatePresence>
                  {RAIL_HINTS[booth.status] && (
                    <p className="booth-hint">{RAIL_HINTS[booth.status]}</p>
                  )}
                </div>
                {booth.idleLeftMs !== null && (
                  <IdleRing leftMs={booth.idleLeftMs} onReset={booth.resetIdle} />
                )}
              </div>

              <div className="booth-stage-wrap">
                {booth.status === 'style' && booth.photo ? (
                  <StylePicker
                    photo={booth.photo}
                    traits={booth.traits}
                    styleId={booth.styleId}
                    onToggle={booth.toggleTrait}
                    onStyle={booth.chooseStyle}
                  />
                ) : (
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
                  />
                )}
              </div>

              <AnimatePresence>
                {!cameraError &&
                  (booth.status === 'camera' ||
                    booth.status === 'countdown' ||
                    booth.status === 'capture' ||
                    booth.status === 'reveal' ||
                    booth.status === 'review' ||
                    booth.status === 'style' ||
                    booth.status === 'confirm') && (
                    <motion.div
                      key={`actions-${booth.status}`}
                      className="booth-actions"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
                    >
                      {(booth.status === 'camera' ||
                        booth.status === 'countdown' ||
                        booth.status === 'capture' ||
                        booth.status === 'reveal') && (
                        <BoothControls
                          status={booth.status}
                          countdown={booth.countdown}
                          progress={booth.progress}
                          onStart={() => {
                            autoShot.current = false
                            booth.start()
                          }}
                        />
                      )}

                      {(booth.status === 'review' || booth.status === 'confirm') && (
                        <button
                          type="button"
                          className="btn booth-choice booth-choice--no"
                          onClick={booth.retake}
                        >
                          TOMAR OTRA
                        </button>
                      )}
                      {booth.status === 'review' && (
                        <button
                          type="button"
                          className="btn booth-choice booth-choice--yes"
                          onClick={booth.like}
                        >
                          ME GUSTA
                        </button>
                      )}
                      {booth.status === 'style' && (
                        <button
                          type="button"
                          className="btn booth-choice booth-choice--yes"
                          onClick={booth.proceed}
                        >
                          CONTINUAR
                        </button>
                      )}
                      {booth.status === 'confirm' && (
                        <button
                          type="button"
                          className="btn booth-choice booth-choice--yes"
                          onClick={booth.accept}
                        >
                          ¡SÍ!
                        </button>
                      )}
                    </motion.div>
                  )}
              </AnimatePresence>
            </motion.div>
          )}

          {booth.status === 'drawing' && (
            <DrawingScreen
              key="drawing"
              job={booth.robotJob}
              sketch={booth.sketch}
              strokes={booth.strokes}
              onCancel={() => void booth.cancelDrawing()}
            />
          )}
          {booth.status === 'thanks' && <ThanksScreen key="thanks" />}
          {booth.status === 'robotError' && <RobotErrorScreen key="robot-error" />}
        </AnimatePresence>

        <AnimatePresence>
          {booth.status === 'robotError' && (
            <motion.div
              key="robot-error-actions"
              className="booth-actions booth-actions--scene"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, ease: [0.4, 0, 0.2, 1] }}
            >
              <button type="button" className="btn booth-choice booth-choice--no" onClick={booth.home}>
                INICIO
              </button>
              <button
                type="button"
                className="btn booth-choice booth-choice--yes"
                onClick={booth.retryRobot}
              >
                REINTENTAR
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

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
