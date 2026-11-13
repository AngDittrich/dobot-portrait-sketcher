import { GUIDE } from '../../hooks/useFraming'
import type { FramingPose } from '../../hooks/useFraming'

/* Cuadro de la cámara (4:3). El SVG se proyecta sobre el visor con el mismo
   recorte que el video, así el óvalo conserva su forma en cualquier visor. */
const FRAME_W = 1333
const FRAME_H = 1000

/**
 * Figura de encuadre (cabeza y hombros), dibujada en coordenadas del cuadro
 * 4:3 de la cámara: el SVG se adapta al visor con el mismo recorte que el
 * video, así el óvalo no se estira cuando el visor es vertical. El color
 * es el estado: verde si la cara está dentro, rojo si no. Sin etiquetas.
 */
export function FramingGuide({ pose }: { pose: FramingPose }) {
  const cx = GUIDE.cx * FRAME_W
  const cy = GUIDE.cy * FRAME_H
  const rx = GUIDE.rx * FRAME_W
  const ry = GUIDE.ry * FRAME_H
  const neckW = rx * 0.34
  const neckTop = cy + ry * 0.72
  const neckBottom = cy + ry * 1.12
  const shoulderTop = neckBottom + ry * 0.26
  const bottom = cy + ry * 2.7
  const shoulderW = rx * 2.05

  const head = `M ${cx} ${cy - ry}
    C ${cx + rx} ${cy - ry} ${cx + rx} ${cy} ${cx + rx} ${cy + ry * 0.12}
    C ${cx + rx} ${cy + ry * 0.72} ${cx + rx * 0.52} ${cy + ry} ${cx} ${cy + ry}
    C ${cx - rx * 0.52} ${cy + ry} ${cx - rx} ${cy + ry * 0.72} ${cx - rx} ${cy + ry * 0.12}
    C ${cx - rx} ${cy} ${cx - rx} ${cy - ry} ${cx} ${cy - ry} Z`

  // Los hombros empiezan bajo el mentón; su curva queda fuera de la cabeza.
  const torso = `M ${cx - neckW} ${neckTop}
    C ${cx - neckW} ${neckBottom} ${cx - shoulderW * 0.6} ${shoulderTop} ${cx - shoulderW} ${bottom}
    L ${cx + shoulderW} ${bottom}
    C ${cx + shoulderW * 0.6} ${shoulderTop} ${cx + neckW} ${neckBottom} ${cx + neckW} ${neckTop} Z`

  const shoulders = `M ${cx - neckW} ${neckTop}
    C ${cx - neckW} ${neckBottom} ${cx - shoulderW * 0.6} ${shoulderTop} ${cx - shoulderW} ${bottom}
    M ${cx + neckW} ${neckTop}
    C ${cx + neckW} ${neckBottom} ${cx + shoulderW * 0.6} ${shoulderTop} ${cx + shoulderW} ${bottom}`

  return (
    <svg
      className={`booth-silhouette is-${pose}`}
      viewBox={`0 0 ${FRAME_W} ${FRAME_H}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <mask id="booth-guide-hole" maskUnits="userSpaceOnUse">
          <rect width={FRAME_W} height={FRAME_H} fill="white" />
          <path fill="black" d={head} />
          <path fill="black" d={torso} />
        </mask>
      </defs>
      <rect className="booth-silhouette-dim" width={FRAME_W} height={FRAME_H} mask="url(#booth-guide-hole)" />
      <path className="booth-silhouette-line" d={head} vectorEffect="non-scaling-stroke" />
      <path className="booth-silhouette-line" d={shoulders} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
