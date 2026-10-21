import type { RobotJob } from '../../hooks/usePhotobooth'

/**
 * Aviso de progreso del robot: aparece cuando el boceto aprobado ya está
 * en la cola del brazo robótico y muestra avance y tiempo restante.
 */

interface RobotStatusProps {
  job: RobotJob | null
}

const LABELS: Record<RobotJob['status'], string> = {
  queued: 'El robot está prepping la orden…',
  drawing: 'El robot está dibujando tu retrato',
  done: '¡Retrato terminado en el papel!',
  error: 'El robot no pudo terminar el dibujo',
}

export function RobotStatus({ job }: RobotStatusProps) {
  if (!job) return null

  const percent = Math.round(Math.min(1, Math.max(0, job.progress)) * 100)
  const remaining = job.status === 'drawing' ? ` · ~${Math.ceil(job.etaSeconds)} s` : ''

  return (
    <div className={`robot-status robot-status--${job.status}`} role="status">
      <div className="robot-status-head">
        <span className="robot-status-label">{LABELS[job.status]}</span>
        <span className="robot-status-value">
          {percent}%{remaining}
        </span>
      </div>
      <div className="robot-status-track" aria-hidden="true">
        <div className="robot-status-fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}
