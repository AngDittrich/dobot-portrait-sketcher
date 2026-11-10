interface Trace {
  d: string
  /** Punto fijo de la traza donde se quedó la mecha. */
  at: number
  /** Más de una mecha sobre la misma traza, como un bus con varias motos. */
  dense?: boolean
}

const TRACES: Trace[] = [
  { d: 'M0 246h164l74 74v204l72 72h208', at: 118 },
  { d: 'M238 320h120', at: 64, dense: true },
  { d: 'M0 640h96l58-58v-96', at: 712 },
  { d: 'M1440 150h-190l-64 64v96l-58 58h-90', at: 286 },
  { d: 'M1186 278h-128l-46 46v72', at: 548, dense: true },
  { d: 'M1440 742h-160l-56 56v102', at: 834 },
  { d: 'M540 900v-120l52-52h150l46-46v-76', at: 372 },
  { d: 'M636 0v76l44 44h190l52 52v92', at: 604 },
  { d: 'M1180 0v58l-40 40h-96', at: 906, dense: true },
  { d: 'M0 900v-58l62-62h140', at: 218 },
  { d: 'M900 0v40l-36 36h-120', at: 748 },
  { d: 'M1440 400h-90l-40 40v60', at: 452, dense: true },
]

const NODES = [
  [164, 246],
  [238, 320],
  [358, 320],
  [154, 486],
  [518, 596],
  [1250, 150],
  [1186, 214],
  [636, 76],
  [1140, 98],
  [1224, 798],
]

/** Estela: tramos alineados detrás de la cabeza, cada uno más tenue. */
const TAILS = [
  { len: 190, className: 'is-far' },
  { len: 112, className: 'is-mid' },
  { len: 46, className: 'is-near' },
]

interface StreakProps {
  d: string
  at: number
  tone: string
}

/**
 * Una mecha quieta: cabeza cuadrada encendida y una estela larga que se apaga
 * hacia atrás. No se anima: la línea se lee como si el pulso ya hubiera pasado.
 */
function Streak({ d, at, tone }: StreakProps) {
  const offset = (start: number) => (1000 - (start % 1000) + 1000) % 1000

  return (
    <g className="circuit-streak">
      {TAILS.map((tail) => (
        <path
          key={tail.className}
          d={d}
          pathLength={1000}
          className={`circuit-tail ${tail.className} ${tone}`}
          style={{
            strokeDasharray: `${tail.len} ${1000 - tail.len}`,
            strokeDashoffset: offset(at - tail.len),
          }}
        />
      ))}
      <path
        d={d}
        pathLength={1000}
        className={`circuit-head ${tone}`}
        style={{
          strokeDasharray: '1.5 998.5',
          strokeDashoffset: offset(at),
        }}
      />
    </g>
  )
}

/**
 * Trazas de circuito en el fondo del home: retícula fuerte, nodos cuadrados y
 * mechas azules largas que se apagan. Puramente decorativo — no recibe puntero
 * ni entra al árbol de lectura.
 */
export function CircuitBackdrop() {
  return (
    <div className="circuit-backdrop" aria-hidden="true">
      <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" fill="none">
        <defs>
          <pattern id="circuit-grid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M48 0H0V48" className="circuit-grid-line" />
          </pattern>
        </defs>

        <rect width="1440" height="900" fill="url(#circuit-grid)" />
        <g className="circuit-grid-major">
          {[240, 480, 720, 960, 1200].map((x) => (
            <path key={`v-${x}`} d={`M${x} 0V900`} />
          ))}
          {[180, 360, 540, 720].map((y) => (
            <path key={`h-${y}`} d={`M0 ${y}H1440`} />
          ))}
        </g>

        <g className="circuit-base">
          {TRACES.map((trace) => (
            <path key={`base-${trace.d}`} d={trace.d} />
          ))}
          {NODES.map(([x, y]) => (
            <rect key={`node-${x}-${y}`} x={x - 3.5} y={y - 3.5} width="7" height="7" />
          ))}
        </g>

        <g className="circuit-live">
          {TRACES.map((trace, index) => {
            const tone = index % 3 === 0 ? 'is-blue' : 'is-celeste'
            return (
              <g key={trace.d}>
                <Streak d={trace.d} at={trace.at} tone={tone} />
                {trace.dense && (
                  <Streak d={trace.d} at={(trace.at + 500) % 1000} tone={tone} />
                )}
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
