import { GUIDE } from '../../hooks/useFraming'
import type { FramingPose } from '../../hooks/useFraming'

/**
 * Figura de encuadre (cabeza y hombros), dibujada con coordenadas en
 * píxeles del escenario para que no se estire con el visor 4:3. El color
 * es el estado: verde si la cara está dentro, rojo si no. Sin etiquetas.
 */
export function FramingGuide({ pose }: { pose: FramingPose }) {
  const cx = GUIDE.cx * 1000
  const cy = GUIDE.cy * 1000
  const rx = GUIDE.rx * 1000
  const ry = GUIDE.ry * 1000
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
      viewBox="0 0 1000 1000"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <mask id="booth-guide-hole" maskUnits="userSpaceOnUse">
          <rect width="1000" height="1000" fill="white" />
          <path fill="black" d={head} />
          <path fill="black" d={torso} />
        </mask>
      </defs>
      <rect className="booth-silhouette-dim" width="1000" height="1000" mask="url(#booth-guide-hole)" />
      <path className="booth-silhouette-line" d={head} vectorEffect="non-scaling-stroke" />
      <path className="booth-silhouette-line" d={shoulders} vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
