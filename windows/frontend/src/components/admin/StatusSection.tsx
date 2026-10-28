import type { AdminActivity, AdminStatus } from '../../lib/api'
import { ProviderCard } from './ProviderCard'

function format(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(number)) return '—'
  return number.toFixed(2)
}

function fact(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (value === true) return 'sí'
  if (value === false) return 'no'
  return String(value)
}

/** Tablero de un vistazo: pose, cabina, proveedor de IA y dibujos del arranque. */
export function StatusSection({
  status,
  activity,
}: {
  status: AdminStatus | null
  activity: AdminActivity | null
}) {
  const live = status?.pose ?? []
  const angles = status?.angles ?? []
  const frame = status?.frame ?? {}
  const currentJob =
    activity?.jobs.find((job) => job.status === 'drawing' || job.status === 'queued') ?? null

  return (
    <div className="admin-section admin-grid">
      <section className="admin-card admin-card--pose">
        <h3>Pose en vivo</h3>
        <div className="admin-pose-readout">
          {(['X', 'Y', 'Z', 'R'] as const).map((axis, index) => (
            <div key={axis} className="admin-pose-axis">
              <span>{axis}</span>
              <strong>{format(live[index])}</strong>
            </div>
          ))}
        </div>
        <div className="admin-joints-readout">
          {[0, 1, 2, 3].map((index) => (
            <div key={index}>
              <span>J{index + 1}</span>
              <strong>{format(angles[index])}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="admin-card">
        <h3>Cabina</h3>
        <dl className="admin-facts">
          <div>
            <dt>Modo</dt>
            <dd>{frame.backend === 'mg400' ? 'Robot' : 'Simulador'}</dd>
          </div>
          <div>
            <dt>IP</dt>
            <dd>{fact(frame.host)}</dd>
          </div>
          <div>
            <dt>Sin mover</dt>
            <dd>{fact(frame.dry_run)}</dd>
          </div>
          <div>
            <dt>Velocidad dibujo</dt>
            <dd>{fact(frame.speed_factor)}</dd>
          </div>
          <div>
            <dt>Z dibujo / viaje</dt>
            <dd>
              {fact(frame.z_draw)} / {fact(frame.z_travel)}
            </dd>
          </div>
        </dl>
      </section>

      {activity && <ProviderCard provider={activity.provider} />}

      <section className="admin-card">
        <h3>Dibujos del arranque</h3>
        <div className="admin-counters">
          <div>
            <strong>{activity?.totals.done ?? 0}</strong>
            <span>terminados</span>
          </div>
          <div>
            <strong>{activity?.totals.error ?? 0}</strong>
            <span>con error</span>
          </div>
        </div>
        {currentJob && (
          <div className="admin-current-job">
            <p>
              Ahora mismo: {currentJob.status === 'queued' ? 'en cola' : 'dibujando'}{' '}
              {Math.round(currentJob.progress * 100)}%
            </p>
            <span className="admin-progress">
              <i style={{ width: `${Math.round(currentJob.progress * 100)}%` }} />
            </span>
          </div>
        )}
      </section>
    </div>
  )
}
