/**
 * Token del panel admin, guardado en `sessionStorage`.
 *
 * El backend lo vive en memoria (`app/admin_ops.py`) y lo olvida si uvicorn
 * se reinicia, pero una recarga normal de la página no reinicia el backend.
 * Guardarlo aquí evita pedir el PIN otra vez solo porque el navegador
 * refrescó: el panel reaparece en la misma sección. Si el backend sí lo
 * rechaza (401), `AdminArea` lo borra y vuelve a pedir el PIN.
 */
const KEY = 'dobot_admin_token'

export function getAdminToken(): string | null {
  try {
    return window.sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function setAdminToken(token: string | null): void {
  try {
    if (token) window.sessionStorage.setItem(KEY, token)
    else window.sessionStorage.removeItem(KEY)
  } catch {
    // Almacenamiento no disponible (ventana privada, por ejemplo): se vuelve
    // a pedir el PIN si hace falta, no es un error que detenga la cabina.
  }
}
