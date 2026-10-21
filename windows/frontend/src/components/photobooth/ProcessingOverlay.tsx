import { PencilLine } from 'lucide-react'

interface ProcessingOverlayProps {
  /** Fotograma original capturado. */
  photo: string
  /** Retrato ya transformado (puede tardar unos ms más que el progreso). */
  sketch: string | null
  /** Progreso 0..1 del "dibujo". */
  progress: number
}

/**
 * Simulación de "dibujo en tiempo real": la foto original permanece de
 * fondo mientras la versión sketch se revela de arriba hacia abajo con
 * clip-path; una línea de escaneo luminosa marca el frente del trazo.
 */
export function ProcessingOverlay({ photo, sketch, progress }: ProcessingOverlayProps) {
  const reveal = Math.min(100, Math.round(progress * 100))

  return (
    <div className="booth-processing" aria-hidden="true">
      <img className="booth-result-img" src={photo} alt="" draggable={false} />

      {sketch && (
        <img
          className="booth-result-img booth-result-sketch"
          src={sketch}
          alt=""
          draggable={false}
          style={{ clipPath: `inset(0 0 ${100 - reveal}% 0)` }}
        />
      )}

      <div className="booth-scanline" style={{ top: `${reveal}%` }} />

      <div className="booth-processing-chip">
        <PencilLine size={16} className="booth-processing-icon" />
        <span className="booth-dots">Dibujando tu retrato</span>
      </div>
    </div>
  )
}
