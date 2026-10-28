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
  frame?: Record<string, number | string | boolean | null>
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
  z_draw: number
  z_travel: number
  r: number
  r_far: number
  far_x: number
  far_y: number
  speed_factor: number
  origin_x: number
  origin_y: number
  x_sign: number
  y_sign: number
  cp_draw: number
}

export function saveAdminBooth(token: string, booth: BoothSettings): Promise<BoothSettings> {
  return request<BoothSettings>('/api/admin/settings', {
    method: 'POST',
    headers: adminHeaders(token),
    body: JSON.stringify(booth),
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
