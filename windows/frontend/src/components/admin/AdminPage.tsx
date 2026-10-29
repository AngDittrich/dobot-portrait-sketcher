import { useCallback, useEffect, useState } from 'react'
import { Gamepad2, Gauge, History, LogOut, OctagonX, Settings } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { adminActivity, adminCommand } from '../../lib/api'
import type { AdminActivity, AdminCommand, AdminStatus } from '../../lib/api'
import { useAdminStatus } from '../../hooks/useAdminStatus'
import { ActivitySection } from './ActivitySection'
import { ConfigSection } from './ConfigSection'
import { ControlSection } from './ControlSection'
import { StatusSection } from './StatusSection'

type SectionId = 'estado' | 'control' | 'configuracion' | 'actividad'

const SECTIONS: { id: SectionId; label: string; icon: LucideIcon }[] = [
  { id: 'estado', label: 'Estado', icon: Gauge },
  { id: 'control', label: 'Control', icon: Gamepad2 },
  { id: 'configuracion', label: 'Configuración', icon: Settings },
  { id: 'actividad', label: 'Actividad', icon: History },
]

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
 */
export function AdminPage({ token, onClose }: { token: string; onClose: () => void }) {
  const [active, setActive] = useState<SectionId>('estado')
  const [notice, setNotice] = useState('')
  const { status, pollError } = useAdminStatus(token)
  const [activity, setActivity] = useState<AdminActivity | null>(null)

  useEffect(() => {
    let stop = false
    const tick = async () => {
      try {
        const next = await adminActivity(token)
        if (!stop) setActivity(next)
      } catch {
        // La actividad no es crítica: el estado del robot manda.
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 3000)
    return () => {
      stop = true
      window.clearInterval(timer)
    }
  }, [token])

  // El token vive en la memoria del servidor: si uvicorn se reinicia, el
  // sondeo recibe 401 para siempre. Se vuelve al PIN en vez de quedarse mudo.
  useEffect(() => {
    if (pollError.startsWith('Backend 401')) onClose()
  }, [pollError, onClose])

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

  const mood = moodOf(status)
  const strip = notice || pollError

  return (
    <div className="admin-page">
      <header className={`admin-top is-${mood.key}`}>
        <span className="admin-top-light" aria-hidden="true" />
        <div className="admin-top-title">
          <h1>Robot MG400</h1>
          <p>{mood.text}</p>
        </div>
        <div className="admin-top-actions">
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
              onClick={() => setActive(id)}
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
          {active === 'actividad' && <ActivitySection activity={activity} token={token} />}
        </main>
      </div>
    </div>
  )
}
