import { useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { unlockAdmin } from '../../lib/api'
import { AdminPage } from '../admin/AdminPage'

/**
 * Entrada al panel del MG400: botón en la barra, PIN de 4 dígitos (se
 * comprueba en el backend) y la página admin a pantalla completa. El token
 * no se guarda, así que salir del panel vuelve a pedir el PIN.
 */
export function AdminDesk() {
  const [phase, setPhase] = useState<'closed' | 'pin' | 'panel'>('closed')
  const [pin, setPin] = useState('')
  const [wrong, setWrong] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  const sending = useRef(false)

  function close() {
    setPhase('closed')
    setToken(null)
    setPin('')
    setWrong(false)
  }

  async function submitPin(next: string) {
    if (sending.current || next.length !== 4) return
    sending.current = true
    try {
      const issued = await unlockAdmin(next)
      setToken(issued)
      setPhase('panel')
      setWrong(false)
    } catch {
      setWrong(true)
      setPin('')
    } finally {
      sending.current = false
    }
  }

  return (
    <>
      <button type="button" className="booth-admin-entry admin-press" onClick={() => setPhase('pin')}>
        Admin
      </button>

      {phase === 'pin' &&
        createPortal(
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
        )}

      {phase === 'panel' &&
        token &&
        createPortal(<AdminPage token={token} onClose={close} />, document.body)}
    </>
  )
}
