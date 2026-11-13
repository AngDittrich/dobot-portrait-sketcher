import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Loader2 } from 'lucide-react'
import {
  adminArea,
  adminCalibration,
  adminCommand,
  adminGoto,
  adminPose,
  adminTestDraw,
  saveAdminBooth,
} from '../../lib/api'
import type { AdminSheet, AdminStatus, Calibration, CornerId, CornerPose, Corners, SpotId } from '../../lib/api'
import { ReachMap } from './ReachMap'

/**
 * Calibración de la cabina. Se mueve la punta aquí mismo, se toman o se
 * escriben las esquinas y el rectángulo se endereza solo. La inferior derecha
 * se puede dejar calculada o medirla a mano.
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
  j4: string
}

type Xyz = { x: string; y: string; z: string }
type CornerKey = CornerId | 'br'

const REACH_WIDTH_MM = 440
const REACH_DEPTH_MM = 240
const STEPS = [0.1, 1, 5, 10]
const STEP_SPEED = 20
const AXES = ['Y+', 'X-', 'X+', 'Y-', 'Z+', 'Z-', 'J4+', 'J4-'] as const

const CORNER_INFO: { id: CornerKey; label: string; hint: string }[] = [
  { id: 'tl', label: 'Superior izquierda', hint: 'Donde empieza el dibujo, mirando la hoja de frente.' },
  { id: 'tr', label: 'Superior derecha', hint: 'El otro extremo del borde de arriba.' },
  { id: 'bl', label: 'Inferior izquierda', hint: 'Bajando por el borde izquierdo.' },
  {
    id: 'br',
    label: 'Inferior derecha',
    hint: 'Se calcula para que la hoja quede a escuadra. También puedes tomarla o escribirla.',
  },
]

function SheetPicker({
  papers,
  selectedId,
  onSelect,
  onMark,
  marking,
  markDisabled,
}: {
  papers: AdminSheet[]
  selectedId: string
  onSelect: (id: string) => void
  onMark: () => void
  marking: boolean
  markDisabled: boolean
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
        title="Centra el tamaño estándar en las esquinas. Si la hoja medida es otra, este marco no cae sobre el papel."
        onClick={onMark}
      >
        {marking ? 'Marcando…' : `Marcar el marco de ${selected.label}`}
      </button>
      <p className="admin-sheet-caption">
        Centra {selected.label} en las esquinas. Si lo medido es otro tamaño, el marco queda corrido respecto al papel.
      </p>
    </div>
  )
}

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
    j4: text(frame.j4, '-50'),
  }
}

function num(value: number): string {
  return String(Math.round(value * 1000) / 1000)
}

function xyzOf(pose: CornerPose): Xyz {
  return { x: num(pose.x), y: num(pose.y), z: num(pose.z) }
}

function readXyz(draft: Xyz, r: number): CornerPose | null {
  if ([draft.x, draft.y, draft.z].some((part) => part.trim() === '')) return null
  const x = Number(draft.x)
  const y = Number(draft.y)
  const z = Number(draft.z)
  if (![x, y, z].every((value) => Number.isFinite(value))) return null
  return { x, y, z, r }
}

function emptyXyz(): Xyz {
  return { x: '', y: '', z: '' }
}

let draft: { booth: BoothForm; corners: Partial<Corners>; brManual: boolean } | null = null

function taught(corners: Partial<Corners>): corners is Corners {
  return Boolean(corners.tl && corners.tr && corners.bl)
}

function sheetOf(corners: Partial<Corners>, brManual: boolean): Corners | null {
  if (!taught(corners)) return null
  return brManual && corners.br ? corners : { tl: corners.tl, tr: corners.tr, bl: corners.bl }
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
  const [drafts, setDrafts] = useState<Partial<Record<CornerKey, Xyz>>>(() => {
    const seeded: Partial<Record<CornerKey, Xyz>> = {}
    for (const key of ['tl', 'tr', 'bl', 'br'] as const) {
      const pose = draft?.corners[key]
      if (pose) seeded[key] = xyzOf(pose)
    }
    return seeded
  })
  const [brManual, setBrManual] = useState(() => draft?.brManual ?? false)
  const [preview, setPreview] = useState<{ key: string; calibration: Calibration | null; error: string }>({
    key: '',
    calibration: null,
    error: '',
  })
  const [saving, setSaving] = useState(false)
  const [marking, setMarking] = useState(false)
  const [testing, setTesting] = useState(false)
  const [tracing, setTracing] = useState(false)
  const [moving, setMoving] = useState('')
  const [stepping, setStepping] = useState(false)
  const [step, setStep] = useState(1)
  const sentJ4 = useRef<number | null>(null)
  const busy = Boolean(status?.busy)
  const live = status?.pose ?? []
  const liveJ4 = status?.angles?.[3]
  const papers = status?.sheets ?? []
  const robot = booth?.backend === 'mg400'

  const seed = status?.frame
  if (booth === null && seed?.backend) {
    const next = formFrom(seed)
    setBooth(next)
    if (seed.corners) {
      setCorners(seed.corners)
      setBrManual(Boolean(seed.corners.br))
      setDrafts(() => {
        const seeded: Partial<Record<CornerKey, Xyz>> = {}
        for (const key of ['tl', 'tr', 'bl', 'br'] as const) {
          const pose = seed.corners?.[key]
          if (pose) seeded[key] = xyzOf(pose)
        }
        return seeded
      })
    }
  }

  useEffect(() => {
    draft = booth ? { booth, corners, brManual } : null
  }, [booth, corners, brManual])

  const sheet = sheetOf(corners, brManual)
  const margin = Number(booth?.margin_mm ?? 8)
  const previewKey = sheet ? JSON.stringify([sheet, margin]) : ''

  useEffect(() => {
    if (!previewKey || !sheet) return
    let stop = false
    const timer = window.setTimeout(() => {
      adminCalibration(token, sheet, Number.isFinite(margin) ? margin : 8)
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
    // sheet y margin ya van dentro de previewKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey, token])

  const previewReady = preview.key === previewKey
  const calibration = sheet ? preview.calibration : null
  const problems = previewReady ? (calibration?.errors ?? []) : []
  const shapeError = previewReady ? preview.error : ''

  function patch<K extends keyof BoothForm>(key: K, value: BoothForm[K]) {
    setBooth((state) => state && { ...state, [key]: value })
  }

  function j4Number(): number | undefined {
    const value = Number(booth?.j4)
    return Number.isFinite(value) ? value : undefined
  }

  async function holdJ4() {
    const value = j4Number()
    if (value === undefined || !robot) return
    const known = sentJ4.current ?? status?.j4_fixed
    if (typeof known === 'number' && Math.abs(known - value) < 0.05) return
    await adminCommand(token, { action: 'j4home', j4: value })
    sentJ4.current = value
  }

  function writeCorner(id: CornerKey, next: Xyz, r: number) {
    if (id === 'br') setBrManual(true)
    setDrafts((state) => ({ ...state, [id]: next }))
    const pose = readXyz(next, r)
    if (!pose) return
    setCorners((state) => ({ ...state, [id]: pose }))
  }

  function editCorner(id: CornerKey, axis: keyof Xyz, value: string) {
    const current =
      drafts[id] ?? (corners[id] ? xyzOf(corners[id]) : id === 'br' ? brCalculated() : emptyXyz())
    const previous = corners[id]
    writeCorner(id, { ...current, [axis]: value }, previous?.r ?? 0)
  }

  function brCalculated(): Xyz {
    const point = calibration?.points.br
    if (!point) return emptyXyz()
    return { x: num(point[0]), y: num(point[1]), z: num(point[2]) }
  }

  function fieldsOf(id: CornerKey): Xyz {
    if (id === 'br' && !brManual) return brCalculated()
    return drafts[id] ?? emptyXyz()
  }

  async function teach(id: CornerKey) {
    if (!robot || busy) return
    try {
      const pose = await adminPose(token)
      writeCorner(id, xyzOf(pose), pose.r)
      onNotice(`${CORNER_INFO.find((item) => item.id === id)?.label} tomada. Falta Guardar cabina.`)
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo leer la pose')
    }
  }

  async function takeJ4() {
    if (!robot || busy) return
    try {
      const pose = await adminPose(token)
      const value = num(pose.j4)
      patch('j4', value)
      await adminCommand(token, { action: 'j4home', j4: pose.j4 })
      sentJ4.current = pose.j4
      onNotice(`J4 de la hoja en ${value}.`)
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo leer J4')
    }
  }

  async function nudge(axis: (typeof AXES)[number]) {
    if (!robot || busy || stepping) return
    setStepping(true)
    try {
      if (axis.startsWith('J4')) {
        const current = j4Number() ?? -50
        const next = Math.round((current + (axis.endsWith('+') ? step : -step)) * 1000) / 1000
        patch('j4', String(next))
        await adminCommand(token, { action: 'j4home', j4: next })
        sentJ4.current = next
      } else {
        await holdJ4()
        await adminCommand(token, { action: 'step', axis, mm: step, speed: STEP_SPEED })
      }
      onNotice('')
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'el brazo no pudo dar el paso')
    } finally {
      setStepping(false)
    }
  }

  function clearBr() {
    setBrManual(false)
    setDrafts((state) => {
      const rest = { ...state }
      delete rest.br
      return rest
    })
    setCorners((state) => {
      const rest = { ...state }
      delete rest.br
      return rest
    })
  }

  async function go(target: SpotId) {
    if (moving || busy || !robot) return
    const lift = Number(booth?.lift_mm ?? 8)
    setMoving(target)
    try {
      await holdJ4()
      const ready = sheetOf(corners, brManual)
      if (ready) {
        await adminGoto(token, { corner: target, corners: ready }, lift, j4Number())
      } else {
        const point = target === 'center' ? undefined : corners[target]
        if (!point) throw new Error('escribe esa esquina primero')
        await adminGoto(token, { point }, lift, j4Number())
      }
      onNotice('')
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'el brazo no pudo ir a ese punto')
    } finally {
      setMoving('')
    }
  }

  async function markSheet() {
    if (!booth || marking || saving) return
    setMarking(true)
    try {
      await holdJ4()
      const area = await adminArea(token, {
        sheet: booth.sheet,
        corners: sheet ?? undefined,
        lift_mm: Number(booth.lift_mm),
        j4: j4Number(),
      })
      onNotice(
        `Marco de ${area.label}: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm, centrado en las esquinas, con el lápiz arriba.`,
      )
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo marcar el marco')
    } finally {
      setMarking(false)
    }
  }

  async function tracePerimeter() {
    if (!booth || tracing || busy || saving) return
    setTracing(true)
    try {
      await holdJ4()
      const area = await adminArea(token, {
        corners: sheet ?? undefined,
        lift_mm: Number(booth.lift_mm),
        j4: j4Number(),
      })
      onNotice(
        `Perímetro de las esquinas de esta pantalla: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm, con el lápiz arriba.`,
      )
    } catch (error) {
      onNotice(error instanceof Error ? error.message : 'no se pudo recorrer el perímetro')
    } finally {
      setTracing(false)
    }
  }

  async function drawTest() {
    if (!booth || testing || saving || busy) return
    setTesting(true)
    try {
      await holdJ4()
      await adminTestDraw(token, {
        corners: sheet ?? undefined,
        lift_mm: Number(booth.lift_mm),
        margin_mm: Number(booth.margin_mm),
        j4: j4Number(),
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
        corners: sheet,
        lift_mm: Number(booth.lift_mm),
        margin_mm: Number(booth.margin_mm),
        sheet: booth.sheet,
        j4: j4Number(),
      })
      if (j4Number() !== undefined) sentJ4.current = j4Number() ?? null
      onNotice('Cabina guardada. El siguiente dibujo usa esta hoja.')
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

  const blocked = robot && (!sheet || Boolean(shapeError) || problems.length > 0)
  const armBusy = busy || stepping || Boolean(moving)

  return (
    <div className="admin-section">
      <form
        className="admin-config"
        onSubmit={(event) => {
          event.preventDefault()
          void saveBooth()
        }}
      >
        <section className="admin-card admin-card--wide">
          <div className="admin-card-head">
            <h3>Mover la punta</h3>
            <span className="admin-card-hint">X hacia arriba del mapa, Y a la izquierda, Z arriba</span>
          </div>
          <div className="admin-live">
            <span className="admin-live-label">En el robot</span>
            {live.length >= 3 ? (
              <Coords values={[live[0], live[1], live[2]]} j4={liveJ4} />
            ) : (
              <span className="admin-card-hint">Sin pose todavía</span>
            )}
          </div>
          <div className="admin-j4-field">
            <label>
              J4 de la hoja
              <input
                inputMode="decimal"
                value={booth.j4}
                disabled={!robot}
                onChange={(event) => patch('j4', event.target.value)}
                onBlur={() => void holdJ4().catch((error: unknown) => onNotice(error instanceof Error ? error.message : 'no se pudo poner J4'))}
              />
            </label>
            <button type="button" className="admin-press" disabled={!robot || armBusy} onClick={() => void takeJ4()}>
              Tomar J4
            </button>
          </div>
          <p className="admin-card-note">
            Un solo ángulo para toda la hoja. Si cada esquina llevara otra muñeca, la punta se correría.
          </p>
          <div className="admin-nudge">
            <div className="admin-nudge-size">
              <span>Un paso</span>
              <div className="admin-segment" role="group" aria-label="Tamaño del paso">
                {STEPS.map((size) => (
                  <button key={size} type="button" className={step === size ? 'is-on' : ''} onClick={() => setStep(size)}>
                    {size}
                  </button>
                ))}
              </div>
            </div>
            <div className="admin-nudge-axes" role="group" aria-label="Pasos en X, Y, Z y J4">
              {AXES.map((axis) => (
                <button key={axis} type="button" className="admin-press" disabled={!robot || armBusy} onClick={() => void nudge(axis)}>
                  {axis}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="admin-card admin-card--wide">
          <div className="admin-card-head">
            <h3>Esquinas de la hoja</h3>
            <span className="admin-card-hint">La punta tiene que tocar el papel al tomar cada esquina</span>
          </div>
          <div className="admin-corners">
            {CORNER_INFO.map((item) => {
              const fields = fieldsOf(item.id)
              const set = item.id === 'br' ? brManual || Boolean(calibration) : Boolean(corners[item.id])
              const residual = calibration?.residuals_mm?.[item.id] ?? 0
              return (
                <div key={item.id} className={`admin-corner is-${item.id}${set ? ' is-set' : ''}`}>
                  <div className="admin-corner-info">
                    <span className="admin-corner-glyph" aria-hidden="true" />
                    <strong>
                      {item.label}
                      {item.id === 'br' ? (
                        <em className="admin-corner-badge">{brManual ? 'A mano' : 'Calculada'}</em>
                      ) : null}
                    </strong>
                    {item.id !== 'br' || brManual || calibration ? (
                      <div className="admin-xyz">
                        {(['x', 'y', 'z'] as const).map((axis) => (
                          <label key={axis}>
                            {axis.toUpperCase()}
                            <input
                              inputMode="decimal"
                              value={fields[axis]}
                              aria-label={`${axis.toUpperCase()} de ${item.label}`}
                              onChange={(event) => editCorner(item.id, axis, event.target.value)}
                            />
                          </label>
                        ))}
                      </div>
                    ) : (
                      <p>{item.hint}</p>
                    )}
                    {item.id !== 'br' && residual > 0.3 ? (
                      <p>El rectángulo la mueve {residual.toFixed(1)} mm. Ir aquí va al rectángulo.</p>
                    ) : item.id === 'br' && !brManual && calibration ? (
                      <p>
                        {calibration.straighten_deg > 0.05
                          ? `Enderezada ${calibration.straighten_deg.toFixed(1)}°. `
                          : ''}
                        Ir aquí va a este punto.
                      </p>
                    ) : item.id !== 'br' && !corners[item.id] ? (
                      <p>{item.hint}</p>
                    ) : null}
                    {item.id === 'br' && brManual ? (
                      <button type="button" className="admin-text-btn" onClick={clearBr}>
                        Calcular de nuevo
                      </button>
                    ) : null}
                  </div>
                  <div className="admin-corner-actions">
                    <button
                      type="button"
                      className="admin-press"
                      disabled={!robot || armBusy}
                      onClick={() => void teach(item.id)}
                    >
                      Tomar posición
                    </button>
                    <button
                      type="button"
                      className="admin-press"
                      disabled={armBusy || (item.id === 'br' ? !sheet : !corners[item.id] && !sheet)}
                      onClick={() => void go(item.id)}
                    >
                      {moving === item.id ? <Loader2 size={16} className="admin-spin" aria-hidden="true" /> : 'Ir aquí'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        <section className="admin-card admin-card--wide admin-calib">
          <div className="admin-calib-map">
            <ReachMap calibration={calibration} corners={corners} live={live} />
          </div>
          <div className="admin-calib-side">
            <h3>Comprobar</h3>
            {calibration ? (
              <>
                <p className="admin-calib-size">
                  {Math.round(calibration.width_mm)} × {Math.round(calibration.height_mm)} mm
                  <span>
                    {calibration.orientation}
                    {calibration.paper ? `, ${calibration.paper.matches ? 'es' : 'parece'} ${calibration.paper.label}` : ''}
                    {calibration.straighten_deg > 0.05 ? `, enderezada ${calibration.straighten_deg.toFixed(1)}°` : ''}
                  </span>
                </p>
                <p className="admin-card-note">
                  El retrato ocupa {Math.round(calibration.draw_width_mm)} × {Math.round(calibration.draw_height_mm)} mm,
                  centrado y con {booth.margin_mm} mm de aire. En el mapa es el rectángulo claro.
                  {calibration.shift_mm > 0.5 && !calibration.manual_br
                    ? ' El punto hueco es lo que tomaste; el lleno es el rectángulo.'
                    : ''}
                </p>
              </>
            ) : (
              <p className="admin-card-note">
                {sheet ? 'Calculando la hoja…' : 'Toma o escribe tres esquinas para ver la hoja.'}
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
              <button type="button" className="admin-press" disabled={!sheet || armBusy} onClick={() => void go('center')}>
                {moving === 'center' ? 'Yendo…' : 'Ir al centro'}
              </button>
              <button
                type="button"
                className="admin-press"
                disabled={armBusy || saving || marking || !sheet}
                title="Recorre las cuatro esquinas que se ven aquí, con el lápiz arriba."
                onClick={() => void tracePerimeter()}
              >
                {tracing ? 'Recorriendo…' : 'Recorrer el perímetro'}
              </button>
              <button
                type="button"
                className="admin-press"
                disabled={armBusy || saving || testing || marking || !sheet}
                title="Escribe SYSCOM en el centro de la hoja, con el lápiz abajo."
                onClick={() => void drawTest()}
              >
                {testing || busy ? 'Dibujando…' : 'Dibujar prueba'}
              </button>
            </div>
          </div>
        </section>

        <div className="admin-config-save">
          {blocked && <span className="admin-card-hint">{sheet ? 'Corrige la hoja para guardar' : 'Faltan esquinas por enseñar'}</span>}
          <button type="submit" className="admin-press admin-press--primary" disabled={busy || saving || blocked}>
            {saving ? 'Guardando…' : 'Guardar cabina'}
          </button>
        </div>

        <details className="admin-card admin-card--wide admin-more">
          <summary>Más opciones</summary>
          <div className="admin-more-body">
            {papers.length > 0 && (
              <SheetPicker
                papers={papers}
                selectedId={booth.sheet}
                onSelect={(id) => patch('sheet', id)}
                onMark={() => void markSheet()}
                marking={marking}
                markDisabled={busy || saving || !sheet || !robot}
              />
            )}
            {calibration?.paper && booth.sheet !== calibration.paper.id ? (
              <p className="admin-note">
                Lo medido {calibration.paper.matches ? 'es' : 'parece'} {calibration.paper.label}. Las esquinas mandan en el tamaño.
              </p>
            ) : null}
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
              <label>
                Usuario
                <input inputMode="numeric" value={booth.user} onChange={(event) => patch('user', event.target.value)} />
              </label>
              <label>
                Herramienta
                <input inputMode="numeric" value={booth.tool} onChange={(event) => patch('tool', event.target.value)} />
              </label>
            </div>
          </div>
        </details>
      </form>
    </div>
  )
}

function Coords({ values, j4 }: { values: number[]; j4?: number }) {
  const cells = [
    ['X', values[0]],
    ['Y', values[1]],
    ['Z', values[2]],
    ['J4', j4],
  ] as const
  return (
    <div className="admin-coords">
      {cells.map(([label, value]) => (
        <span key={label} className={`admin-coord admin-coord--${label === 'J4' ? 'r' : label.toLowerCase()}`}>
          <b>{label}</b>
          {typeof value === 'number' ? value.toFixed(2) : '—'}
        </span>
      ))}
    </div>
  )
}
