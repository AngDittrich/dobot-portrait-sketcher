import { SECTION_TIMEOUT_MS } from '../../hooks/usePhotobooth'

interface IdleRingProps {
  leftMs: number
  onReset: () => void
}

const RADIUS = 28
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

function formatLeft(leftMs: number): string {
  const seconds = Math.max(0, Math.ceil(leftMs / 1000))
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

/**
 * Anillo que se vacía en 3 minutos. Pulsarlo vuelve a llenarlo.
 * El número es el tiempo que queda, no una etiqueta de estado.
 */
export function IdleRing({ leftMs, onReset }: IdleRingProps) {
  const ratio = Math.max(0, Math.min(1, leftMs / SECTION_TIMEOUT_MS))
  const label = formatLeft(leftMs)

  return (
    <button
      type="button"
      className="idle-ring"
      onClick={onReset}
      aria-label={`Quedan ${label}. Pulsa para volver a empezar el tiempo.`}
    >
      <svg viewBox="0 0 72 72" aria-hidden="true">
        <circle className="idle-ring-track" cx="36" cy="36" r={RADIUS} />
        <circle
          className="idle-ring-value"
          cx="36"
          cy="36"
          r={RADIUS}
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - ratio)}
          transform="rotate(-90 36 36)"
        />
      </svg>
      <span className="idle-ring-time">{label}</span>
    </button>
  )
}
