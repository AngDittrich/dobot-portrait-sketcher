/**
 * Motor de transformación a "sketch" (efecto dibujo a lápiz).
 *
 * El boceto de verdad lo genera el backend Python (`windows/backend`): la
 * foto viaja como data URL a `POST /api/sketch` y vuelve como dibujo de
 * líneas (el mismo que después lleva el robot al papel).
 *
 * `generateSketchLocal` conserva la versión de navegador (canvas) como
 * respaldo: si el backend no está levantado, la cabina sigue funcionando.
 */

import { postSketch } from './api'

/** Ancho máximo de trabajo: suficiente para pantalla y ágil para el blur. */
const MAX_WIDTH = 1024
/** Radio del desenfoque (px). A mayor radio, trazo más suave/limpió. */
const BLUR_RADIUS = 6

/* Tinta "grafito" y "papel" derivados de la paleta SYSCOM (slate). */
const GRAPHITE = { r: 30, g: 41, b: 59 } // --slate-800
const PAPER = { r: 250, g: 250, b: 249 }

/**
 * Boceto del backend. Si el backend no responde se cae al sketch local,
 * para que la demo siga viva sin el servidor levantado.
 */
export async function generateSketch(photoDataUrl: string): Promise<string> {
  try {
    const result = await postSketch(photoDataUrl)
    return result.image
  } catch (error) {
    console.warn('El backend no respondió; se usa el sketch local.', error)
    return generateSketchLocal(photoDataUrl)
  }
}

/** Versión 100 % local en el navegador (canvas). */
export async function generateSketchLocal(photoDataUrl: string): Promise<string> {
  const img = await loadImage(photoDataUrl)
  const { width, height } = fitWithin(img.naturalWidth, img.naturalHeight, MAX_WIDTH)

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Canvas 2D no disponible en este navegador')

  ctx.drawImage(img, 0, 0, width, height)
  const frame = ctx.getImageData(0, 0, width, height)

  const gray = toGrayscale(frame.data)
  const inverted = invertChannel(gray)
  const blurred = boxBlur(inverted, width, height, BLUR_RADIUS, 2)

  const out = ctx.createImageData(width, height)
  for (let i = 0; i < gray.length; i++) {
    const dodge = colorDodge(gray[i], blurred[i]) // 0..255
    const t = dodge / 255
    // Mapear negro→grafito, blanco→papel (mantiene el look lápiz con tinte de marca)
    out.data[i * 4] = GRAPHITE.r + (PAPER.r - GRAPHITE.r) * t
    out.data[i * 4 + 1] = GRAPHITE.g + (PAPER.g - GRAPHITE.g) * t
    out.data[i * 4 + 2] = GRAPHITE.b + (PAPER.b - GRAPHITE.b) * t
    out.data[i * 4 + 3] = 255
  }

  ctx.putImageData(out, 0, 0)
  return canvas.toDataURL('image/png')
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('No se pudo decodificar la foto capturada'))
    img.src = src
  })
}

function fitWithin(w: number, h: number, maxW: number) {
  if (w <= maxW) return { width: w, height: h }
  const scale = maxW / w
  return { width: maxW, height: Math.round(h * scale) }
}

/** Luminancia Rec. 601 → canal único. */
function toGrayscale(rgba: Uint8ClampedArray): Float32Array {
  const len = rgba.length / 4
  const gray = new Float32Array(len)
  for (let i = 0; i < len; i++) {
    gray[i] = rgba[i * 4] * 0.299 + rgba[i * 4 + 1] * 0.587 + rgba[i * 4 + 2] * 0.114
  }
  return gray
}

function invertChannel(channel: Float32Array): Float32Array {
  const out = new Float32Array(channel.length)
  for (let i = 0; i < channel.length; i++) out[i] = 255 - channel[i]
  return out
}

/** Color dodge clásico: base / (255 - blend). */
function colorDodge(base: number, blend: number): number {
  if (blend >= 255) return 255
  return Math.min(255, (base * 255) / (255 - blend))
}

/**
 * Box blur separable con ventana deslizante O(n) por pasada.
 * `passes` pasadas aproximan un gaussiano. Opera sobre canal único.
 */
function boxBlur(src: Float32Array, width: number, height: number, radius: number, passes: number): Float32Array {
  const current = Float32Array.from(src)
  const tmp = new Float32Array(current.length)

  for (let p = 0; p < passes; p++) {
    blurPassHorizontal(current, tmp, width, height, radius)
    blurPassVertical(tmp, current, width, height, radius)
  }
  return current
}

function blurPassHorizontal(src: Float32Array, dst: Float32Array, w: number, h: number, r: number) {
  const window = 2 * r + 1
  for (let y = 0; y < h; y++) {
    const row = y * w
    let acc = 0
    for (let x = -r; x <= r; x++) acc += src[row + clamp(x, 0, w - 1)]
    for (let x = 0; x < w; x++) {
      dst[row + x] = acc / window
      const exit = clamp(x - r, 0, w - 1)
      const enter = clamp(x + r + 1, 0, w - 1)
      acc += src[row + enter] - src[row + exit]
    }
  }
}

function blurPassVertical(src: Float32Array, dst: Float32Array, w: number, h: number, r: number) {
  const window = 2 * r + 1
  for (let x = 0; x < w; x++) {
    let acc = 0
    for (let y = -r; y <= r; y++) acc += src[clamp(y, 0, h - 1) * w + x]
    for (let y = 0; y < h; y++) {
      dst[y * w + x] = acc / window
      const exit = clamp(y - r, 0, h - 1)
      const enter = clamp(y + r + 1, 0, h - 1)
      acc += src[enter * w + x] - src[exit * w + x]
    }
  }
}

function clamp(v: number, min: number, max: number) {
  return v < min ? min : v > max ? max : v
}
