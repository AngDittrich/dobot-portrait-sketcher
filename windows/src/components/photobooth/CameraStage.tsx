import { AnimatePresence, motion } from 'framer-motion'
import { CameraOff } from 'lucide-react'
import Webcam from 'react-webcam'
import type { ReactNode, RefObject } from 'react'
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
  /** Dock de controles (BoothControls), flotando sobre el borde inferior. */
  children: ReactNode
}

/**
 * Visor del robot sobre el escenario: feed vivo enmarcado por esquinas
 * viewfinder con glow, barrido de luz ambiental y los overlays de cada
 * estado. El estado se comunica con luz y composición — nunca con badges
 * (regla AGENTS.MD / docs §17.6).
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
  children,
}: CameraStageProps) {
  const liveVisible = status === 'camera' || status === 'countdown'
  const showFrame = !cameraError && (status === 'camera' || status === 'countdown' || status === 'capture')
  const showVideo = status === 'camera' || status === 'countdown' || status === 'capture'

  return (
    <div className={`booth-stage is-${status}`}>
      {showVideo && !cameraError && (
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

      {status === 'reveal' && photo && (
        <ProcessingOverlay photo={photo} sketch={sketch} progress={progress} />
      )}

      <AnimatePresence>
        {status === 'confirm' && sketch && (
          <motion.div
            key="print"
            className="booth-print"
            initial={{ opacity: 0, y: 70, rotate: -9, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, rotate: -1.6, scale: 1 }}
            exit={{ opacity: 0, y: 30, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 190, damping: 21 }}
          >
            <div className="booth-print-frame">
              <img src={sketch} alt="Tu retrato convertido en dibujo a lápiz" draggable={false} />
              <span className="booth-print-caption">SYSCOM · Robot Dobot</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Barrido de luz ambiental mientras el robot espera */}
      {status === 'camera' && !cameraError && <div className="booth-scan" aria-hidden="true" />}

      {showFrame && (
        <>
          <span className="booth-corner booth-corner--tl" aria-hidden="true" />
          <span className="booth-corner booth-corner--tr" aria-hidden="true" />
          <span className="booth-corner booth-corner--bl" aria-hidden="true" />
          <span className="booth-corner booth-corner--br" aria-hidden="true" />
        </>
      )}

      <AnimatePresence>
        {status === 'countdown' && countdown > 0 && (
          <CountdownOverlay key="countdown" value={countdown} />
        )}
      </AnimatePresence>
      <AnimatePresence>{status === 'capture' && <FlashOverlay key="flash" />}</AnimatePresence>

      {/* Dock de controles flotante */}
      <div className="booth-dock-wrap">{children}</div>

      {/* Estado vacío: permisos de cámara denegados */}
      {cameraError && (
        <div className="booth-empty" role="alert">
          <span className="booth-empty-icon" aria-hidden="true">
            <CameraOff size={26} />
          </span>
          <p className="booth-empty-title">Necesitamos acceso a tu cámara</p>
          <p className="booth-empty-text">
            Revisa los permisos del navegador para este sitio y vuelve a intentarlo. No se
            guarda ninguna imagen.
          </p>
          <button type="button" className="btn booth-cta booth-cta--glass" onClick={onRetryCamera}>
            Reintentar
          </button>
        </div>
      )}
    </div>
  )
}
