import { motion } from 'framer-motion'
import { IRIS_SHARE } from '../../hooks/usePhotobooth'

interface ProcessingOverlayProps {
  photo: string
  sketch: string | null
  /** 0..1 a lo largo de iris + transformación. */
  progress: number
}

/**
 * Reveal en dos tiempos, sincronizado con el progreso del hook:
 * 1. La foto se abre en iris (círculo) con un leve acercamiento.
 * 2. El sketch la cubre en diagonal, con una banda de grafito en el frente.
 * Framer Motion anima la entrada; el barrido sigue el reloj del wizard.
 */
export function ProcessingOverlay({ photo, sketch, progress }: ProcessingOverlayProps) {
  const iris = Math.min(1, progress / IRIS_SHARE)
  const sketchT = progress <= IRIS_SHARE ? 0 : (progress - IRIS_SHARE) / (1 - IRIS_SHARE)
  const cover = sketchT * 200
  const band = Math.round(sketchT * 100)

  return (
    <div className="booth-processing" aria-hidden="true">
      <motion.img
        className="booth-result-img"
        src={photo}
        alt=""
        draggable={false}
        initial={{ scale: 1.08, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.9, ease: [0.22, 0.9, 0.28, 1] }}
        style={{ clipPath: `circle(${8 + iris * 142}% at 50% 46%)` }}
      />

      {sketch && sketchT > 0 && (
        <img
          className="booth-result-img booth-result-sketch"
          src={sketch}
          alt=""
          draggable={false}
          style={{ clipPath: `polygon(0 0, ${cover}% 0, 0 ${cover}%)` }}
        />
      )}

      {sketchT > 0 && sketchT < 1 && (
        <div
          className="booth-diagonal-glow"
          style={{
            background: `linear-gradient(135deg, transparent ${Math.max(0, band - 2)}%, rgba(191, 219, 254, 0.95) ${band}%, transparent ${Math.min(100, band + 3)}%)`,
          }}
        />
      )}

      <div className="booth-progress-rail">
        <div className="booth-progress-fill" style={{ width: `${Math.round(progress * 100)}%` }} />
      </div>
    </div>
  )
}
