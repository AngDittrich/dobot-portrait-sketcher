import { motion } from 'framer-motion'

/**
 * Flash de cámara: destello blanco rápido que se disipa,
 * dejando ver el fotograma congelado capturado.
 */
export function FlashOverlay() {
  return (
    <motion.div
      className="booth-flash"
      initial={{ opacity: 0 }}
      animate={{ opacity: [0, 1, 0.35] }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5, times: [0, 0.2, 1], ease: 'easeOut' }}
      aria-hidden="true"
    />
  )
}
