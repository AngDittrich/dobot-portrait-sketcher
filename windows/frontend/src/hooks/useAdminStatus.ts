import { useCallback, useEffect, useRef, useState } from 'react'
import { adminCommand, adminStatus } from '../lib/api'
import type { AdminStatus } from '../lib/api'
import type { StickId } from '../components/admin/stickSpaces'

/**
 * Sondeo del estado del robot cada 800 ms mientras la página admin está abierta.
 */
export function useAdminStatus(token: string) {
  const [status, setStatus] = useState<AdminStatus | null>(null)
  const [pollError, setPollError] = useState('')

  useEffect(() => {
    let stop = false
    let inflight = false
    const tick = async () => {
      // Si el sondeo anterior sigue en camino (reconexión lenta), no se lanza
      // otro: dos consultas a la vez se pisan en el único socket del MG400.
      if (inflight) return
      inflight = true
      try {
        const next = await adminStatus(token)
        if (stop) return
        setStatus(next)
        setPollError('')
      } catch (error) {
        if (!stop) setPollError(error instanceof Error ? error.message : 'sin respuesta')
      } finally {
        inflight = false
      }
    }
    void tick()
    const timer = window.setInterval(() => void tick(), 800)
    return () => {
      stop = true
      window.clearInterval(timer)
    }
  }, [token])

  return { status, pollError }
}

/**
 * Cadena de jog: MoveJog al salir de la zona muerta del stick y MoveJog() al
 * soltar. Si dos sticks pisan a la vez manda el último. Al desmontar (cambiar
 * de sección o cerrar el panel) el brazo frena solo.
 */
export function useJog({
  token,
  getSpeed,
  onError,
}: {
  token: string
  getSpeed: () => number
  onError: (message: string) => void
}) {
  const tokenRef = useRef(token)
  useEffect(() => {
    tokenRef.current = token
  }, [token])
  const getSpeedRef = useRef(getSpeed)
  useEffect(() => {
    getSpeedRef.current = getSpeed
  })
  const onErrorRef = useRef(onError)
  useEffect(() => {
    onErrorRef.current = onError
  })

  const [stickEpoch, setStickEpoch] = useState(0)
  const jogging = useRef(false)
  const desired = useRef<string | null>(null)
  const applied = useRef<string | null>(null)
  const owner = useRef<StickId | null>(null)
  const chain = useRef(Promise.resolve())

  useEffect(() => {
    return () => {
      desired.current = null
      owner.current = null
      const issued = tokenRef.current
      void chain.current.then(() => {
        if (applied.current === null && !jogging.current) return
        applied.current = null
        jogging.current = false
        return adminCommand(issued, { action: 'jog', axis: '' }).catch(() => undefined)
      })
    }
  }, [])

  const hold = useCallback((stick: StickId, axis: string | null) => {
    const issued = tokenRef.current
    if (!issued) return
    if (axis === null) {
      if (owner.current !== stick) return
      owner.current = null
    } else {
      owner.current = stick
    }
    desired.current = axis
    chain.current = chain.current
      .then(async () => {
        while (applied.current !== desired.current) {
          const next = desired.current
          await adminCommand(issued, {
            action: 'jog',
            axis: next ?? '',
            speed: next ? getSpeedRef.current() : undefined,
          })
          applied.current = next
          jogging.current = next !== null
        }
      })
      .catch((error: unknown) => {
        desired.current = null
        applied.current = null
        owner.current = null
        jogging.current = false
        setStickEpoch((value) => value + 1)
        onErrorRef.current(error instanceof Error ? error.message : 'el robot rechazó el movimiento')
      })
  }, [])

  return { hold, stickEpoch }
}
