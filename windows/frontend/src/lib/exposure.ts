/**
 * Calibración de exposición de la cámara USB.
 *
 * Las captures del quiosco traen 3-4.5% de blanco clipado (luma ≥ 250):
 * la luz del techo quema la coronilla y XDoG pierde el contorno de la
 * cabeza (el blanco quemado no tiene bordes). Como el clipado no tiene
 * datos, el único arreglo real es bajar la exposición EN LA CÁMARA
 * antes de capturar. Se intenta una sola vez, en silencio; si el
 * hardware no expone el control, no pasa nada.
 */

/** Luma a partir de la cual el píxel cuenta como quemado. */
export const CLIPPED_LUMA = 250

/** Fracción de píxeles quemados tolerada antes de intervenir. */
export const CLIP_RATIO_LIMIT = 0.01

/** Tamaño de la muestra (basta para medir luz, sobra para detalle). */
export const SAMPLE_W = 64
export const SAMPLE_H = 36

/** Subconjunto de MediaTrackCapabilities que nos interesa. */
export interface ExposureCaps {
  exposureCompensation?: { min?: number; max?: number; step?: number }
}

/**
 * Fracción de píxeles quemados en un buffer RGBA (0-1). Puro, testeable
 * sin DOM.
 */
export function clippedRatioFromRgba(data: Uint8ClampedArray | number[]): number {
  const n = Math.floor(data.length / 4)
  if (n === 0) return 0
  let clipped = 0
  for (let i = 0; i < n; i++) {
    const r = data[i * 4]
    const g = data[i * 4 + 1]
    const b = data[i * 4 + 2]
    if (0.299 * r + 0.587 * g + 0.114 * b >= CLIPPED_LUMA) clipped++
  }
  return clipped / n
}

/**
 * Decide el nuevo exposureCompensation (valor absoluto para
 * applyConstraints) o `null` si no hay que tocar nada: poca quema,
 * hardware sin soporte, o ya estamos al mínimo.
 */
export function decideExposureCut(
  ratio: number,
  caps: ExposureCaps | undefined,
  current: number,
): number | null {
  if (!Number.isFinite(ratio) || ratio <= CLIP_RATIO_LIMIT) return null
  const range = caps?.exposureCompensation
  if (!range) return null
  const step = range.step && range.step > 0 ? range.step : 1
  const min = range.min ?? -3
  const base = Number.isFinite(current) ? current : 0
  const next = base - step
  if (next < min) return null
  return next
}

/** Lee la fracción quemada del frame vivo. `null` si aún no hay frames. */
export function sampleClippedRatio(video: HTMLVideoElement): number | null {
  if (!video.videoWidth) return null
  const canvas = document.createElement('canvas')
  canvas.width = SAMPLE_W
  canvas.height = SAMPLE_H
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  if (!ctx) return null
  ctx.drawImage(video, 0, 0, SAMPLE_W, SAMPLE_H)
  return clippedRatioFromRgba(ctx.getImageData(0, 0, SAMPLE_W, SAMPLE_H).data)
}

/**
 * Calibra una vez: muestrea luz y baja un paso la compensación si hace
 * falta. Nunca lanza (el quiosco no se puede trabar por esto).
 */
export async function calibrateExposure(
  video: HTMLVideoElement,
  track: MediaStreamTrack,
): Promise<boolean> {
  try {
    const ratio = sampleClippedRatio(video)
    if (ratio === null) return false
    const caps = (
      track.getCapabilities as (() => ExposureCaps) | undefined
    )?.call(track)
    const settings = (
      track.getSettings as (() => { exposureCompensation?: number }) | undefined
    )?.call(track)
    const next = decideExposureCut(ratio, caps, settings?.exposureCompensation ?? 0)
    if (next === null) return false
    await track.applyConstraints({
      advanced: [{ exposureCompensation: next } as MediaTrackConstraintSet],
    })
    return true
  } catch {
    return false
  }
}
