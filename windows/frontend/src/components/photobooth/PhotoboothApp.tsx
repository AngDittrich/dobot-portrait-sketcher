import { useCallback, useRef, useState } from 'react'
import type Webcam from 'react-webcam'
import { usePhotobooth } from '../../hooks/usePhotobooth'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'
import { BoothControls } from './BoothControls'
import { CameraStage } from './CameraStage'
import { ConfettiCanvas } from './ConfettiCanvas'
import { Toast } from './Toast'

/** Mensajes para tecnologías de asistencia (aria-live). */
const STATUS_MESSAGES: Record<PhotoboothStatus, string> = {
  idle: 'Cabina lista. Pulsa "¡Tomar Foto!" para comenzar.',
  countdown: 'Cuenta regresiva en curso.',
  capture: 'Foto capturada.',
  processing: 'Dibujando tu retrato.',
  review: 'Retrato listo. Elige "¡Me encanta!" o "Repetir foto".',
}

/**
 * Orquestador de la experiencia: brand bar SYSCOM, encabezado,
 * visor (CameraStage), zona de acción (BoothControls) y capas
 * globales (toast + confetti).
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
      <header className="booth-brandbar">
        <div className="booth-brandbar-inner">
          {/* TODO(BRAND): sustituir el wordmark tipográfico por el logo oficial
              (docs/assets/brand/syscomLargeLogo.webp) cuando el asset esté
              disponible en este repo; sobre fondo oscuro va en blanco. */}
          <span className="booth-wordmark">SYSCOM</span>
          <span className="booth-brand-divider" aria-hidden="true" />
          <span className="booth-product">Cabina de Retratos</span>
          <span className="booth-demo-badge">Demo UI · sin robot conectado</span>
        </div>
      </header>

      <main className="booth-main">
        <div className="booth-heading">
          <p className="micro-label">Photobooth interactivo</p>
          <h1 className="booth-title">Convierte tu foto en un retrato a lápiz</h1>
          <p className="booth-subtitle">
            Tómate una foto y observa cómo se dibuja tu retrato en segundos.
          </p>
        </div>

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
        />

        <BoothControls
          status={booth.status}
          countdown={booth.countdown}
          progress={booth.progress}
          cameraError={cameraError}
          onStart={booth.start}
          onAccept={booth.accept}
          onRetake={booth.retake}
        />
      </main>

      <footer className="booth-footer">
        <span className="micro-label">SYSCOM · Experiencia interactiva</span>
      </footer>

      <Toast toast={booth.toast} onDismiss={booth.dismissToast} />
      <ConfettiCanvas trigger={booth.celebrationId} />

      <p className="sr-only" aria-live="polite">
        {STATUS_MESSAGES[booth.status]}
        {booth.status === 'countdown' ? ` ${booth.countdown}` : ''}
      </p>
    </div>
  )
}
