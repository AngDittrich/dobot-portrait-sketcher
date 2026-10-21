import { AnimatePresence, motion } from 'framer-motion'

/**
 * Números 3-2-1 a pantalla completa sobre el visor.
 * Cada dígito entra con un spring (escala grande → natural) rodeado de
 * glow y un anillo expansivo que marca el ritmo de la captura.
 */
export function CountdownOverlay({ value }: { value: number }) {
  return (
    <div className="booth-countdown" aria-hidden="true">
      <AnimatePresence mode="popLayout">
        <motion.div
          key={value}
          className="booth-countdown-inner"
          initial={{ scale: 2.1, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0.55, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        >
          <motion.span
            className="booth-countdown-ring"
            initial={{ scale: 0.55, opacity: 0.9 }}
            animate={{ scale: 1.7, opacity: 0 }}
            transition={{ duration: 0.9, ease: 'easeOut' }}
          />
          <span className="booth-countdown-number">{value}</span>
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
