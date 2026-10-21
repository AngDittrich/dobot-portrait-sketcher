import { AnimatePresence, motion } from 'framer-motion'
import { CheckCircle2, Info, X } from 'lucide-react'
import type { ToastData } from '../../hooks/usePhotobooth'

interface ToastProps {
  toast: ToastData | null
  onDismiss: () => void
}

/**
 * Aviso flotante inferior (patrón alert de la guía: acento lateral de 4px
 * en el color semántico). Entra con slide-up; el auto-cierre lo orquesta
 * `usePhotobooth` (TOAST_MS).
 */
export function Toast({ toast, onDismiss }: ToastProps) {
  return (
    <div className="booth-toast-wrap">
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.id}
            className={`booth-toast booth-toast--${toast.kind}`}
            role="status"
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
          >
            <span className="booth-toast-icon" aria-hidden="true">
              {toast.kind === 'success' ? <CheckCircle2 size={18} /> : <Info size={18} />}
            </span>
            <span className="booth-toast-message">{toast.message}</span>
            <button
              type="button"
              className="booth-toast-close"
              onClick={onDismiss}
              aria-label="Cerrar aviso"
            >
              <X size={15} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
