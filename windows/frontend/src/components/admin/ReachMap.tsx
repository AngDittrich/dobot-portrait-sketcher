import type { Calibration, CornerId, CornerPose } from '../../lib/api'

/**
 * El área del MG400 vista desde arriba: X del robot hacia arriba de la
 * pantalla, Y hacia la izquierda. Muestra hasta dónde llega el brazo, la hoja
 * enseñada, dónde cae el retrato y el lápiz en vivo.
 */

const REACH = 440
const INNER = 170
const J1 = 160

function screen(x: number, y: number): [number, number] {
  return [-y, -x]
}

function polygon(points: number[][]): string {
  return points.map(([x, y]) => screen(x, y).join(',')).join(' ')
}

function sector(radius: number): string {
  const steps = 64
  const points: string[] = ['0,0']
  for (let step = 0; step <= steps; step += 1) {
    const angle = ((-J1 + (2 * J1 * step) / steps) * Math.PI) / 180
    const [sx, sy] = screen(radius * Math.cos(angle), radius * Math.sin(angle))
    points.push(`${sx.toFixed(1)},${sy.toFixed(1)}`)
  }
  return `M ${points.join(' L ')} Z`
}

const LABELS: Record<CornerId, string> = { tl: 'SI', tr: 'SD', bl: 'II' }

export function ReachMap({
  calibration,
  corners,
  live,
}: {
  calibration: Calibration | null
  corners: Partial<Record<CornerId, CornerPose>>
  live: number[]
}) {
  const sheet = calibration
    ? [calibration.points.tl, calibration.points.tr, calibration.points.br, calibration.points.bl]
    : null

  return (
    <svg className="admin-map" viewBox="-470 -470 940 940" role="img" aria-label="Área de alcance del brazo vista desde arriba">
      <path d={sector(REACH)} className="admin-map-reach" />
      <circle cx={0} cy={0} r={INNER} className="admin-map-inner" />
      {[100, 200, 300, 400].map((radius) => (
        <circle key={radius} cx={0} cy={0} r={radius} className="admin-map-ring" />
      ))}
      <line x1={0} y1={0} x2={0} y2={-REACH} className="admin-map-axis" />
      <text x={6} y={-REACH + 18} className="admin-map-text">
        X
      </text>
      <text x={-REACH + 8} y={-8} className="admin-map-text">
        Y
      </text>
      {sheet && <polygon points={polygon(sheet)} className="admin-map-sheet" />}
      {calibration && <polygon points={polygon(calibration.draw_box)} className="admin-map-draw" />}
      {(Object.keys(LABELS) as CornerId[]).map((key) => {
        const corner = corners[key]
        if (!corner) return null
        const [sx, sy] = screen(corner.x, corner.y)
        return (
          <g key={key}>
            <circle cx={sx} cy={sy} r={9} className="admin-map-corner" />
            <text x={sx + 13} y={sy + 5} className="admin-map-label">
              {LABELS[key]}
            </text>
          </g>
        )
      })}
      <rect x={-34} y={-34} width={68} height={68} rx={12} className="admin-map-base" />
      <text x={0} y={60} textAnchor="middle" className="admin-map-text">
        base
      </text>
      {live.length >= 2 && (
        <circle
          cx={screen(live[0], live[1])[0]}
          cy={screen(live[0], live[1])[1]}
          r={11}
          className="admin-map-pen"
        />
      )}
    </svg>
  )
}
