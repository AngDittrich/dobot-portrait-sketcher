import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import type { Axes } from './stickSpaces'

/**
 * Joystick del panel admin. Manda el eje al salir de la zona muerta y null al
 * soltar. El brazo sigue en el controlador entre esas dos órdenes, así que no
 * hace falta un websocket para que el movimiento sea continuo.
 */

function axisFromOffset(dx: number, dy: number, dead: number, axes: Axes): string | null {
  if (Math.hypot(dx, dy) < dead) return null
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? axes.right : axes.left
  return dy > 0 ? axes.down : axes.up
}

export function JoyStick({
  title,
  axes,
  disabled,
  onHold,
}: {
  title: string
  axes: Axes
  disabled: boolean
  onHold: (axis: string | null) => void
}) {
  const well = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const hotRef = useRef<string | null>(null)
  const [knob, setKnob] = useState({ x: 0, y: 0 })
  const [hot, setHot] = useState<string | null>(null)
  const [tracking, setTracking] = useState(false)
  const onHoldRef = useRef(onHold)
  useEffect(() => {
    onHoldRef.current = onHold
  }, [onHold])

  useEffect(() => {
    return () => {
      if (!dragging.current) return
      dragging.current = false
      onHoldRef.current(null)
    }
  }, [])

  useEffect(() => {
    if (!disabled || !dragging.current) return
    dragging.current = false
    hotRef.current = null
    setKnob({ x: 0, y: 0 })
    setHot(null)
    setTracking(false)
    onHoldRef.current(null)
  }, [disabled])

  function sample(event: ReactPointerEvent<HTMLDivElement>) {
    const node = well.current
    if (!node) return null
    const rect = node.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    let dx = event.clientX - cx
    let dy = event.clientY - cy
    const dist = Math.hypot(dx, dy)
    const max = rect.width * 0.32
    if (dist > max && dist > 0) {
      dx = (dx / dist) * max
      dy = (dy / dist) * max
    }
    return { dx, dy, axis: axisFromOffset(dx, dy, rect.width * 0.16, axes) }
  }

  function aim(event: ReactPointerEvent<HTMLDivElement>) {
    const next = sample(event)
    if (!next) return
    setKnob({ x: next.dx, y: next.dy })
    if (next.axis === hotRef.current) return
    hotRef.current = next.axis
    setHot(next.axis)
    onHoldRef.current(next.axis)
  }

  function release() {
    if (!dragging.current) return
    dragging.current = false
    hotRef.current = null
    setTracking(false)
    setHot(null)
    onHoldRef.current(null)
    requestAnimationFrame(() => setKnob({ x: 0, y: 0 }))
  }

  return (
    <div className={`admin-stick-wrap${disabled ? ' is-disabled' : ''}`}>
      <span className="admin-stick-title">{title}</span>
      <div
        ref={well}
        className={`admin-stick${hot ? ' is-live' : ''}${tracking ? ' is-tracking' : ''}`}
        role="application"
        aria-label={title}
        onPointerDown={(event) => {
          if (disabled) return
          event.preventDefault()
          event.currentTarget.setPointerCapture(event.pointerId)
          dragging.current = true
          setTracking(true)
          aim(event)
        }}
        onPointerMove={(event) => {
          if (!dragging.current) return
          aim(event)
        }}
        onPointerUp={release}
        onPointerCancel={release}
        onLostPointerCapture={release}
      >
        <i className={hot === axes.up ? 'is-hot' : ''}>{axes.up}</i>
        <i className={`admin-stick-east ${hot === axes.right ? 'is-hot' : ''}`}>{axes.right}</i>
        <i className={`admin-stick-south ${hot === axes.down ? 'is-hot' : ''}`}>{axes.down}</i>
        <i className={`admin-stick-west ${hot === axes.left ? 'is-hot' : ''}`}>{axes.left}</i>
        <span className="admin-stick-cross" />
        <span
          className="admin-stick-knob"
          style={{ transform: `translate(${knob.x}px, ${knob.y}px)` }}
        />
      </div>
    </div>
  )
}
