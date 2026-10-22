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

/** Foto (data URL) -> boceto en el servidor. */
export async function postSketch(image: string): Promise<SketchResponse> {
  const data = await request<SketchResponse>('/api/sketch', {
    method: 'POST',
    body: JSON.stringify({ image }),
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
