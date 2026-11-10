interface Trace {
  d: string
  /** Segundos que tarda el segmento en recorrer la traza completa. */
  duration: number
  /** Desfase inicial: así no arrancan todas a la vez. */
  delay: number
  /** Más de un segmento por traza, como un bus con varias motos. */
  dense?: boolean
}

const TRACES: Trace[] = [
  { d: 'M0 246h164l74 74v204l72 72h208', duration: 11, delay: -2 },
  { d: 'M238 320h120', duration: 6.5, delay: -4.5, dense: true },
  { d: 'M0 640h96l58-58v-96', duration: 9, delay: -7.5 },
  { d: 'M1440 150h-190l-64 64v96l-58 58h-90', duration: 12.5, delay: -3 },
  { d: 'M1186 278h-128l-46 46v72', duration: 7.5, delay: -6, dense: true },
  { d: 'M1440 742h-160l-56 56v102', duration: 10, delay: -9.5 },
  { d: 'M540 900v-120l52-52h150l46-46v-76', duration: 13.5, delay: -1.5 },
  { d: 'M636 0v76l44 44h190l52 52v92', duration: 8.5, delay: -8 },
  { d: 'M1180 0v58l-40 40h-96', duration: 6, delay: -2.8, dense: true },
  { d: 'M0 900v-58l62-62h140', duration: 11.5, delay: -5.5 },
  { d: 'M900 0v40l-36 36h-120', duration: 9.5, delay: -11 },
  { d: 'M1440 400h-90l-40 40v60', duration: 7, delay: -13, dense: true },
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

/** Estela: tramos que se alinean detrás de la cabeza, cada uno más tenue. */
const TAILS = [
  { len: 86, className: 'circuit-tail is-far' },
  { len: 46, className: 'circuit-tail is-mid' },
  { len: 20, className: 'circuit-tail is-near' },
]

interface CometProps {
  d: string
  duration: number
  delay: number
  tone: string
}

/** Una moto de luz: cabeza cuadrada a opacity plena y estela que se apaga. */
function Comet({ d, duration, delay, tone }: CometProps) {
  // La longitud del trazo se retrasa lo justo para quedar detrás de la cabeza.
  const lag = (len: number) => delay + (len * duration) / 1000

  return (
    <>
      {TAILS.map((tail) => (
        <path
          key={tail.className}
          d={d}
          pathLength={1000}
          className={`${tail.className} ${tone}`}
          style={{
            animationDuration: `${duration}s`,
            animationDelay: `${lag(tail.len)}s`,
            strokeDasharray: `${tail.len} ${1000 - tail.len}`,
          }}
        />
      ))}
      <path
        d={d}
        pathLength={1000}
        className={`circuit-head ${tone}`}
        style={{
          animationDuration: `${duration}s`,
          animationDelay: `${lag(0)}s`,
          strokeDasharray: '0.01 999.99',
        }}
      />
    </>
  )
}

/**
 * Trazas de circuito en el fondo del home: la base queda quieta y una
 * cabeza de luz recorre cada traza con su estela desvaneciéndose.
 * Puramente decorativo — no recibe puntero ni entra al árbol de lectura.
 */
export function CircuitBackdrop() {
  return (
    <div className="circuit-backdrop" aria-hidden="true">
      <svg viewBox="0 0 1440 900" preserveAspectRatio="xMidYMid slice" fill="none">
        <g className="circuit-base">
          {TRACES.map((trace) => (
            <path key={`base-${trace.d}`} d={trace.d} />
          ))}
          {NODES.map(([x, y]) => (
            <rect key={`node-${x}-${y}`} x={x - 3} y={y - 3} width="6" height="6" />
          ))}
        </g>

        <g className="circuit-live">
          {TRACES.map((trace, index) => {
            const tone = index % 3 === 0 ? 'is-blue' : 'is-celeste'
            return (
              <g key={trace.d} className="circuit-spark">
                <Comet d={trace.d} duration={trace.duration} delay={trace.delay} tone={tone} />
                {trace.dense && (
                  <Comet
                    d={trace.d}
                    duration={trace.duration}
                    delay={trace.delay - trace.duration / 2}
                    tone={tone}
                  />
                )}
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
