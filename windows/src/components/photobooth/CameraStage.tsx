import { AnimatePresence, motion } from 'framer-motion'
import { CameraOff } from 'lucide-react'
import Webcam from 'react-webcam'
import type { RefObject } from 'react'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'
import { CountdownOverlay } from './CountdownOverlay'
import { FlashOverlay } from './FlashOverlay'
import { ProcessingOverlay } from './ProcessingOverlay'

interface CameraStageProps {
  webcamRef: RefObject<Webcam | null>
  /** Cambiarlo remonta el stream (reintento tras error de permisos). */
  webcamKey: number
  status: PhotoboothStatus
  countdown: number
  photo: string | null
  sketch: string | null
  progress: number
  cameraError: boolean
  onCameraReady: () => void
  onCameraError: () => void
  onRetryCamera: () => void
}

/**
 * Visor de la cabina: feed vivo de la webcam enmarcado con esquinas tipo
 * viewfinder, badge "EN VIVO" y los overlays de cada estado (countdown,
 * flash, reveal del sketch, resultado final).
 */
export function CameraStage({
  webcamRef,
  webcamKey,
  status,
  countdown,
  photo,
  sketch,
  progress,
  cameraError,
  onCameraReady,
  onCameraError,
  onRetryCamera,
}: CameraStageProps) {
  const liveVisible = status === 'idle' || status === 'countdown'

  return (
    <div className={`booth-stage is-${status}`}>
      {!cameraError && (
        <Webcam
          key={webcamKey}
          ref={webcamRef}
          audio={false}
          mirrored
          screenshotFormat="image/jpeg"
          screenshotQuality={0.92}
          videoConstraints={{ width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' }}
          onUserMedia={onCameraReady}
          onUserMediaError={onCameraError}
          className="booth-video"
          style={{ opacity: liveVisible ? 1 : 0 }}
          aria-label="Vista previa de la cámara"
        />
      )}

      {/* Frame congelado bajo el flash */}
      <AnimatePresence>
        {status === 'capture' && photo && (
          <motion.img
            key="frozen"
            src={photo}
            alt="Foto capturada"
            className="booth-result-img"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            draggable={false}
          />
        )}
      </AnimatePresence>

      {/* Transformación a sketch con línea de escaneo */}
      {status === 'processing' && photo && (
        <ProcessingOverlay photo={photo} sketch={sketch} progress={progress} />
      )}

      {/* Resultado final */}
      <AnimatePresence>
        {status === 'review' && sketch && (
          <motion.img
            key="sketch"
            src={sketch}
            alt="Tu retrato convertido en dibujo a lápiz"
            className="booth-result-img"
            initial={{ opacity: 0, scale: 1.015 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
            draggable={false}
          />
        )}
      </AnimatePresence>

      {/* Barrido ambiental mientras la cabina está en reposo */}
      {liveVisible && !cameraError && <div className="booth-scan" aria-hidden="true" />}

      {!cameraError && status !== 'review' && (
        <>
          <span className="booth-corner booth-corner--tl" aria-hidden="true" />
          <span className="booth-corner booth-corner--tr" aria-hidden="true" />
          <span className="booth-corner booth-corner--bl" aria-hidden="true" />
          <span className="booth-corner booth-corner--br" aria-hidden="true" />
        </>
      )}

      {liveVisible && !cameraError && (
        <span className="badge booth-live">
          <span className="booth-live-dot" aria-hidden="true" />
          EN VIVO
        </span>
      )}

      <AnimatePresence>
        {status === 'countdown' && <CountdownOverlay key="countdown" value={countdown} />}
      </AnimatePresence>
      <AnimatePresence>{status === 'capture' && <FlashOverlay key="flash" />}</AnimatePresence>

      {/* Estado vacío: permisos de cámara denegados (patrón empty-state) */}
      {cameraError && (
        <div className="booth-empty" role="alert">
          <span className="booth-empty-icon" aria-hidden="true">
            <CameraOff size={26} />
          </span>
          <p className="booth-empty-title">Necesitamos acceso a tu cámara</p>
          <p className="booth-empty-text">
            Revisa los permisos del navegador para este sitio y vuelve a intentarlo. La cabina no
            guarda ninguna imagen.
          </p>
          <button type="button" className="btn btn-secondary" onClick={onRetryCamera}>
            Reintentar
          </button>
        </div>
      )}
    </div>
  )
}
