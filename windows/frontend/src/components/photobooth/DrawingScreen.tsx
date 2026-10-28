import { motion } from 'framer-motion'
import type { RobotJob } from '../../hooks/usePhotobooth'
import type { SketchStroke } from '../../lib/sketch'
import { RobotStatus } from './RobotStatus'
import { SketchCanvas } from './SketchCanvas'

/**
 * El Dobot dibuja. La orden real sale de usePhotobooth.accept
 * (POST /api/jobs). RobotStatus muestra el progreso del backend y la hoja
 * se va llenando con los mismos trazos que el brazo está recorriendo.
 */

interface DrawingScreenProps {
  job: RobotJob | null
  sketch: string | null
  strokes: SketchStroke[]
}

export function DrawingScreen({ job, sketch, strokes }: DrawingScreenProps) {
  const drawing = job === null || job.status === 'queued' || job.status === 'drawing'
  const progress = job === null ? null : job.progress

  return (
    <motion.section
      className="booth-scene booth-scene--drawing"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      <motion.div
        className="booth-sheet"
        initial={{ rotate: -1.2, y: 10, opacity: 0 }}
        animate={{ rotate: -1.2, y: 0, opacity: 1 }}
        transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      >
        {strokes.length > 0 ? (
          <SketchCanvas strokes={strokes} progress={progress} />
        ) : sketch ? (
          <img className="booth-sheet-image" src={sketch} alt="Tu retrato en líneas" draggable={false} />
        ) : null}
        <div className="booth-sheet-edge" aria-hidden="true" />
      </motion.div>

      <div className="booth-scene-copy booth-scene-copy--drawing">
        <motion.img
          src="/robot/dobotidlemarker.webp"
          alt="Robot Dobot con marcador, dibujando"
          className="booth-robot booth-robot--drawing"
          draggable={false}
          animate={{ rotate: [0, -1.4, 0.6, 0] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        />
        <h1 className="booth-scene-title booth-dots">
          {drawing ? 'El robot está dibujando tu imagen ahora' : 'Tu retrato está listo'}
        </h1>
        <RobotStatus job={job} />
      </div>
    </motion.section>
  )
}
