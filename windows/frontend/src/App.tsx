import { useEffect } from 'react'
import { AdminArea } from './components/admin/AdminArea'
import { PhotoboothApp } from './components/photobooth/PhotoboothApp'
import { useRoute } from './hooks/useRoute'
import './styles/photobooth.css'
import './styles/admin.css'
import './styles/robot.css'

/**
 * Enrutamiento de la cabina: la URL dice si se ve el wizard del visitante o
 * el panel admin, y en qué sección. Antes todo vivía en estado de React
 * (`PhotoboothApp` ↔ `AdminDesk`), así que recargar la página en cualquier
 * panel admin mandaba de vuelta a la cabina: no había nada en la URL que
 * dijera dónde estaba el administrador.
 */
function App() {
  const { path, navigate } = useRoute()
  const isAdmin = path === '/admin' || path.startsWith('/admin/')

  // Cualquier otra ruta (typos, enlaces viejos) cae en la cabina.
  useEffect(() => {
    if (path !== '/' && !isAdmin) navigate('/', { replace: true })
  }, [path, isAdmin, navigate])

  return (
    <>
      <PhotoboothApp onOpenAdmin={() => navigate('/admin')} />
      {isAdmin && <AdminArea path={path} navigate={navigate} />}
    </>
  )
}

export default App
