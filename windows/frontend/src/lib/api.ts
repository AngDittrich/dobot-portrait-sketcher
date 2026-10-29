/**
 * Cliente del backend Python (FastAPI) que vive en `windows/backend`.
 *
 * En desarrollo el proxy de Vite manda `/api` al backend local, así que
 * basta con dejar `VITE_API_BASE` vacío. Para apuntar a otra máquina
 * (por ejemplo el PC que tiene el robot) se define `VITE_API_BASE=http://IP:8000`.
 */

/** Base del backend. Vacío = mismo origen (proxy de Vite en desarrollo). */
export const API_BASE = (import.meta.env.VITE_API_BASE ?? '').trim().replace(/\/$/, '')

export interface SketchResponse {
  /** Identificador del boceto (para mandarlo después al robot). */
  id: string
  /** Vista previa del boceto (data URL PNG). */
  image: string
  /** El mismo dibujo en SVG. */
  svg: string
  /** Trazos en píxeles del recorte. */
  strokes: { points: [number, number][] }[]
  /** Métricas: nº de trazos, longitud en mm, tiempo estimado... */
  stats: Record<string, number | string | boolean>
}

export interface JobResponse {
  job_id: string
  sketch_id: string
  status: string
  est_seconds: number
}

export interface JobStatus {
  job_id: string
  status: 'queued' | 'drawing' | 'done' | 'error'
  progress: number
  eta_seconds: number
  error: string | null
}

/** Último boceto generado: lo usa el hook para mandarlo al robot. */
let lastSketchId: string | null = null

export function getLastSketchId(): string | null {
  return lastSketchId
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(`Backend ${response.status}${detail ? `: ${detail.slice(0, 200)}` : ''}`)
  }
  return (await response.json()) as T
}

/** Foto (data URL) y rasgos elegidos -> boceto en el servidor. */
export async function postSketch(
  image: string,
  traits: string[] = [],
  style = 'caricatura',
): Promise<SketchResponse> {
  const data = await request<SketchResponse>('/api/sketch', {
    method: 'POST',
    body: JSON.stringify({ image, traits, style }),
  })
  lastSketchId = data.id
  return data
}

/** Boceto aprobado -> trabajo de dibujo del robot. */
export async function postJob(sketchId?: string | null): Promise<JobResponse> {
  return request<JobResponse>('/api/jobs', {
    method: 'POST',
    body: JSON.stringify({ sketch_id: sketchId ?? lastSketchId }),
  })
}

/** Progreso del trabajo de dibujo. */
export async function getJob(jobId: string): Promise<JobStatus> {
  return request<JobStatus>(`/api/jobs/${jobId}`)
}

export interface AdminStatus {
  backend: string
  busy: boolean
  connected: boolean
  detail?: string
  mode?: number | null
  mode_label?: string
  pose?: number[]
  angles?: number[]
  alarms?: string
  alarm_text?: string
  frame?: Partial<BoothSettings>
  calibration?: Calibration | null
  sheets?: AdminSheet[]
}

export interface AdminSheet {
  id: string
  label: string
  short_mm: number
  long_mm: number
}

/** Pose enseñada de una esquina de la hoja, en coordenadas del robot. */
export interface CornerPose {
  x: number
  y: number
  z: number
  r: number
}

export type CornerId = 'tl' | 'tr' | 'bl'
export type SpotId = CornerId | 'br' | 'center'
export type Corners = Record<CornerId, CornerPose>

/** Lo que el servidor calcula de unas esquinas: medida, retrato y avisos. */
export interface Calibration {
  width_mm: number
  height_mm: number
  orientation: 'horizontal' | 'vertical'
  angle_deg: number
  paper: { id: string; label: string; diff_mm: number; matches: boolean } | null
  draw_width_mm: number
  draw_height_mm: number
  /** [x, y, z, r] de las esquinas y el centro. */
  points: Record<SpotId, number[]>
  /** Cuatro esquinas [x, y] de donde cae el retrato. */
  draw_box: number[][]
  errors: string[]
  warnings: string[]
}

export interface AdminCommand {
  action: string
  axis?: string
  mm?: number
  value?: number
  on?: boolean
  index?: number
  x?: number
  y?: number
  z?: number
  r?: number
  speed?: number
}

function adminHeaders(token: string): HeadersInit {
  return { 'X-Admin-Token': token }
}

/** PIN de 4 dígitos → token para el resto del panel. */
export async function unlockAdmin(pin: string): Promise<string> {
  const data = await request<{ token: string }>('/api/admin/unlock', {
    method: 'POST',
    body: JSON.stringify({ pin }),
  })
  return data.token
}

export function adminStatus(token: string): Promise<AdminStatus> {
  return request<AdminStatus>('/api/admin/status', { headers: adminHeaders(token) })
}

export interface BoothSettings {
  backend: string
  host: string
  dry_run: boolean
  user: number
  tool: number
  speed_factor: number
  cp_draw: number
  corners: Corners | null
  lift_mm: number
  margin_mm: number
}

export function saveAdminBooth(token: string, booth: BoothSettings): Promise<BoothSettings> {
  return request<BoothSettings>('/api/admin/settings', {
    method: 'POST',
    headers: adminHeaders(token),
    body: JSON.stringify(booth),
  })
}

/** Recorre el borde de la hoja enseñada con el lápiz arriba. */
export function adminArea(token: string): Promise<{ width_mm: number; height_mm: number }> {
  return request('/api/admin/area', { method: 'POST', headers: adminHeaders(token) })
}

/** Medida y avisos de unas esquinas todavía sin guardar. */
export function adminCalibration(
  token: string,
  corners: Corners,
  marginMm: number,
): Promise<Calibration> {
  return request<Calibration>('/api/admin/calibration', {
    method: 'POST',
    headers: adminHeaders(token),
    body: JSON.stringify({ corners, margin_mm: marginMm }),
  })
}

/**
 * Lleva el brazo con el lápiz arriba a una esquina o al centro de la hoja
 * (`corners` completas) o a una esquina suelta (`point`) antes de tener las tres.
 */
export function adminGoto(
  token: string,
  target: { corner: SpotId; corners: Corners } | { point: CornerPose },
  liftMm: number,
): Promise<{ x: number; y: number; z: number; r: number }> {
  return request('/api/admin/goto', {
    method: 'POST',
    headers: adminHeaders(token),
    body: JSON.stringify({ ...target, lift_mm: liftMm }),
  })
}

export function adminCommand(
  token: string,
  command: AdminCommand,
): Promise<{ command: string; code: number; value: string }> {
  return request('/api/admin/command', {
    method: 'POST',
    headers: adminHeaders(token),
    body: JSON.stringify(command),
  })
}

export interface AdminActivityJob {
  job_id: string
  sketch_id: string
  status: 'queued' | 'drawing' | 'done' | 'error'
  progress: number
  error: string | null
  /** Segundos Unix; `finished_at` es null mientras sigue dibujando. */
  created_at: number
  finished_at: number | null
}

export interface AdminActivity {
  jobs: AdminActivityJob[]
  totals: { done: number; error: number }
  provider: {
    configured: string
    model: string
    fallback_model: string
    available: Record<string, boolean>
  }
}

/** Dibujos recientes, contadores y proveedor de IA (sección Actividad). */
export function adminActivity(token: string): Promise<AdminActivity> {
  return request<AdminActivity>('/api/admin/activity', { headers: adminHeaders(token) })
}

/** Las `<img>` no mandan headers: el token viaja en la query para la miniatura. */
export function adminSketchPreviewUrl(sketchId: string, token: string): string {
  return `${API_BASE}/api/admin/sketches/${encodeURIComponent(sketchId)}/preview?token=${encodeURIComponent(token)}`
}
