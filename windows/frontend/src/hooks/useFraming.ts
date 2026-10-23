import { useEffect, useState } from 'react'
import type { RefObject } from 'react'
import type Webcam from 'react-webcam'

/**
 * Óvalo de la cara dentro del visor (0..1 del escenario).
 * La silueta dibujada usa los mismos números.
 */
export const GUIDE = {
  cx: 0.5,
  cy: 0.38,
  rx: 0.15,
  ry: 0.2,
} as const

export type FramingPose = 'ready' | 'off'

/**
 * Mira el video y dice si la cara está dentro de la silueta.
 * `ready` se sostiene unos instantes para no disparar la foto con un parpadeo.
 */
export function useFraming(webcamRef: RefObject<Webcam | null>, active: boolean): FramingPose | null {
  const [pose, setPose] = useState<FramingPose | null>(null)
  const [session, setSession] = useState(active)
  if (session !== active) {
    setSession(active)
    setPose(null)
  }

  useEffect(() => {
    if (!active) return

    let cancelled = false
    let streak = 0
    let current: FramingPose = 'off'
    let timer = 0
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d', { willReadFrequently: true })

    const tick = () => {
      if (cancelled) return
      const video = webcamRef.current?.video ?? null
      const good = video && context ? faceInGuide(video, canvas, context) : false
      streak = good ? (streak > 0 ? streak + 1 : 1) : streak < 0 ? streak - 1 : -1
      const next: FramingPose = streak >= 3 ? 'ready' : streak <= -3 ? 'off' : current
      if (next !== current) {
        current = next
        setPose(next)
      }
      timer = window.setTimeout(tick, 180)
    }

    timer = window.setTimeout(tick, 180)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [active, webcamRef])

  return pose
}

function faceInGuide(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  context: CanvasRenderingContext2D,
): boolean {
  const stageW = video.clientWidth
  const stageH = video.clientHeight
  const videoW = video.videoWidth
  const videoH = video.videoHeight
  if (!stageW || !stageH || !videoW || !videoH || video.readyState < 2) return false

  const sampleW = 96
  const sampleH = Math.max(1, Math.round((sampleW * videoH) / videoW))
  if (canvas.width !== sampleW || canvas.height !== sampleH) {
    canvas.width = sampleW
    canvas.height = sampleH
  }
  context.drawImage(video, 0, 0, sampleW, sampleH)
  const pixels = context.getImageData(0, 0, sampleW, sampleH).data

  // object-fit: cover — el óvalo está en el escenario, no en el cuadro crudo.
  const scale = Math.max(stageW / videoW, stageH / videoH)
  const offsetX = (videoW * scale - stageW) / 2
  const offsetY = (videoH * scale - stageH) / 2

  const cx = GUIDE.cx * stageW
  const cy = GUIDE.cy * stageH
  const rx = GUIDE.rx * stageW
  const ry = GUIDE.ry * stageH

  let inside = 0
  let skin = 0
  let skinX = 0
  let skinY = 0
  const steps = 16

  for (let iy = 0; iy < steps; iy += 1) {
    for (let ix = 0; ix < steps; ix += 1) {
      const sx = cx + ((ix + 0.5) / steps - 0.5) * 2 * rx
      const sy = cy + ((iy + 0.5) / steps - 0.5) * 2 * ry
      const nx = (sx - cx) / rx
      const ny = (sy - cy) / ry
      if (nx * nx + ny * ny > 1) continue
      inside += 1

      const vx = (sx + offsetX) / scale
      const vy = (sy + offsetY) / scale
      const px = Math.min(sampleW - 1, Math.max(0, Math.round((vx / videoW) * sampleW)))
      const py = Math.min(sampleH - 1, Math.max(0, Math.round((vy / videoH) * sampleH)))
      const index = (py * sampleW + px) * 4
      if (!isSkin(pixels[index], pixels[index + 1], pixels[index + 2])) continue
      skin += 1
      skinX += nx
      skinY += ny
    }
  }

  if (inside === 0 || skin < 8) return false
  const ratio = skin / inside
  const centerX = skinX / skin
  const centerY = skinY / skin
  const centered = centerX * centerX + centerY * centerY < 0.4
  return ratio >= 0.32 && ratio <= 0.97 && centered
}

/** Piel en YCbCr. Cubre tonos claros y oscuros sin contar la oficina gris. */
function isSkin(red: number, green: number, blue: number): boolean {
  const luma = 0.299 * red + 0.587 * green + 0.114 * blue
  const cb = 128 - 0.168736 * red - 0.331264 * green + 0.5 * blue
  const cr = 128 + 0.5 * red - 0.418688 * green - 0.081312 * blue
  return luma > 40 && cb > 77 && cb < 135 && cr > 130 && cr < 180
}
