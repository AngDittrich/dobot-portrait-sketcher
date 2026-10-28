import { useEffect, useRef, useState } from 'react'
import { saveAdminBooth } from '../../lib/api'
import type { AdminStatus } from '../../lib/api'

/**
 * Calibración de la cabina, agrupada por tema. Al guardar, los valores quedan
 * en `data/robot.json` y mandan sobre el `.env` desde el siguiente dibujo.
 */

type BoothForm = {
  backend: string
  host: string
  dry_run: boolean
  user: string
  tool: string
  z_draw: string
  z_travel: string
  r: string
  r_far: string
  far_x: string
  far_y: string
  speed_factor: string
  origin_x: string
  origin_y: string
  x_sign: string
  y_sign: string
  cp_draw: string
}

function fieldText(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  return String(value)
}

function boothFromFrame(frame: Record<string, number | string | boolean | null>): BoothForm {
  return {
    backend: fieldText(frame.backend) || 'mg400',
    host: fieldText(frame.host),
    dry_run: frame.dry_run === true || frame.dry_run === 'true' || frame.dry_run === 1,
    user: fieldText(frame.user ?? 0),
    tool: fieldText(frame.tool ?? 0),
    z_draw: fieldText(frame.z_draw),
    z_travel: fieldText(frame.z_travel),
    r: fieldText(frame.r),
    r_far: fieldText(frame.r_far),
    far_x: fieldText(frame.far_x),
    far_y: fieldText(frame.far_y),
    speed_factor: fieldText(frame.speed_factor ?? 20),
    origin_x: fieldText(frame.origin_x),
    origin_y: fieldText(frame.origin_y),
    x_sign: fieldText(frame.x_sign ?? -1),
    y_sign: fieldText(frame.y_sign ?? -1),
    cp_draw: fieldText(frame.cp_draw ?? 0),
  }
}

export function ConfigSection({
  status,
  token,
  onNotice,
}: {
  status: AdminStatus | null
  token: string
  onNotice: (message: string) => void
}) {
  const [booth, setBooth] = useState<BoothForm | null>(null)
  const boothReady = useRef(false)
  const [saving, setSaving] = useState(false)
  const busy = Boolean(status?.busy)
  const live = status?.pose ?? []

  useEffect(() => {
    const frame = status?.frame
    if (boothReady.current || !frame || (frame.origin_x == null && frame.host == null)) return
    boothReady.current = true
    setBooth(boothFromFrame(frame))
  }, [status])

  function patch<K extends keyof BoothForm>(key: K, value: BoothForm[K]) {
    setBooth((current) => current && { ...current, [key]: value })
  }

  function teach(which: 'origin' | 'far') {
    if (live.length < 4) return
    setBooth((current) => {
      if (!current) return current
      if (which === 'origin') {
        return {
          ...current,
          origin_x: String(live[0]),
          origin_y: String(live[1]),
          z_draw: String(live[2]),
          r: String(live[3]),
        }
      }
      return {
        ...current,
        far_x: String(live[0]),
        far_y: String(live[1]),
        r_far: String(live[3]),
      }
    })
  }

  async function saveBooth() {
    if (!booth || saving) return
    setSaving(true)
    const number = (value: string) => Number(value)
    try {
      await saveAdminBooth(token, {
        backend: booth.backend,
        host: booth.host.trim(),
        dry_run: booth.dry_run,
        user: number(booth.user),
        tool: number(booth.tool),
        z_draw: number(booth.z_draw),
        z_travel: number(booth.z_travel),
        r: number(booth.r),
        r_far: number(booth.r_far),
        far_x: number(booth.far_x),
        far_y: number(booth.far_y),
        speed_factor: number(booth.speed_factor),
        origin_x: number(booth.origin_x),
        origin_y: number(booth.origin_y),
        x_sign: number(booth.x_sign),
        y_sign: number(booth.y_sign),
        cp_draw: number(booth.cp_draw),
      })
      onNotice('Cabina guardada. El siguiente dibujo usa estos valores.')
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo guardar la cabina')
    } finally {
      setSaving(false)
    }
  }

  if (!booth) {
    return (
      <div className="admin-section">
        <p className="admin-empty">Leyendo la calibración del robot…</p>
      </div>
    )
  }

  return (
    <div className="admin-section">
      <form
        className="admin-config"
        onSubmit={(event) => {
          event.preventDefault()
          void saveBooth()
        }}
      >
        <section className="admin-card">
          <h3>Conexión</h3>
          <div className="admin-fields">
            <label>
              Modo
              <select value={booth.backend} onChange={(event) => patch('backend', event.target.value)}>
                <option value="mg400">Robot</option>
                <option value="mock">Simulador</option>
              </select>
            </label>
            <label>
              IP
              <input value={booth.host} onChange={(event) => patch('host', event.target.value)} />
            </label>
            <label className="admin-check">
              <input
                type="checkbox"
                checked={booth.dry_run}
                onChange={(event) => patch('dry_run', event.target.checked)}
              />
              Sin mover (simula el dibujo)
            </label>
          </div>
        </section>

        <section className="admin-card">
          <h3>Hoja y calibración</h3>
          <div className="admin-fields">
            <label>
              Origen X
              <input inputMode="decimal" value={booth.origin_x} onChange={(event) => patch('origin_x', event.target.value)} />
            </label>
            <label>
              Origen Y
              <input inputMode="decimal" value={booth.origin_y} onChange={(event) => patch('origin_y', event.target.value)} />
            </label>
            <label>
              Z dibujo
              <input inputMode="decimal" value={booth.z_draw} onChange={(event) => patch('z_draw', event.target.value)} />
            </label>
            <label>
              Z viaje
              <input inputMode="decimal" value={booth.z_travel} onChange={(event) => patch('z_travel', event.target.value)} />
            </label>
            <label>
              R origen
              <input inputMode="decimal" value={booth.r} onChange={(event) => patch('r', event.target.value)} />
            </label>
            <label>
              Esquina X
              <input inputMode="decimal" value={booth.far_x} onChange={(event) => patch('far_x', event.target.value)} />
            </label>
            <label>
              Esquina Y
              <input inputMode="decimal" value={booth.far_y} onChange={(event) => patch('far_y', event.target.value)} />
            </label>
            <label>
              R esquina
              <input inputMode="decimal" value={booth.r_far} onChange={(event) => patch('r_far', event.target.value)} />
            </label>
          </div>
          <div className="admin-card-actions">
            <button type="button" className="admin-press" disabled={live.length < 4} onClick={() => teach('origin')}>
              Pose como origen
            </button>
            <button type="button" className="admin-press" disabled={live.length < 4} onClick={() => teach('far')}>
              Pose como esquina
            </button>
          </div>
        </section>

        <section className="admin-card">
          <h3>Cinemática</h3>
          <div className="admin-fields">
            <label>
              Usuario
              <input inputMode="decimal" value={booth.user} onChange={(event) => patch('user', event.target.value)} />
            </label>
            <label>
              Herramienta
              <input inputMode="decimal" value={booth.tool} onChange={(event) => patch('tool', event.target.value)} />
            </label>
            <label>
              Signo X
              <select value={booth.x_sign} onChange={(event) => patch('x_sign', event.target.value)}>
                <option value="-1">-1</option>
                <option value="1">1</option>
              </select>
            </label>
            <label>
              Signo Y
              <select value={booth.y_sign} onChange={(event) => patch('y_sign', event.target.value)}>
                <option value="-1">-1</option>
                <option value="1">1</option>
              </select>
            </label>
          </div>
        </section>

        <section className="admin-card">
          <h3>Dibujo</h3>
          <div className="admin-fields">
            <label>
              Velocidad
              <input inputMode="decimal" value={booth.speed_factor} onChange={(event) => patch('speed_factor', event.target.value)} />
            </label>
            <label>
              CP
              <input inputMode="decimal" value={booth.cp_draw} onChange={(event) => patch('cp_draw', event.target.value)} />
            </label>
          </div>
        </section>

        <div className="admin-config-save">
          <button type="submit" className="admin-press admin-press--primary" disabled={busy || saving}>
            {saving ? 'Guardando…' : 'Guardar cabina'}
          </button>
        </div>
      </form>
    </div>
  )
}
