import { adminSketchPreviewUrl } from '../../lib/api'
import type { AdminActivity, AdminActivityJob } from '../../lib/api'
import { ProviderCard } from './ProviderCard'

const STATUS_LABEL: Record<AdminActivityJob['status'], string> = {
  queued: 'En cola',
  drawing: 'Dibujando',
  done: 'Terminado',
  error: 'Error',
}

function timeOf(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString('es-MX', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function duration(job: AdminActivityJob): string {
  if (job.finished_at === null) return 'en curso'
  const seconds = Math.max(0, job.finished_at - job.created_at)
  if (seconds < 60) return `${seconds.toFixed(0)} s`
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

/** Bitácora de dibujos del arranque, con miniatura y el estado del proveedor. */
export function ActivitySection({
  activity,
  token,
  onCancel,
  cancelling,
}: {
  activity: AdminActivity | null
  token: string
  onCancel?: () => void
  cancelling?: boolean
}) {
  if (!activity) {
    return (
      <div className="admin-section">
        <p className="admin-empty">Leyendo la actividad…</p>
      </div>
    )
  }

  return (
    <div className="admin-section admin-activity">
      <section className="admin-card admin-card--jobs">
        <h3>Dibujos recientes</h3>
        {activity.jobs.length === 0 ? (
          <p className="admin-empty">Todavía no hay dibujos en este arranque.</p>
        ) : (
          <ul className="admin-job-list">
            {activity.jobs.map((job) => (
              <li key={job.job_id} className={`admin-job is-${job.status}`}>
                <span className="admin-job-thumb" aria-hidden="true">
                  <img
                    src={adminSketchPreviewUrl(job.sketch_id, token)}
                    alt=""
                    loading="lazy"
                    onError={(event) => event.currentTarget.classList.add('is-gone')}
                  />
                </span>
                <div className="admin-job-info">
                  <strong>{STATUS_LABEL[job.status]}</strong>
                  <span>
                    {timeOf(job.created_at)} · {duration(job)}
                  </span>
                  {job.status === 'drawing' && (
                    <span className="admin-progress">
                      <i style={{ width: `${Math.round(job.progress * 100)}%` }} />
                    </span>
                  )}
                  {job.error && <span className="admin-job-error">{job.error}</span>}
                </div>
                {(job.status === 'drawing' || job.status === 'queued') && onCancel && (
                  <button
                    type="button"
                    className="admin-press admin-job-cancel"
                    onClick={onCancel}
                    disabled={cancelling}
                  >
                    {cancelling ? 'Cancelando…' : 'Cancelar'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="admin-activity-side">
        <ProviderCard provider={activity.provider} />
        <section className="admin-card">
          <h3>Del arranque</h3>
          <div className="admin-counters">
            <div>
              <strong>{activity.totals.done}</strong>
              <span>terminados</span>
            </div>
            <div>
              <strong>{activity.totals.error}</strong>
              <span>con error</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
