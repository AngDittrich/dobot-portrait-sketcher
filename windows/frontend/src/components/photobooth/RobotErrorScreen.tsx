import { motion } from 'framer-motion'

/**
 * El trabajo del robot terminó con error. No vuelve sola a la bienvenida:
 * alguien del equipo tiene que verla. REINTENTAR e INICIO viven en la
 * barra de botones de PhotoboothApp; el detalle técnico sale en la consola.
 */
export function RobotErrorScreen() {
  return (
    <motion.section
      className="booth-scene"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      <img
        src="/robot/dobot-robot-error.webp"
        alt="Robot Dobot detenido"
        className="booth-robot"
        draggable={false}
      />
      <div className="booth-scene-copy">
        <h1 className="booth-scene-title">EL ROBOT SE DETUVO</h1>
        <p className="booth-welcome-text">Avísale al equipo de SYSCOM para revisarlo.</p>
      </div>
    </motion.section>
  )
}
