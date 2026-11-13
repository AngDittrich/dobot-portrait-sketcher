import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  Cable,
  Gauge,
  PenLine,
  Ruler,
  Settings2,
  Spline,
  Unplug,
  Weight,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { AdminStatus } from '../../lib/api'
import type { AdminActions } from '../../hooks/useAdminActions'
import { settingsFrom, useBoothForm } from './boothDraft'

/**
 * Ajustes de la cabina y del movimiento. La hoja y las esquinas están en Calibración.
 */
export function ConfigSection({
  status,
  actions,
  speed,
  onSpeed,
}: {
  status: AdminStatus | null
  actions: AdminActions
  speed: number
  onSpeed: (value: number) => void
}) {
  const { booth, corners, brManual, patch } = useBoothForm(status)
  const [saving, setSaving] = useState(false)
  const [collision, setCollision] = useState(2)
  const [speedl, setSpeedl] = useState(50)
  const [accl, setAccl] = useState(50)
  const [weight, setWeight] = useState('0')
  const [inertia, setInertia] = useState('0')
  const speedRef = useRef(speed)
  const collisionRef = useRef(2)
  const speedlRef = useRef(50)
  const acclRef = useRef(50)
  useEffect(() => {
    speedRef.current = speed
  }, [speed])

  async function saveBooth() {
    if (!booth || saving) return
    setSaving(true)
    try {
      await actions.saveBooth(settingsFrom(booth, corners, brManual))
    } catch {
      // El aviso ya lo dejó el hook.
    } finally {
      setSaving(false)
    }
  }

  if (!booth) {
    return (
      <div className="admin-section">
        <p className="admin-empty">Leyendo la configuración…</p>
      </div>
    )
  }

  return (
    <div className="admin-section">
      <div className="admin-config">
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void saveBooth()
        }}
      >
        <section className="admin-card">
          <TileHead icon={Cable} title="Conexión" hint="A qué robot habla la cabina." />
          <div className="admin-fields">
            <Field icon={Settings2} label="Modo">
              <select value={booth.backend} onChange={(event) => patch('backend', event.target.value)}>
                <option value="mg400">Robot</option>
                <option value="mock">Simulador</option>
              </select>
            </Field>
            <Field icon={Cable} label="IP">
              <input value={booth.host} onChange={(event) => patch('host', event.target.value)} />
            </Field>
            <label className="admin-check">
              <input
                type="checkbox"
                checked={booth.dry_run}
                onChange={(event) => patch('dry_run', event.target.checked)}
              />
              <Unplug size={15} aria-hidden="true" />
              Sin mover (simula el dibujo)
            </label>
            <Field icon={Settings2} label="Usuario">
              <input inputMode="numeric" value={booth.user} onChange={(event) => patch('user', event.target.value)} />
            </Field>
            <Field icon={PenLine} label="Herramienta">
              <input inputMode="numeric" value={booth.tool} onChange={(event) => patch('tool', event.target.value)} />
            </Field>
          </div>
        </section>

        <section className="admin-card">
          <TileHead icon={PenLine} title="Dibujo" hint="Cómo baja el lápiz y qué tan suave es el trazo." />
          <div className="admin-fields">
            <Field icon={Ruler} label="Levantar lápiz (mm)">
              <input inputMode="decimal" value={booth.lift_mm} onChange={(event) => patch('lift_mm', event.target.value)} />
            </Field>
            <Field icon={Ruler} label="Margen (mm)">
              <input inputMode="decimal" value={booth.margin_mm} onChange={(event) => patch('margin_mm', event.target.value)} />
            </Field>
            <Field icon={Gauge} label="Velocidad del trazo">
              <input
                inputMode="decimal"
                value={booth.speed_factor}
                onChange={(event) => patch('speed_factor', event.target.value)}
              />
            </Field>
            <Field icon={Spline} label="Suavizado CP (0–100)">
              <input inputMode="decimal" value={booth.cp_draw} onChange={(event) => patch('cp_draw', event.target.value)} />
            </Field>
          </div>
        </section>

        <div className="admin-config-save">
          <button type="submit" className="admin-press admin-press--primary" disabled={saving}>
            {saving ? 'Guardando…' : 'Guardar configuración'}
          </button>
        </div>
      </form>

        <section className="admin-card">
          <TileHead icon={Gauge} title="Movimiento" hint="Se aplican al robot al soltar la barra. No hace falta guardar." />
          <div className="admin-sliders">
            <Slider
              icon={Gauge}
              label="Velocidad del jog"
              value={speed}
              min={1}
              max={100}
              onChange={(value) => {
                speedRef.current = value
                onSpeed(value)
              }}
              onCommit={() => void actions.send({ action: 'speed', value: speedRef.current })}
            />
            <Slider
              icon={Spline}
              label="Velocidad lineal"
              value={speedl}
              min={1}
              max={100}
              onChange={(value) => {
                speedlRef.current = value
                setSpeedl(value)
              }}
              onCommit={() => void actions.send({ action: 'speedl', value: speedlRef.current })}
            />
            <Slider
              icon={Zap}
              label="Aceleración"
              value={accl}
              min={1}
              max={100}
              onChange={(value) => {
                acclRef.current = value
                setAccl(value)
              }}
              onCommit={() => void actions.send({ action: 'accl', value: acclRef.current })}
            />
            <Slider
              icon={Zap}
              label="Choque"
              value={collision}
              min={0}
              max={5}
              suffix=""
              onChange={(value) => {
                collisionRef.current = value
                setCollision(value)
              }}
              onCommit={() => void actions.send({ action: 'collision', value: collisionRef.current })}
            />
          </div>
        </section>

        <section className="admin-card">
          <TileHead icon={Weight} title="Carga de la herramienta" hint="Peso e inercia que el controlador usa para el lápiz." />
          <div className="admin-fields">
            <Field icon={Weight} label="Peso kg (0–5)">
              <input inputMode="decimal" value={weight} onChange={(event) => setWeight(event.target.value)} />
            </Field>
            <Field icon={Gauge} label="Inercia (0–1)">
              <input inputMode="decimal" value={inertia} onChange={(event) => setInertia(event.target.value)} />
            </Field>
          </div>
          <div className="admin-tile-actions">
            <button
              type="button"
              className="admin-press"
              onClick={() => {
                const w = Number(weight)
                const inertiaValue = Number(inertia)
                if (Number.isFinite(w) && Number.isFinite(inertiaValue)) {
                  void actions.send({ action: 'payload', weight: w, inertia: inertiaValue })
                }
              }}
            >
              <Weight size={16} aria-hidden="true" />
              Fijar carga
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}

function TileHead({ icon: Icon, title, hint }: { icon: LucideIcon; title: string; hint: string }) {
  return (
    <header className="admin-tile-head">
      <span className="admin-tile-icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{hint}</p>
      </div>
    </header>
  )
}

function Field({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: ReactNode }) {
  return (
    <label>
      <span className="admin-field-name">
        <Icon size={14} aria-hidden="true" />
        {label}
      </span>
      {children}
    </label>
  )
}

function Slider({
  icon: Icon,
  label,
  value,
  min,
  max,
  suffix = '%',
  onChange,
  onCommit,
}: {
  icon: LucideIcon
  label: string
  value: number
  min: number
  max: number
  suffix?: string
  onChange: (value: number) => void
  onCommit: () => void
}) {
  return (
    <label>
      <span className="admin-field-name">
        <Icon size={14} aria-hidden="true" />
        {label}
      </span>
      <strong>
        {value}
        {suffix}
      </strong>
      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        onPointerUp={onCommit}
        onBlur={onCommit}
      />
    </label>
  )
}
