import { useCallback, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type Webcam from 'react-webcam'
import { usePhotobooth } from '../../hooks/usePhotobooth'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'
import { BoothControls } from './BoothControls'
import { CameraStage } from './CameraStage'
import { ConfettiCanvas } from './ConfettiCanvas'
import { Toast } from './Toast'

/** Titular dinámico según el momento del flujo. */
const HEADINGS: Record<PhotoboothStatus, string> = {
  idle: 'Tu retrato, dibujado a lápiz',
  countdown: 'Mantén la pose…',
  capture: '¡Perfecta!',
  processing: 'Trazando tu retrato',
  review: 'Tu retrato está listo',
}

/** Mensajes para tecnologías de asistencia (aria-live). */
const STATUS_MESSAGES: Record<PhotoboothStatus, string> = {
  idle: 'Cabina lista. Pulsa "¡Tomar Foto!" para comenzar.',
  countdown: 'Cuenta regresiva en curso.',
  capture: 'Foto capturada.',
  processing: 'Dibujando tu retrato.',
  review: 'Retrato listo. Elige "¡Me encanta!" o "Repetir foto".',
}

const headingAnimation = {
  initial: { opacity: 0, y: 10, filter: 'blur(4px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  exit: { opacity: 0, y: -8, filter: 'blur(4px)' },
  transition: { duration: 0.28, ease: [0.4, 0, 0.2, 1] },
} as const

/**
 * Orquestador de la experiencia: escenario inmersivo de una sola pantalla
 * (100dvh, sin scroll) con brand bar glass, titular dinámico, visor con
 * dock de controles y capas globales (toast + confetti).
 */
export function PhotoboothApp() {
  const webcamRef = useRef<Webcam>(null)
  const booth = usePhotobooth(webcamRef)
  const [cameraError, setCameraError] = useState(false)
  const [webcamKey, setWebcamKey] = useState(0)

  const handleCameraReady = useCallback(() => setCameraError(false), [])
  const handleCameraError = useCallback(() => setCameraError(true), [])
  const retryCamera = useCallback(() => {
    setCameraError(false)
    setWebcamKey((key) => key + 1)
  }, [])

  return (
    <div className="booth-shell">
      {/* Ambiente: aurora de marca + grano de película */}
      <div className="booth-ambient" aria-hidden="true">
        <span className="booth-aurora booth-aurora--a" />
        <span className="booth-aurora booth-aurora--b" />
        <span className="booth-noise" />
      </div>

      <header className="booth-brandbar">
        <div className="booth-brandbar-inner">
          {/* El logo oficial es negro: se invierte a blanco sobre oscuro (docs §2) */}
          <img
            src="/brand/syscomLargeLogo.webp"
            alt="SYSCOM"
            className="booth-logo"
            draggable={false}
          />
          <span className="booth-brand-divider" aria-hidden="true" />
          <span className="booth-product">Cabina de Retratos</span>
          <span className="booth-demo-note">Modo demo · Sin robot conectado</span>
        </div>
      </header>

      <main className="booth-main">
        <div className="booth-heading">
          <AnimatePresence mode="wait">
            <motion.h1 key={booth.status} className="booth-title" {...headingAnimation}>
              {HEADINGS[booth.status]}
            </motion.h1>
          </AnimatePresence>
          {booth.status === 'idle' && (
            <p className="booth-subtitle">
              Tómate una foto — la cabina la convierte en arte en segundos.
            </p>
          )}
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
            onCameraReady={handleCameraReady}
            onCameraError={handleCameraError}
            onRetryCamera={retryCamera}
          >
            <BoothControls
              status={booth.status}
              countdown={booth.countdown}
              progress={booth.progress}
              cameraError={cameraError}
              onStart={booth.start}
              onAccept={booth.accept}
              onRetake={booth.retake}
            />
          </CameraStage>
        </div>
      </main>

      <Toast toast={booth.toast} onDismiss={booth.dismissToast} />
      <ConfettiCanvas trigger={booth.celebrationId} />

      <p className="sr-only" aria-live="polite">
        {STATUS_MESSAGES[booth.status]}
        {booth.status === 'countdown' ? ` ${booth.countdown}` : ''}
      </p>
    </div>
  )
}
