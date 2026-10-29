import { useEffect, useMemo, useRef } from 'react'
import type { SketchStroke } from '../../lib/sketch'

/**
 * La hoja de papel donde se ve el retrato apareciendo trazo a trazo,
 * al ritmo del brazo.
 *
 * Los trazos llegan del backend en el mismo orden en que los dibuja el
 * robot (`order_strokes`), así que pintarlos por longitud acumulada es
 * una simulación fiel, no un efecto. Mientras el backend reporta progreso
 * cada segundo, aquí se interpola con requestAnimationFrame para que la
 * línea avance continua y nunca retroceda.
 *
 * Entre un trazo y el siguiente la pluma se levanta y viaja: eso se dibuja
 * como una línea punteada tenue con la punta en movimiento, para que se
 * entienda lo mismo que hace el brazo.
 */

interface SketchCanvasProps {
  strokes: SketchStroke[]
  /** 0..1 tal como lo reporta el robot. `null` = avance por tiempo. */
  progress: number | null
}

/** Tinta grafito de la cabina. */
const INK = '#1e293b'
/** Constante de suavizado: cuánto tarda la línea en alcanzar el reporte. */
const EASE_MS = 420
/** Segundos que tarda el dibujo simulado cuando no hay robot conectado. */
const IDLE_SECONDS = 14

interface Plan {
  lengths: number[]
  starts: number[]
  total: number
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export function SketchCanvas({ strokes, progress }: SketchCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const shownRef = useRef(0)
  const progressRef = useRef<number | null>(null)

  useEffect(() => {
    progressRef.current = progress
  }, [progress])

  /** Trazos con su longitud acumulada, medidos una sola vez. */
  const plan = useMemo<Plan>(() => {
    const lengths: number[] = []
    const starts: number[] = []
    let total = 0
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity

    for (let index = 0; index < strokes.length; index++) {
      const stroke = strokes[index]
      starts.push(total)
      let length = 0
      const points = stroke.points
      for (let i = 0; i < points.length; i++) {
        const [x, y] = points[i]
        if (x < minX) minX = x
        if (y < minY) minY = y
        if (x > maxX) maxX = x
        if (y > maxY) maxY = y
        if (i > 0) length += Math.hypot(x - points[i - 1][0], y - points[i - 1][1])
      }
      lengths.push(length)
      total += length
      // El backend también suma este viaje con el lápiz levantado al progreso
      // del trabajo. Incluirlo mantiene la animación y la punta de la pluma
      // al mismo ritmo que el MG400.
      const next = strokes[index + 1]?.points
      if (points.length > 0 && next && next.length > 0) {
        const end = points[points.length - 1]
        total += Math.hypot(next[0][0] - end[0], next[0][1] - end[1])
      }
    }

    if (!Number.isFinite(minX)) {
      minX = 0
      minY = 0
      maxX = 1
      maxY = 1
    }

    return { lengths, starts, total, minX, minY, maxX, maxY }
  }, [strokes])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || plan.total <= 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0
    let last = performance.now()
    const idleFrom = last
    let drawnInk = -1

    const paint = (revealed: number) => {
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      const boxW = plan.maxX - plan.minX || 1
      const boxH = plan.maxY - plan.minY || 1
      const pad = 16
      const scale = Math.min((width - pad * 2) / boxW, (height - pad * 2) / boxH)
      const offsetX = (width - boxW * scale) / 2 - plan.minX * scale
      const offsetY = (height - boxH * scale) / 2 - plan.minY * scale
      const place = (x: number, y: number): [number, number] => [x * scale + offsetX, y * scale + offsetY]

      ctx.strokeStyle = INK
      ctx.lineWidth = Math.max(1.6, 2.1 * scale * 0.35)
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'

      const goal = revealed * plan.total
      let nib: [number, number] | null = null
      let penDown = false

      for (let s = 0; s < strokes.length; s++) {
        const start = plan.starts[s]
        if (start > goal) break
        const points = strokes[s].points
        if (points.length < 2) continue
        const remaining = goal - start

        ctx.beginPath()
        ctx.moveTo(...place(points[0][0], points[0][1]))
        let walked = 0
        let cut = false
        for (let i = 1; i < points.length; i++) {
          const [x, y] = points[i]
          const [px, py] = points[i - 1]
          const step = Math.hypot(x - px, y - py)
          if (remaining <= walked + step) {
            // Último tramo: se corta justo donde va la pluma.
            const t = step > 0 ? (remaining - walked) / step : 0
            const cx = px + (x - px) * t
            const cy = py + (y - py) * t
            ctx.lineTo(...place(cx, cy))
            nib = place(cx, cy)
            penDown = true
            cut = true
            break
          }
          walked += step
          ctx.lineTo(...place(x, y))
        }
        ctx.stroke()

        if (cut) break
      }

      if (nib === null && goal < plan.total) {
        // En el hueco: la punta viaja del final de un trazo al inicio del otro.
        let gapFrom = 0
        let gapIndex = -1
        for (let s = 0; s < strokes.length - 1; s++) {
          const end = plan.starts[s] + plan.lengths[s]
          if (goal >= end && goal < plan.starts[s + 1]) {
            gapFrom = end
            gapIndex = s
            break
          }
        }
        if (gapIndex >= 0) {
          const from = strokes[gapIndex].points
          const to = strokes[gapIndex + 1].points
          if (from.length > 0 && to.length > 0) {
            const a = place(from[from.length - 1][0], from[from.length - 1][1])
            const b = place(to[0][0], to[0][1])
            const gap = plan.starts[gapIndex + 1] - gapFrom
            const t = gap > 0 ? Math.min(1, (goal - gapFrom) / gap) : 1

            ctx.save()
            ctx.setLineDash([3, 5])
            ctx.lineWidth = 1
            ctx.strokeStyle = 'rgba(30, 41, 59, 0.28)'
            ctx.beginPath()
            ctx.moveTo(a[0], a[1])
            ctx.lineTo(b[0], b[1])
            ctx.stroke()
            ctx.restore()

            nib = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            penDown = false
          }
        }
      }

      // Punta de la pluma: punto lleno cuando escribe, anillo tenue cuando vuela.
      if (nib && revealed < 1) {
        ctx.save()
        if (penDown) {
          ctx.shadowColor = 'rgba(30, 41, 59, 0.55)'
          ctx.shadowBlur = 10
          ctx.fillStyle = INK
          ctx.beginPath()
          ctx.arc(nib[0], nib[1], 2.2, 0, Math.PI * 2)
          ctx.fill()
        } else {
          ctx.strokeStyle = 'rgba(30, 41, 59, 0.4)'
          ctx.lineWidth = 1.2
          ctx.beginPath()
          ctx.arc(nib[0], nib[1], 2.6, 0, Math.PI * 2)
          ctx.stroke()
        }
        ctx.restore()
      }
    }

    const frame = (now: number) => {
      const dt = Math.min(120, now - last)
      last = now

      const reported = progressRef.current
      const target =
        reported === null
          ? // Sin robot conectado el dibujo se hace solo, a ritmo de demo.
            Math.min(1, (now - idleFrom) / (IDLE_SECONDS * 1000))
          : Math.min(1, Math.max(0, reported))

      const gap = target - shownRef.current
      if (gap > 0.0004) {
        const ease = 1 - Math.exp(-dt / EASE_MS)
        shownRef.current = Math.min(target, shownRef.current + gap * ease)
      } else if (gap < 0) {
        // El robot nunca desdibuja: si el reporte baja, se ignora.
        shownRef.current = Math.max(shownRef.current, 0)
      }

      if (Math.abs(shownRef.current - drawnInk) > 0.0003) {
        paint(shownRef.current)
        drawnInk = shownRef.current
      }
      raf = requestAnimationFrame(frame)
    }

    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [plan, strokes])

  return <canvas ref={canvasRef} className="booth-sheet-canvas" aria-hidden="true" />
}
