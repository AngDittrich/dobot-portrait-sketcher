import { motion } from 'framer-motion'

/** Cierre del wizard. Vuelve solo a la bienvenida (THANKS_MS). */
export function ThanksScreen() {
  return (
    <motion.section
      className="booth-scene booth-scene--thanks"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 0.9, 0.28, 1] }}
    >
      <motion.img
        src="/wizard/portrait-ready.jpg"
        alt="Retrato a lápiz listo para llevar"
        className="booth-thanks-art"
        draggable={false}
        initial={{ rotate: -6, y: 40, opacity: 0 }}
        animate={{ rotate: -1.5, y: 0, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 180, damping: 18 }}
      />
      <div className="booth-scene-copy">
        <h1 className="booth-scene-title">LISTO. TOMA TU DIBUJO.</h1>
        <p className="booth-welcome-text">SYSCOM agradece tu visita.</p>
      </div>
    </motion.section>
  )
}
