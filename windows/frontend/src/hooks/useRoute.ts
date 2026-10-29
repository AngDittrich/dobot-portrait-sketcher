import { useCallback, useEffect, useState } from 'react'

/**
 * Enrutamiento mínimo con la History API, sin librería: la URL es la fuente
 * de verdad de en qué pantalla se está. Antes de esto solo existía un estado
 * de React (`PhotoboothApp` ↔ panel admin), así que recargar la página
 * siempre volvía a la cabina del visitante, sin importar dónde estuviera el
 * administrador.
 */
function readPath(): string {
  return window.location.pathname || '/'
}

export function useRoute() {
  const [path, setPath] = useState(readPath)

  useEffect(() => {
    const onPop = () => setPath(readPath())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((next: string, options?: { replace?: boolean }) => {
    if (next === readPath()) return
    if (options?.replace) window.history.replaceState(null, '', next)
    else window.history.pushState(null, '', next)
    setPath(next)
  }, [])

  return { path, navigate }
}
