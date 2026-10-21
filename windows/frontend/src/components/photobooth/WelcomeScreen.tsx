import { motion } from 'framer-motion'

/**
 * Slide de bienvenida del wizard: el robot saluda y una sola acción
 * arranca la cabina. Sin pasos numerados ni etiquetas de estado.
 */
export function WelcomeScreen({ onBegin }: { onBegin: () => void }) {
  return (
    <motion.section
      className="booth-welcome"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, y: -12 }}
      transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
    >
      <motion.img
        src="/robot/dobotsayinghello.webp"
        alt="Robot Dobot saludando"
        className="booth-robot"
        draggable={false}
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: [0, -10, 0] }}
        transition={{
          opacity: { duration: 0.45 },
          y: { duration: 5.2, repeat: Infinity, ease: 'easeInOut' },
        }}
      />
      <div className="booth-welcome-copy">
        <p className="booth-kicker">Cabina de retratos</p>
        <h1 className="booth-welcome-title">Hola</h1>
        <p className="booth-welcome-text">
          Tómate una foto, evalúala, envíala y recibe tu dibujo robótico.
        </p>
        <button type="button" className="btn booth-cta booth-cta--xl" onClick={onBegin}>
          COMENZAR
        </button>
      </div>
    </motion.section>
  )
}
