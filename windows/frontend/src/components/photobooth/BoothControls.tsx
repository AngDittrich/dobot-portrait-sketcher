import { AnimatePresence, motion } from 'framer-motion'
import { Camera, Loader2 } from 'lucide-react'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'

interface BoothControlsProps {
  status: PhotoboothStatus
  countdown: number
  progress: number
  cameraError: boolean
  onStart: () => void
}

const dockAnimation = {
  initial: { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -10 },
  transition: { type: 'spring', stiffness: 320, damping: 26 },
} as const

/**
 * Dock del visor durante la toma y el reveal.
 * La decisión (TOMAR OTRA / ¡SÍ!) vive fuera, anclada a las esquinas.
 */
export function BoothControls({
  status,
  countdown,
  progress,
  cameraError,
  onStart,
}: BoothControlsProps) {
  if (cameraError || status === 'confirm') return null

  return (
    <AnimatePresence mode="wait">
      {status === 'camera' && (
        <motion.div key="camera" className="booth-dock" {...dockAnimation}>
          <button type="button" className="btn booth-cta" onClick={onStart}>
            <Camera size={20} aria-hidden="true" />
            ¡Tomar Foto!
          </button>
        </motion.div>
      )}

      {status === 'countdown' && countdown > 0 && (
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

      {status === 'reveal' && (
        <motion.div key="reveal" className="booth-dock" {...dockAnimation}>
          <span className="booth-dock-text">
            <Loader2 size={16} className="booth-spin" aria-hidden="true" />
            <span
              className="booth-dots"
              role="progressbar"
              aria-label="Transformación a dibujo"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)}
            >
              Convirtiendo tu foto
            </span>
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
