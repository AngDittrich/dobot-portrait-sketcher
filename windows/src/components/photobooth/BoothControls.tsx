import { AnimatePresence, motion } from 'framer-motion'
import { Camera, Heart, Loader2, RotateCcw } from 'lucide-react'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'

interface BoothControlsProps {
  status: PhotoboothStatus
  countdown: number
  progress: number
  cameraError: boolean
  onStart: () => void
  onAccept: () => void
  onRetake: () => void
}

const dockAnimation = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
  transition: { type: 'spring', stiffness: 320, damping: 26 },
} as const

/**
 * Dock flotante "liquid glass" sobre el visor: un único punto de acción
 * que cambia según el momento del flujo (CTA obturador, estado, decisión).
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
  // Con el empty-state de permisos visible, el dock no estorba
  if (cameraError) return null

  return (
    <AnimatePresence mode="wait">
      {status === 'idle' && (
        <motion.div key="idle" className="booth-dock" {...dockAnimation}>
          <button type="button" className="btn booth-cta" onClick={onStart}>
            <Camera size={20} aria-hidden="true" />
            ¡Tomar Foto!
          </button>
        </motion.div>
      )}

      {status === 'countdown' && (
        <motion.div key="countdown" className="booth-dock" {...dockAnimation}>
          <span className="booth-dock-text">
            Foto en <strong>{countdown}</strong>
          </span>
        </motion.div>
      )}

      {status === 'capture' && (
        <motion.div key="capture" className="booth-dock" {...dockAnimation}>
          <span className="booth-dock-text">¡Perfecta!</span>
        </motion.div>
      )}

      {status === 'processing' && (
        <motion.div key="processing" className="booth-dock" {...dockAnimation}>
          <span className="booth-dock-text">
            <Loader2 size={16} className="booth-spin" aria-hidden="true" />
            <span
              className="booth-dots"
              role="progressbar"
              aria-label="Progreso del dibujo"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}
            >
              Dibujando tu retrato
            </span>
          </span>
        </motion.div>
      )}

      {status === 'review' && (
        <motion.div key="review" className="booth-dock" {...dockAnimation}>
          <span className="booth-dock-text">¿Qué te parece?</span>
          <div className="booth-review-actions">
            <button type="button" className="btn booth-cta" onClick={onAccept}>
              <Heart size={18} aria-hidden="true" />
              ¡Me encanta!
            </button>
            <button
              type="button"
              className="btn booth-cta booth-cta--glass"
              onClick={onRetake}
            >
              <RotateCcw size={16} aria-hidden="true" />
              Repetir
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
