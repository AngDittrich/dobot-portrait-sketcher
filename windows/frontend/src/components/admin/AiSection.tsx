import type { AdminActivity } from '../../lib/api'
import { ProviderCard } from './ProviderCard'

/** Ruta, modelo y respaldo del boceto. Solo lectura: se elige por el entorno. */
export function AiSection({ activity }: { activity: AdminActivity | null }) {
  if (!activity) {
    return (
      <div className="admin-section">
        <p className="admin-empty">Leyendo el proveedor…</p>
      </div>
    )
  }

  return (
    <div className="admin-section admin-grid">
      <ProviderCard provider={activity.provider} />
    </div>
  )
}
