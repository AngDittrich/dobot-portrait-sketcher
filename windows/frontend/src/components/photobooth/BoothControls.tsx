import { Camera, Loader2 } from 'lucide-react'
import type { PhotoboothStatus } from '../../hooks/usePhotobooth'

interface BoothControlsProps {
  status: PhotoboothStatus
  countdown: number
  progress: number
  onStart: () => void
}

/**
 * Pie del rail de la toma: el mismo sitio y el mismo peso que las decisiones
 * de las demás pantallas. Durante la cuenta y el reveal, el pie informa en vez
 * de ofrecer un botón.
 */
export function BoothControls({ status, countdown, progress, onStart }: BoothControlsProps) {
  if (status === 'camera') {
    return (
      <button type="button" className="btn booth-choice booth-choice--yes" onClick={onStart}>
        <Camera size={18} aria-hidden="true" />
        ¡Tomar Foto!
      </button>
    )
  }

  if (status === 'countdown' && countdown > 0) {
    return (
      <p className="booth-choice booth-choice--wait" aria-live="polite">
        Foto en {countdown}
      </p>
    )
  }

  if (status === 'capture') {
    return (
      <p className="booth-choice booth-choice--wait" aria-live="polite">
        ¡Perfecta!
      </p>
    )
  }

  if (status === 'reveal') {
    return (
      <p className="booth-choice booth-choice--wait">
        <Loader2 size={16} className="booth-spin" aria-hidden="true" />
        <span
          role="progressbar"
          aria-label="Transformación a dibujo"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
        >
          Convirtiendo tu foto
        </span>
      </p>
    )
  }

  return null
}
