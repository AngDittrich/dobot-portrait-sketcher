import { motion } from 'framer-motion'
import type { RobotJob } from '../../hooks/usePhotobooth'
import { RobotStatus } from './RobotStatus'

/**
 * El Dobot dibuja. La orden real sale de usePhotobooth.accept
 * (POST /api/jobs). RobotStatus muestra el progreso del backend.
 */
export function DrawingScreen({ job }: { job: RobotJob | null }) {
  return (
    <motion.section
      className="booth-scene"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      <motion.img
        src="/robot/dobotidlemarker.webp"
        alt="Robot Dobot con marcador, dibujando"
        className="booth-robot"
        draggable={false}
        animate={{ rotate: [0, -1.4, 0.6, 0] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <div className="booth-scene-copy">
        <h1 className="booth-scene-title booth-dots">El robot está dibujando tu imagen ahora</h1>
        <RobotStatus job={job} />
      </div>
    </motion.section>
  )
}
