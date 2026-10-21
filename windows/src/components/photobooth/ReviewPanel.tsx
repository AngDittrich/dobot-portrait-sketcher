import { motion } from 'framer-motion'
import { Heart, RotateCcw } from 'lucide-react'

interface ReviewPanelProps {
  onAccept: () => void
  onRetake: () => void
}

/**
 * Decisión final del flujo: aceptar el retrato (celebración + futuro envío
 * al robot) o descartarlo para repetir la toma.
 */
export function ReviewPanel({ onAccept, onRetake }: ReviewPanelProps) {
  return (
    <motion.div
      className="booth-review"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24 }}
    >
      <p className="booth-review-title">¿Qué te parece tu retrato?</p>
      <div className="booth-review-actions">
        <button type="button" className="btn btn-primary booth-cta" onClick={onAccept}>
          <Heart size={20} aria-hidden="true" />
          ¡Me encanta!
        </button>
        <button
          type="button"
          className="btn btn-secondary booth-cta booth-cta--secondary"
          onClick={onRetake}
        >
          <RotateCcw size={18} aria-hidden="true" />
          Repetir foto
        </button>
      </div>
    </motion.div>
  )
}
