import type { CapacitorConfig } from '@capacitor/cli'

/**
 * Envoltura Android de la cabina.
 *
 * La app web NO se copia aquí: `webDir` apunta al `dist` que genera
 * windows/frontend, así que la UI se sigue editando en un solo sitio.
 *
 * Dos ajustes que no son opcionales:
 * - `allowMixedContent`: Capacitor sirve la app desde https://localhost (eso es
 *   lo que hace que la cámara funcione, porque getUserMedia exige contexto
 *   seguro) mientras el backend de la cabina es http://192.168.10.3:8000.
 *   Sin esto el WebView bloquea la llamada y el boceto nunca llega.
 * - `server.cleartext`: Android 9+ bloquea tráfico sin cifrar por defecto.
 */
const config: CapacitorConfig = {
  appId: 'com.syscom.cabina',
  appName: 'Cabina SYSCOM',
  webDir: '../../windows/frontend/dist',
  android: {
    allowMixedContent: true,
  },
  server: {
    cleartext: true,
  },
}

export default config
