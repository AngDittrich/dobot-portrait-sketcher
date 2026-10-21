import { AnimatePresence, motion } from 'framer-motion'
import { Info, Sparkles, X } from 'lucide-react'
import type { ToastData } from '../../hooks/usePhotobooth'

interface ToastProps {
  toast: ToastData | null
  onDismiss: () => void
}

/**
 * Aviso flotante inferior: tarjeta oscura "glass" coherente con el
 * escenario (docs §17.5). Sin colores semánticos estridentes ni badges
 * genéricos; el auto-cierre lo orquesta `usePhotobooth` (TOAST_MS).
 */
export function Toast({ toast, onDismiss }: ToastProps) {
  return (
    <div className="booth-toast-wrap">
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.id}
            className="booth-toast"
            role="status"
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            transition={{ type: 'spring', stiffness: 380, damping: 28 }}
          >
            <span className="booth-toast-icon" aria-hidden="true">
              {toast.kind === 'success' ? <Sparkles size={18} /> : <Info size={18} />}
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
