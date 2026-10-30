import { useCallback, useEffect, useState } from 'react'
import { LogOut, OctagonX, ScrollText, Trash2 } from 'lucide-react'
import { adminActivity, adminClearJobs, adminCommand, cancelActiveJob } from '../../lib/api'
import type { AdminActivity, AdminCommand, AdminStatus } from '../../lib/api'
import { useAdminStatus } from '../../hooks/useAdminStatus'
import { ActivitySection } from './ActivitySection'
import { ConfigSection } from './ConfigSection'
import { ControlSection } from './ControlSection'
import { DebugSection } from './DebugSection'
import { SECTIONS } from './sections'
import type { SectionId } from './sections'
import { StatusSection } from './StatusSection'

type Mood = 'connecting' | 'mock' | 'offline' | 'alarm' | 'busy' | 'ready'

/** El estado se cuenta con luz y composición (sin dots ni pills, ver AGENTS.MD). */
function moodOf(status: AdminStatus | null): { key: Mood; text: string } {
  if (!status) return { key: 'connecting', text: 'Conectando…' }
  if (status.backend === 'mock') return { key: 'mock', text: 'Simulador, sin robot físico' }
  // Durante el dibujo el MG400 no siempre contesta el sondeo: el busy local
  // (empieza y termina con el trabajo) cuenta la verdad aunque connected caiga.
  if (status.busy) return { key: 'busy', text: 'Dibujando…' }
  if (!status.connected) return { key: 'offline', text: status.detail || 'Sin enlace' }
  if (status.alarm_text) return { key: 'alarm', text: status.alarm_text }
  return { key: 'ready', text: status.mode_label || 'Conectado' }
}

/**
 * Página del administrador a pantalla completa. Sonda el robot cada 800 ms y
 * la actividad cada 3 s; el PARO queda siempre al alcance en el encabezado.
 *
 * La sección activa (`active`) vive en la URL, no aquí: la controla
 * `AdminArea` para que una recarga de página reabra la misma pestaña.
 */
export function AdminPage({
  token,
  section: active,
  onSection,
  onClose,
  onExpired,
  onDemo,
}: {
  token: string
  section: SectionId
  onSection: (id: SectionId) => void
  onClose: () => void
  onExpired: () => void
  onDemo: () => void
}) {
  const [notice, setNotice] = useState('')
  const [cancelling, setCancelling] = useState(false)
  const { status, pollError } = useAdminStatus(token)
  const [activity, setActivity] = useState<AdminActivity | null>(null)

  const loadActivity = useCallback(async () => {
    try {
      const next = await adminActivity(token)
      setActivity(next)
    } catch {
      // La actividad no es crítica: el estado del robot manda.
    }
  }, [token])

  useEffect(() => {
    let stop = false
    const tick = async () => {
      if (stop) return
      await loadActivity()
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 3000)
    return () => {
      stop = true
      window.clearInterval(timer)
    }
  }, [loadActivity])

  // El token vive en la memoria del servidor: si uvicorn se reinicia, el
  // sondeo recibe 401 para siempre. Se vuelve a pedir el PIN sin salir de
  // esta sección (a diferencia de Salir, que sí vuelve a la cabina).
  useEffect(() => {
    if (pollError.startsWith('Backend 401')) onExpired()
  }, [pollError, onExpired])

  const send = useCallback(
    async (command: AdminCommand) => {
      try {
        await adminCommand(token, command)
        setNotice('')
      } catch (error) {
        setNotice(error instanceof Error ? error.message : 'el robot rechazó la orden')
      }
    },
    [token],
  )

  const clearLogs = useCallback(async () => {
    try {
      await adminClearJobs(token)
      await loadActivity()
      setNotice('')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'no se pudo borrar la bitácora')
    }
  }, [token, loadActivity])

  const cancelDraw = useCallback(async () => {
    setCancelling(true)
    try {
      await cancelActiveJob()
      setNotice('')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'no se pudo cancelar el dibujo')
    } finally {
      setCancelling(false)
    }
  }, [])

  const mood = moodOf(status)
  const strip = notice || pollError
  const hasLogs = (activity?.jobs ?? []).some(
    (job) => job.status === 'done' || job.status === 'error',
  )

  return (
    <div className="admin-page">
      <header className={`admin-top is-${mood.key}`}>
        <span className="admin-top-light" aria-hidden="true" />
        <button type="button" className="admin-brand" onClick={onDemo} aria-label="Ir al demo">
          <img src="/brand/syscomLargeLogo.webp" alt="" />
        </button>
        <div className="admin-top-title">
          <h1>Robot MG400</h1>
          <p>{mood.text}</p>
        </div>
        <div className="admin-top-actions">
          <button
            type="button"
            className={active === 'actividad' ? 'admin-exit is-on' : 'admin-exit'}
            onClick={() => onSection('actividad')}
          >
            <ScrollText size={18} aria-hidden="true" />
            Logs
          </button>
          <button
            type="button"
            className="admin-exit"
            onClick={() => void clearLogs()}
            disabled={!hasLogs}
          >
            <Trash2 size={18} aria-hidden="true" />
            Borrar
          </button>
          <button
            type="button"
            className="admin-estop"
            onClick={() => void send({ action: 'estop' })}
          >
            <OctagonX size={22} aria-hidden="true" />
            Paro
          </button>
          <button type="button" className="admin-exit" onClick={onClose}>
            <LogOut size={18} aria-hidden="true" />
            Salir
          </button>
        </div>
      </header>

      {strip && (
        <p className="admin-strip" role="status">
          {strip}
        </p>
      )}

      <div className="admin-body">
        <nav className="admin-nav" aria-label="Secciones del panel">
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={active === id ? 'is-on' : ''}
              aria-current={active === id ? 'page' : undefined}
              onClick={() => onSection(id)}
            >
              <Icon size={20} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <main className="admin-content">
          {active === 'estado' && <StatusSection status={status} activity={activity} />}
          {active === 'control' && (
            <ControlSection status={status} token={token} send={send} onNotice={setNotice} />
          )}
          {active === 'configuracion' && (
            <ConfigSection status={status} token={token} onNotice={setNotice} />
          )}
          {active === 'actividad' && (
            <ActivitySection
              activity={activity}
              token={token}
              onCancel={() => void cancelDraw()}
              cancelling={cancelling}
            />
          )}
          {active === 'depuracion' && <DebugSection token={token} />}
        </main>
      </div>
    </div>
  )
}
