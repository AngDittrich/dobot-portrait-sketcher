import { useEffect, useState } from 'react'
import { adminArchive, adminArchiveImageUrl } from '../../lib/api'
import type { ArchiveVisit } from '../../lib/api'

function timeOf(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString('es-MX', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Las seis etapas de cada visita, leídas del archivo en disco. No vuelve a llamar a la IA. */
export function DebugSection({ token }: { token: string }) {
  const [visits, setVisits] = useState<ArchiveVisit[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    let stop = false
    adminArchive(token)
      .then((payload) => {
        if (stop) return
        setVisits(payload.visits)
        setSelected((current) => current ?? payload.visits[0]?.folder ?? null)
      })
      .catch((reason: unknown) => {
        if (!stop) setError(reason instanceof Error ? reason.message : 'no se pudo leer el archivo')
      })
    return () => {
      stop = true
    }
  }, [token])

  if (error) {
    return (
      <div className="admin-section">
        <p className="admin-empty">{error}</p>
      </div>
    )
  }
  if (!visits) {
    return (
      <div className="admin-section">
        <p className="admin-empty">Leyendo las visitas…</p>
      </div>
    )
  }
  if (visits.length === 0) {
    return (
      <div className="admin-section">
        <p className="admin-empty">Todavía no hay fotos en el archivo.</p>
      </div>
    )
  }

  const visit = visits.find((item) => item.folder === selected) ?? visits[0]

  return (
    <div className="admin-section admin-debug">
      <section className="admin-card">
        <h3>Visitas</h3>
        <ul className="admin-debug-list">
          {visits.map((item) => (
            <li key={item.folder}>
              <button
                type="button"
                className={item.folder === visit.folder ? 'is-on' : ''}
                onClick={() => setSelected(item.folder)}
              >
                <strong>{timeOf(item.created_at)}</strong>
                <span>{item.model || 'sin modelo'}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <ol className="admin-debug-steps">
        {visit.steps.map((step, index) => (
          <li key={step.file} className="admin-card">
            <p className="admin-debug-kicker">
              {index + 1} · {step.title}
            </p>
            <img
              src={adminArchiveImageUrl(visit.folder, step.file, token)}
              alt={step.title}
            />
            <p>{step.note}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}
