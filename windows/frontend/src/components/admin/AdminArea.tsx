import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { getAdminToken, setAdminToken } from '../../lib/adminSession'
import { unlockAdmin } from '../../lib/api'
import { AdminPage } from './AdminPage'
import { DEFAULT_SECTION, isSectionId } from './sections'

/**
 * Dueño de la ruta `/admin` y `/admin/:seccion`. La sección vive en la URL
 * (no en un `useState` de `AdminPage`), así que recargar la página reabre el
 * panel en la misma pestaña en vez de mandar a la cabina del visitante.
 *
 * El PIN se pide de nuevo solo al pulsar Salir o si el backend rechaza el
 * token (se reinició uvicorn, que olvida los tokens en memoria): en ambos
 * casos se borra `sessionStorage`, pero la URL de la sección no se toca.
 */
export function AdminArea({
  path,
  navigate,
}: {
  path: string
  navigate: (next: string, options?: { replace?: boolean }) => void
}) {
  const [token, setToken] = useState<string | null>(() => getAdminToken())
  const [pin, setPin] = useState('')
  const [wrong, setWrong] = useState(false)
  const sending = useRef(false)

  const raw = path.split('/')[2] ?? ''
  const section = isSectionId(raw) ? raw : DEFAULT_SECTION

  // Completa o corrige la URL (/admin, o una sección que no existe) sin
  // perder el historial: un solo reemplazo, no una pila de redirecciones.
  useEffect(() => {
    const canonical = `/admin/${section}`
    if (path !== canonical) navigate(canonical, { replace: true })
  }, [path, section, navigate])

  function close() {
    setAdminToken(null)
    setToken(null)
    setPin('')
    setWrong(false)
    navigate('/')
  }

  async function submitPin(next: string) {
    if (sending.current || next.length !== 4) return
    sending.current = true
    try {
      const issued = await unlockAdmin(next)
      setAdminToken(issued)
      setToken(issued)
      setWrong(false)
    } catch {
      setWrong(true)
      setPin('')
    } finally {
      sending.current = false
    }
  }

  const onExpired = useCallback(() => {
    setAdminToken(null)
    setToken(null)
  }, [])

  if (!token) {
    return createPortal(
      <div className="admin-veil" role="presentation" onClick={close}>
        <form
          className={`admin-glass admin-pin${wrong ? ' is-wrong' : ''}`}
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-pin-title"
          onClick={(event) => event.stopPropagation()}
          onSubmit={(event) => {
            event.preventDefault()
            void submitPin(pin)
          }}
        >
          <h2 id="admin-pin-title">Panel del robot</h2>
          <p>PIN de 4 dígitos</p>
          <div className="admin-pin-cells" aria-hidden="true">
            {[0, 1, 2, 3].map((index) => (
              <span key={index} className={pin.length > index ? 'is-filled' : ''}>
                {pin[index] ? '•' : ''}
              </span>
            ))}
          </div>
          <input
            autoFocus
            inputMode="numeric"
            autoComplete="off"
            aria-label="PIN de 4 dígitos"
            value={pin}
            onChange={(event) => {
              const next = event.target.value.replace(/\D/g, '').slice(0, 4)
              setWrong(false)
              setPin(next)
              if (next.length === 4) void submitPin(next)
            }}
          />
        </form>
      </div>,
      document.body,
    )
  }

  return createPortal(
    <AdminPage
      token={token}
      section={section}
      onSection={(id) => navigate(`/admin/${id}`, { replace: true })}
      onClose={close}
      onExpired={onExpired}
    />,
    document.body,
  )
}
