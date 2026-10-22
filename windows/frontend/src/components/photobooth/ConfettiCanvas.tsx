import { useEffect, useRef } from 'react'
import { fireConfetti } from '../../lib/confetti'

interface ConfettiCanvasProps {
  /** Cada cambio (distinto de 0) dispara una ráfaga. */
  trigger: number
}

/**
 * Capa de celebración a pantalla completa. No captura eventos del puntero
 * y respeta `prefers-reduced-motion` (no dispara la ráfaga).
 */
export function ConfettiCanvas({ trigger }: ConfettiCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (trigger === 0) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const canvas = canvasRef.current
    if (!canvas) return
    return fireConfetti(canvas)
  }, [trigger])

  return <canvas ref={canvasRef} className="booth-confetti" aria-hidden="true" />
}
