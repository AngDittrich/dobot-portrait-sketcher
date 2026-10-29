import { useEffect, useState, type CSSProperties } from 'react'
import { adminArea, adminCalibration, adminGoto, adminTestDraw, saveAdminBooth } from '../../lib/api'
import type { AdminSheet, AdminStatus, Calibration, CornerId, CornerPose, Corners, SpotId } from '../../lib/api'
import { ReachMap } from './ReachMap'

/**
 * Calibración de la cabina como asistente: se enseñan tres esquinas de la
 * hoja con el lápiz tocando el papel, se revisan en el mapa y se guardan en
 * `data/robot.json`. El retrato se ajusta solo a esa hoja.
 */

type BoothForm = {
  backend: string
  host: string
  dry_run: boolean
  user: string
  tool: string
  speed_factor: string
  cp_draw: string
  lift_mm: string
  margin_mm: string
  sheet: string
}

/** Caja medida del brazo: 440 mm a lo ancho y 240 de fondo. Igual que sheet.py. */
const REACH_WIDTH_MM = 440
const REACH_DEPTH_MM = 240

function SheetPicker({
  papers,
  selectedId,
  onSelect,
  onMark,
  marking,
  markDisabled,
  needsCorners,
}: {
  papers: AdminSheet[]
  selectedId: string
  onSelect: (id: string) => void
  onMark: () => void
  marking: boolean
  markDisabled: boolean
  needsCorners: boolean
}) {
  const selected = papers.find((paper) => paper.id === selectedId) ?? papers[0]
  return (
    <div className="admin-sheet-picker">
      <div className="admin-sheet-stage">
        <div
          className="admin-sheet-page"
          style={{
            width: `${(selected.width_mm / REACH_WIDTH_MM) * 100}%`,
            height: `${(selected.height_mm / REACH_DEPTH_MM) * 100}%`,
          }}
        >
          <span
            className="admin-sheet-draw"
            style={{
              width: `${(selected.draw_width_mm / selected.width_mm) * 100}%`,
              height: `${(selected.draw_height_mm / selected.height_mm) * 100}%`,
            }}
          />
        </div>
      </div>
      <p className="admin-sheet-caption">
        Alcance {REACH_WIDTH_MM}×{REACH_DEPTH_MM} mm · {selected.label} a escala · retrato{' '}
        {Math.round(selected.draw_width_mm)}×{Math.round(selected.draw_height_mm)} mm
      </p>
      <div className="admin-sheet-row" role="group" aria-label="Tamaño de hoja">
        {papers.map((paper) => (
          <button
            key={paper.id}
            type="button"
            className="admin-sheet-pick"
            aria-pressed={paper.id === selected.id}
            disabled={!paper.fits}
            title={paper.reason || `${paper.width_mm} × ${paper.height_mm} mm, lado largo a lo ancho`}
            onClick={() => onSelect(paper.id)}
            style={{ '--w': paper.width_mm, '--h': paper.height_mm } as CSSProperties}
          >
            <span className="admin-sheet-pick-page" />
            <span className="admin-sheet-pick-name">{paper.label}</span>
          </button>
        ))}
      </div>
      <button
        type="button"
        className="admin-press admin-sheet-mark"
        disabled={markDisabled || marking}
        title="Recorre con el lápiz arriba el rectángulo de esta hoja, centrado en las esquinas que enseñaste."
        onClick={onMark}
      >
        {marking ? 'Marcando…' : `Marcar el marco de ${selected.label}`}
      </button>
      {needsCorners ? (
        <p className="admin-sheet-caption">Enseña las tres esquinas: el marco se centra en esa hoja.</p>
      ) : null}
    </div>
  )
}

const CORNER_INFO: { id: CornerId; label: string; hint: string }[] = [
  { id: 'tl', label: 'Superior izquierda', hint: 'Donde empieza el dibujo: arriba a la izquierda, mirando la hoja de frente.' },
  { id: 'tr', label: 'Superior derecha', hint: 'Sobre el mismo borde de arriba, del otro lado.' },
  { id: 'bl', label: 'Inferior izquierda', hint: 'Bajando por el borde izquierdo.' },
]

function text(value: unknown, fallback: string): string {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function formFrom(frame: NonNullable<AdminStatus['frame']>): BoothForm {
  return {
    backend: text(frame.backend, 'mg400'),
    host: text(frame.host, ''),
    dry_run: frame.dry_run === true,
    user: text(frame.user, '0'),
    tool: text(frame.tool, '0'),
    speed_factor: text(frame.speed_factor, '20'),
    cp_draw: text(frame.cp_draw, '0'),
    lift_mm: text(frame.lift_mm, '8'),
    margin_mm: text(frame.margin_mm, '8'),
    sheet: text(frame.sheet, 'a5'),
  }
}

// Borrador sin guardar. Para mover el brazo hay que ir a Control y volver:
// sin esto, cambiar de sección borraba las esquinas recién enseñadas.
let draft: { booth: BoothForm; corners: Partial<Corners> } | null = null

function complete(corners: Partial<Corners>): corners is Corners {
  return Boolean(corners.tl && corners.tr && corners.bl)
}

function mm(value: number): string {
  return value.toFixed(1)
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
  const [booth, setBooth] = useState<BoothForm | null>(() => draft?.booth ?? null)
  const [corners, setCorners] = useState<Partial<Corners>>(() => draft?.corners ?? {})
  const [preview, setPreview] = useState<{ key: string; calibration: Calibration | null; error: string }>({
    key: '',
    calibration: null,
    error: '',
  })
  const [saving, setSaving] = useState(false)
  const [marking, setMarking] = useState(false)
  const [testing, setTesting] = useState(false)
  const [moving, setMoving] = useState<string>('')
  const busy = Boolean(status?.busy)
  const live = status?.pose ?? []
  const papers = status?.sheets ?? []
  const hasPose = live.length >= 4

  // Se siembra una sola vez con lo guardado: el sondeo de 800 ms no pisa lo que se edita.
  const seed = status?.frame
  if (booth === null && seed?.backend) {
    setBooth(formFrom(seed))
    if (seed.corners) setCorners(seed.corners)
  }

  useEffect(() => {
    draft = booth ? { booth, corners } : null
  }, [booth, corners])

  const ready = complete(corners)
  const margin = Number(booth?.margin_mm ?? 8)
  const previewKey = ready ? JSON.stringify([corners, margin]) : ''

  useEffect(() => {
    if (!previewKey || !complete(corners)) return
    let stop = false
    const timer = window.setTimeout(() => {
      adminCalibration(token, corners, Number.isFinite(margin) ? margin : 8)
        .then((calibration) => {
          if (!stop) setPreview({ key: previewKey, calibration, error: '' })
        })
        .catch((error: unknown) => {
          if (!stop) {
            setPreview({
              key: previewKey,
              calibration: null,
              error: error instanceof Error ? error.message : 'las esquinas no forman una hoja',
            })
          }
        })
    }, 250)
    return () => {
      stop = true
      window.clearTimeout(timer)
    }
    // corners y margin ya van dentro de previewKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey, token])

  const current = preview.key === previewKey ? preview : { calibration: null, error: '' }
  const calibration = current.calibration
  const problems = calibration?.errors ?? []
  const shapeError = current.error

  function patch<K extends keyof BoothForm>(key: K, value: BoothForm[K]) {
    setBooth((state) => state && { ...state, [key]: value })
  }

  function teach(id: CornerId) {
    if (!hasPose) return
    const pose: CornerPose = { x: live[0], y: live[1], z: live[2], r: live[3] }
    setCorners((state) => ({ ...state, [id]: pose }))
    onNotice(`Esquina ${CORNER_INFO.find((item) => item.id === id)?.label.toLowerCase()} guardada. Falta Guardar cabina.`)
  }

  async function go(target: SpotId) {
    if (moving || busy) return
    const lift = Number(booth?.lift_mm ?? 8)
    setMoving(target)
    try {
      if (complete(corners)) {
        await adminGoto(token, { corner: target, corners }, lift)
      } else {
        const point = target === 'tl' || target === 'tr' || target === 'bl' ? corners[target] : undefined
        if (!point) throw new Error('enseña esa esquina primero')
        await adminGoto(token, { point }, lift)
      }
      onNotice('')
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'el brazo no pudo ir a ese punto')
    } finally {
      setMoving('')
    }
  }

  async function markArea() {
    if (saving || marking) return
    setSaving(true)
    try {
      const area = await adminArea(token)
      onNotice(`Área recorrida: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm con el lápiz arriba.`)
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo marcar el área')
    } finally {
      setSaving(false)
    }
  }

  async function markSheet() {
    if (!booth || marking || saving) return
    setMarking(true)
    try {
      const area = await adminArea(token, {
        sheet: booth.sheet,
        corners: complete(corners) ? corners : undefined,
        lift_mm: Number(booth.lift_mm),
      })
      onNotice(
        `Marco de ${area.label}: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm, con el lápiz arriba.`,
      )
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo marcar el marco')
    } finally {
      setMarking(false)
    }
  }

  async function drawTest() {
    if (!booth || testing || saving || busy) return
    setTesting(true)
    try {
      await adminTestDraw(token, {
        corners: complete(corners) ? corners : undefined,
        lift_mm: Number(booth.lift_mm),
        margin_mm: Number(booth.margin_mm),
      })
      onNotice('Dibujando SYSCOM en el centro de la hoja.')
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo dibujar la prueba')
    } finally {
      setTesting(false)
    }
  }

  async function saveBooth() {
    if (!booth || saving) return
    setSaving(true)
    try {
      await saveAdminBooth(token, {
        backend: booth.backend,
        host: booth.host.trim(),
        dry_run: booth.dry_run,
        user: Number(booth.user),
        tool: Number(booth.tool),
        speed_factor: Number(booth.speed_factor),
        cp_draw: Number(booth.cp_draw),
        corners: complete(corners) ? corners : null,
        lift_mm: Number(booth.lift_mm),
        margin_mm: Number(booth.margin_mm),
        sheet: booth.sheet,
      })
      onNotice('Cabina guardada. El siguiente dibujo usa esta hoja.')
      draft = null
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

  const isRobot = booth.backend === 'mg400'
  const blocked = isRobot && (!ready || Boolean(shapeError) || problems.length > 0)
  const taught = CORNER_INFO.filter((item) => corners[item.id]).length

  return (
    <div className="admin-section">
      <form
        className="admin-config"
        onSubmit={(event) => {
          event.preventDefault()
          void saveBooth()
        }}
      >
        <section className="admin-card admin-card--wide admin-calib">
          <div className="admin-calib-map">
            <ReachMap calibration={calibration} corners={corners} live={live} />
          </div>
          <div className="admin-calib-side">
            <h3>Hoja</h3>
            {calibration ? (
              <>
                <p className="admin-calib-size">
                  {Math.round(calibration.width_mm)} × {Math.round(calibration.height_mm)} mm
                  <span>
                    {calibration.orientation}
                    {calibration.paper ? `, ${calibration.paper.matches ? 'es' : 'parece'} ${calibration.paper.label}` : ''}
                  </span>
                </p>
                <p className="admin-card-note">
                  El retrato ocupa {Math.round(calibration.draw_width_mm)} × {Math.round(calibration.draw_height_mm)} mm,
                  centrado y con {booth.margin_mm} mm de aire al borde. En el mapa es el rectángulo claro dentro de la hoja.
                </p>
              </>
            ) : (
              <p className="admin-card-note">
                {taught === 0
                  ? 'Mueve el brazo desde Control hasta que la punta toque una esquina de la hoja y pulsa Guardar pose en esa esquina.'
                  : `Llevas ${taught} de 3 esquinas.`}
              </p>
            )}
            {shapeError && <p className="admin-alert">{shapeError}</p>}
            {problems.map((problem) => (
              <p key={problem} className="admin-alert">
                {problem}
              </p>
            ))}
            {calibration?.warnings.map((warning) => (
              <p key={warning} className="admin-note">
                {warning}
              </p>
            ))}
            <div className="admin-card-actions">
              <button type="button" className="admin-press" disabled={!ready || busy || Boolean(moving)} onClick={() => void go('center')}>
                {moving === 'center' ? 'Yendo…' : 'Ir al centro'}
              </button>
              <button
                type="button"
                className="admin-press"
                disabled={busy || saving || marking || !status?.calibration}
                title={status?.calibration ? '' : 'guarda las esquinas primero'}
                onClick={() => void markArea()}
              >
                Recorrer el borde guardado
              </button>
            </div>
            {papers.length > 0 && (
              <SheetPicker
                papers={papers}
                selectedId={booth.sheet}
                onSelect={(id) => patch('sheet', id)}
                onMark={() => void markSheet()}
                marking={marking}
                markDisabled={busy || saving || (!ready && !status?.calibration) || booth.backend !== 'mg400'}
                needsCorners={!ready && !status?.calibration}
              />
            )}
            {calibration?.paper && booth.sheet !== calibration.paper.id ? (
              <p className="admin-note">
                Lo medido {calibration.paper.matches ? 'es' : 'parece'} {calibration.paper.label} y elegiste{' '}
                {papers.find((paper) => paper.id === booth.sheet)?.label ?? booth.sheet}. Las esquinas mandan en el tamaño.
              </p>
            ) : null}
          </div>
        </section>

        <section className="admin-card admin-card--wide">
          <div className="admin-card-head">
            <h3>Esquinas de la hoja</h3>
            <span className="admin-card-hint">El lápiz debe tocar el papel al guardar cada pose</span>
          </div>
          <div className="admin-corners">
            {CORNER_INFO.map((item) => {
              const pose = corners[item.id]
              return (
                <div key={item.id} className={`admin-corner is-${item.id}${pose ? ' is-set' : ''}`}>
                  <span className="admin-corner-glyph" aria-hidden="true" />
                  <strong>{item.label}</strong>
                  <p>{pose ? `X ${mm(pose.x)}  Y ${mm(pose.y)}  Z ${mm(pose.z)}  R ${mm(pose.r)}` : item.hint}</p>
                  <div className="admin-corner-actions">
                    <button type="button" className="admin-press" disabled={!hasPose || busy} onClick={() => teach(item.id)}>
                      Guardar pose
                    </button>
                    <button
                      type="button"
                      className="admin-press"
                      disabled={!pose || busy || Boolean(moving)}
                      onClick={() => void go(item.id)}
                    >
                      {moving === item.id ? 'Yendo…' : 'Ir aquí'}
                    </button>
                  </div>
                </div>
              )
            })}
            <div className={`admin-corner is-br${ready ? ' is-set' : ''}`}>
              <span className="admin-corner-glyph" aria-hidden="true" />
              <strong>Inferior derecha</strong>
              <p>
                {calibration
                  ? `Calculada: X ${mm(calibration.points.br[0])}  Y ${mm(calibration.points.br[1])}  Z ${mm(calibration.points.br[2])}  R ${mm(calibration.points.br[3])}`
                  : 'Se calcula con las otras tres.'}
              </p>
              <div className="admin-corner-actions">
                <button type="button" className="admin-press" disabled={!ready || busy || Boolean(moving)} onClick={() => void go('br')}>
                  {moving === 'br' ? 'Yendo…' : 'Ir aquí'}
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="admin-card">
          <h3>Dibujo</h3>
          <div className="admin-fields">
            <label>
              Levantar lápiz (mm)
              <input inputMode="decimal" value={booth.lift_mm} onChange={(event) => patch('lift_mm', event.target.value)} />
            </label>
            <label>
              Margen al borde (mm)
              <input inputMode="decimal" value={booth.margin_mm} onChange={(event) => patch('margin_mm', event.target.value)} />
            </label>
            <label>
              Velocidad (1–100)
              <input inputMode="decimal" value={booth.speed_factor} onChange={(event) => patch('speed_factor', event.target.value)} />
            </label>
            <label>
              Suavizado CP (0–100)
              <input inputMode="decimal" value={booth.cp_draw} onChange={(event) => patch('cp_draw', event.target.value)} />
            </label>
          </div>
        </section>

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
              <input type="checkbox" checked={booth.dry_run} onChange={(event) => patch('dry_run', event.target.checked)} />
              Sin mover (simula el dibujo)
            </label>
          </div>
          <details className="admin-advanced">
            <summary>Avanzado</summary>
            <div className="admin-fields">
              <label>
                Usuario
                <input inputMode="numeric" value={booth.user} onChange={(event) => patch('user', event.target.value)} />
              </label>
              <label>
                Herramienta
                <input inputMode="numeric" value={booth.tool} onChange={(event) => patch('tool', event.target.value)} />
              </label>
            </div>
          </details>
        </section>

        <div className="admin-config-save">
          {blocked && <span className="admin-card-hint">{ready ? 'Corrige la hoja para guardar' : 'Faltan esquinas por enseñar'}</span>}
          <button
            type="button"
            className="admin-press"
            disabled={busy || saving || testing || marking || (!ready && !status?.calibration) || booth.backend !== 'mg400'}
            title="Escribe SYSCOM en el centro de la hoja enseñada, con el lápiz abajo."
            onClick={() => void drawTest()}
          >
            {testing || busy ? 'Dibujando…' : 'Dibujar prueba'}
          </button>
          <button type="submit" className="admin-press admin-press--primary" disabled={busy || saving || blocked}>
            {saving ? 'Guardando…' : 'Guardar cabina'}
          </button>
        </div>
      </form>
    </div>
  )
}
