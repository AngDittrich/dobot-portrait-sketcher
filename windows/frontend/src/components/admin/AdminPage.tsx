import { useCallback, useEffect, useState } from 'react'
import { LogOut, Menu, OctagonX, ScrollText, Trash2, X } from 'lucide-react'
import { adminActivity } from '../../lib/api'
import type { AdminActivity, AdminStatus } from '../../lib/api'
import { useAdminActions } from '../../hooks/useAdminActions'
import { useAdminStatus } from '../../hooks/useAdminStatus'
import { DEFAULT_PAD_TUNE, usePad } from '../../hooks/usePad'
import type { PadTune } from '../../hooks/usePad'
import { ActivitySection } from './ActivitySection'
import { AiSection } from './AiSection'
import { CalibrationSection } from './CalibrationSection'
import { ConfigSection } from './ConfigSection'
import { ControlSection } from './ControlSection'
import { DebugSection } from './DebugSection'
import { DrawSection } from './DrawSection'
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
  const [clearing, setClearing] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [speed, setSpeed] = useState(50)
  const [tune, setTune] = useState<PadTune>(DEFAULT_PAD_TUNE)
  const [navOpen, setNavOpen] = useState(false)
  // En Control y Configuración el brazo se mueve a mano: la pose de hace un
  // segundo se sentía como delay. En las demás pestañas basta con 1 s.
  const pollMs = active === 'control' || active === 'calibracion' || active === 'configuracion' ? 400 : 1000
  const { status, pollError } = useAdminStatus(token, pollMs)
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

  const actions = useAdminActions(token, {
    onNotice: setNotice,
    onExpired,
    reloadActivity: loadActivity,
  })

  const clearLogs = useCallback(async () => {
    if (clearing) return
    setClearing(true)
    try {
      await actions.clearLogs()
    } catch {
      // El aviso ya lo dejó el hook.
    } finally {
      setClearing(false)
    }
  }, [actions, clearing])

  const pad = usePad({
    token,
    speed,
    setSpeed,
    busy: Boolean(status?.busy),
    drag: status?.mode === 6,
    tune,
    onClearLogs: () => void clearLogs(),
    onNotice: setNotice,
  })

  const cancelDraw = useCallback(async () => {
    if (cancelling) return
    setCancelling(true)
    try {
      await actions.cancelDraw()
    } catch {
      // El aviso ya lo dejó el hook.
    } finally {
      setCancelling(false)
    }
  }, [actions, cancelling])

  const mood = moodOf(status)
  const strip = notice || pollError
  const hasLogs = (activity?.jobs ?? []).some(
    (job) => job.status === 'done' || job.status === 'error',
  )

  // El menú plegado se cierra con Escape y al elegir sección: en tablet no
  // hay sitio para dejarlo abierto sobre el contenido.
  useEffect(() => {
    if (!navOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])

  const go = (id: SectionId) => {
    onSection(id)
    setNavOpen(false)
  }

  return (
    <div className="admin-page">
      <header className={`admin-top is-${mood.key}`}>
        <span className="admin-top-light" aria-hidden="true" />
        <button
          type="button"
          className="admin-menu"
          aria-expanded={navOpen}
          aria-controls="admin-nav"
          onClick={() => setNavOpen((open) => !open)}
        >
          <Menu size={20} aria-hidden="true" />
          <span>Menú</span>
        </button>
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
            aria-label="Logs"
            onClick={() => go('actividad')}
          >
            <ScrollText size={18} aria-hidden="true" />
            <span className="admin-action-label">Logs</span>
          </button>
          <button
            type="button"
            className="admin-exit"
            aria-label="Borrar trabajos cerrados"
            onClick={() => void clearLogs()}
            disabled={!hasLogs || clearing}
          >
            <Trash2 size={18} aria-hidden="true" />
            <span className="admin-action-label">Borrar</span>
          </button>
          <button
            type="button"
            className="admin-estop"
            aria-label="Paro de emergencia"
            onClick={() => void actions.send({ action: 'estop' })}
          >
            <OctagonX size={20} aria-hidden="true" />
            <span>Paro</span>
          </button>
          <button
            type="button"
            className="admin-exit"
            aria-label="Salir del panel"
            onClick={onClose}
          >
            <LogOut size={18} aria-hidden="true" />
            <span className="admin-action-label">Salir</span>
          </button>
        </div>
      </header>

      {strip && (
        <p className="admin-strip" role="status">
          {strip}
        </p>
      )}

      <div className="admin-body">
        <nav id="admin-nav" className={navOpen ? 'admin-nav is-open' : 'admin-nav'} aria-label="Secciones del panel">
          <div className="admin-nav-head">
            <span>Secciones</span>
            <button
              type="button"
              className="admin-nav-close"
              aria-label="Cerrar el menú"
              onClick={() => setNavOpen(false)}
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          {SECTIONS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={active === id ? 'is-on' : ''}
              aria-current={active === id ? 'page' : undefined}
              onClick={() => go(id)}
            >
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        {navOpen && (
          <button
            type="button"
            className="admin-nav-scrim"
            aria-label="Cerrar el menú"
            onClick={() => setNavOpen(false)}
          />
        )}

        <main className="admin-content">
          {active === 'estado' && <StatusSection status={status} activity={activity} />}
          {active === 'control' && (
            <ControlSection
              status={status}
              token={token}
              actions={actions}
              onNotice={setNotice}
              speed={speed}
              onSpeed={setSpeed}
              pad={pad}
              tune={tune}
              onTune={setTune}
            />
          )}
          {active === 'calibracion' && <CalibrationSection status={status} actions={actions} />}
          {active === 'dibujar' && <DrawSection status={status} />}
          {active === 'ia' && <AiSection activity={activity} />}
          {active === 'configuracion' && (
            <ConfigSection status={status} actions={actions} speed={speed} onSpeed={setSpeed} />
          )}
          {active === 'actividad' && (
            <ActivitySection
              activity={activity}
              token={token}
              onCancel={() => void cancelDraw()}
              cancelling={cancelling}
              onClear={() => void clearLogs()}
              clearing={clearing}
              canClear={hasLogs}
            />
          )}
          {active === 'depuracion' && <DebugSection token={token} />}
        </main>
      </div>
    </div>
  )
}
