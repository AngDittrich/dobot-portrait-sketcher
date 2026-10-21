import { AnimatePresence, motion } from 'framer-motion'
import { Camera, Loader2 } from 'lucide-react'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'
import { ReviewPanel } from './ReviewPanel'

interface BoothControlsProps {
  status: PhotoboothStatus
  countdown: number
  progress: number
  cameraError: boolean
  onStart: () => void
  onAccept: () => void
  onRetake: () => void
}

const fadeUp = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { type: 'spring', stiffness: 320, damping: 26 },
} as const

/**
 * Zona de acción bajo el visor: cambia según el estado del flujo
 * (CTA principal, píldoras de estado, progreso o decisión final).
 * Altura mínima fija para evitar saltos de layout entre estados.
 */
export function BoothControls({
  status,
  countdown,
  progress,
  cameraError,
  onStart,
  onAccept,
  onRetake,
}: BoothControlsProps) {
  return (
    <div className="booth-actions">
      <AnimatePresence mode="wait">
        {status === 'idle' && (
          <motion.div key="idle" className="booth-actions-block" {...fadeUp}>
            <button
              type="button"
              className="btn btn-primary booth-cta"
              onClick={onStart}
              disabled={cameraError}
            >
              <Camera size={22} aria-hidden="true" />
              ¡Tomar Foto!
            </button>
            <p className="booth-hint">Tu foto se transformará en un dibujo a lápiz al instante</p>
          </motion.div>
        )}

        {status === 'countdown' && (
          <motion.p key="countdown" className="booth-status-pill" {...fadeUp}>
            Foto en {countdown}… ¡mantén la pose!
          </motion.p>
        )}

        {status === 'capture' && (
          <motion.p key="capture" className="booth-status-pill" {...fadeUp}>
            ¡Capturada!
          </motion.p>
        )}

        {status === 'processing' && (
          <motion.div key="processing" className="booth-actions-block" {...fadeUp}>
            <p className="booth-status-pill">
              <Loader2 size={16} className="booth-spin" aria-hidden="true" />
              Dibujando tu retrato…
            </p>
            <div
              className="booth-progress"
              role="progressbar"
              aria-label="Progreso del dibujo"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}
            >
              <div className="booth-progress-fill" style={{ width: `${progress * 100}%` }} />
            </div>
          </motion.div>
        )}

        {status === 'review' && <ReviewPanel key="review" onAccept={onAccept} onRetake={onRetake} />}
      </AnimatePresence>
    </div>
  )
}
