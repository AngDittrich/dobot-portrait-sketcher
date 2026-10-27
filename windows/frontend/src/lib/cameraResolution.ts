/**
 * Resolución real de la cámara USB.
 *
 * El navegador ya pide 2560×1440 ideal, pero la cámara entrega lo que su
 * hardware permite (medido: 720×405). Este módulo decide UN solo reintento:
 * si el track anuncia más de lo que entrega (`getCapabilities`), se remonta
 * el stream pidiendo el máximo útil. Si el hardware ya está al tope, no se
 * insiste (pedir de más solo provoca error de constraints).
 */

/** Ancho mínimo útil: 1080p basta para dientes y líneas finas. */
export const TARGET_MIN_WIDTH = 1920

export interface CaptureSize {
  w: number
  h: number
}

/** Subconjunto de MediaTrackCapabilities que nos interesa. */
export interface WidthCaps {
  width?: { max?: number }
}

/**
 * Decide si vale pedir más resolución. Devuelve los constraints para
 * remontar el stream, o `null` si ya está bien o el hardware llegó al tope.
 */
export function decideStepUp(
  actual: CaptureSize,
  caps: WidthCaps | undefined,
): MediaTrackConstraints | null {
  if (actual.w >= TARGET_MIN_WIDTH) return null
  const max = caps?.width?.max ?? actual.w
  if (max <= actual.w) return null
  const want = Math.min(max, TARGET_MIN_WIDTH)
  if (want <= actual.w) return null
  return { width: { min: want }, facingMode: 'user' }
}

/** Lee la resolución efectiva del video vivo (0×0 si aún no hay frames). */
export function actualCaptureSize(video: {
  videoWidth: number
  videoHeight: number
}): CaptureSize {
  return { w: video.videoWidth | 0, h: video.videoHeight | 0 }
}
