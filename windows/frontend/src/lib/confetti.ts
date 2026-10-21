/**
 * Confetti ligero en canvas — paleta SYSCOM (azules de marca + slates + verde éxito).
 * Sin dependencias: física mínima (gravedad + rotación + arrastre).
 */

export const CONFETTI_COLORS = ['#1a3a6b', '#2a5494', '#d4e0ed', '#ffffff', '#9db8dc', '#94a3b8']

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  color: string
  rotation: number
  spin: number
  shape: 'rect' | 'circle'
  life: number
  ttl: number
}

const GRAVITY = 0.16
const DRAG = 0.992
const DURATION_MS = 2200

/**
 * Lanza una ráfaga de confetti desde el centro-inferior del canvas.
 * Devuelve una función para cancelar la animación (cleanup de efectos).
 */
export function fireConfetti(canvas: HTMLCanvasElement, count = 140): () => void {
  const ctx = canvas.getContext('2d')
  if (!ctx) return () => {}

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const { clientWidth: w, clientHeight: h } = canvas
  canvas.width = w * dpr
  canvas.height = h * dpr
  ctx.scale(dpr, dpr)

  const originX = w / 2
  const originY = h * 0.62

  const particles: Particle[] = Array.from({ length: count }, () => {
    const angle = -Math.PI / 2 + (Math.random() - 0.5) * (Math.PI / 1.6)
    const speed = 9 + Math.random() * 9
    return {
      x: originX,
      y: originY,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      size: 5 + Math.random() * 6,
      color: CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)],
      rotation: Math.random() * Math.PI * 2,
      spin: (Math.random() - 0.5) * 0.3,
      shape: Math.random() > 0.35 ? 'rect' : 'circle',
      life: 0,
      ttl: 90 + Math.random() * 50,
    }
  })

  let raf = 0
  const startedAt = performance.now()

  const tick = () => {
    const elapsed = performance.now() - startedAt
    ctx.clearRect(0, 0, w, h)

    let alive = false
    for (const p of particles) {
      p.life += 1
      if (p.life > p.ttl || p.y > h + 30) continue
      alive = true

      p.vx *= DRAG
      p.vy = p.vy * DRAG + GRAVITY
      p.x += p.vx
      p.y += p.vy
      p.rotation += p.spin

      const fade = 1 - p.life / p.ttl
      ctx.save()
      ctx.globalAlpha = Math.max(0, fade)
      ctx.translate(p.x, p.y)
      ctx.rotate(p.rotation)
      ctx.fillStyle = p.color
      if (p.shape === 'rect') {
        ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2)
      } else {
        ctx.beginPath()
        ctx.arc(0, 0, p.size / 2.6, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.restore()
    }

    if (alive && elapsed < DURATION_MS) {
      raf = requestAnimationFrame(tick)
    } else {
      ctx.clearRect(0, 0, w, h)
    }
  }

  raf = requestAnimationFrame(tick)
  return () => cancelAnimationFrame(raf)
}
