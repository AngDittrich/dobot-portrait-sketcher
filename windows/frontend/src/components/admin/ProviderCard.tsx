import type { AdminActivity } from '../../lib/api'

type Provider = AdminActivity['provider']

/** Tarjeta del proveedor de IA: qué ruta dibuja el boceto y si puede responder. */
export function ProviderCard({ provider }: { provider: Provider }) {
  const openrouter = provider.available.openrouter === true
  const local = provider.available.local === true
  return (
    <section className="admin-card">
      <h3>Boceto por IA</h3>
      <dl className="admin-facts">
        <div>
          <dt>Ruta</dt>
          <dd>{provider.configured}</dd>
        </div>
        <div>
          <dt>Modelo</dt>
          <dd>{provider.model}</dd>
        </div>
        <div>
          <dt>Respaldo</dt>
          <dd>{provider.fallback_model}</dd>
        </div>
        <div>
          <dt>OpenRouter</dt>
          <dd className={openrouter ? 'is-good' : 'is-bad'}>{openrouter ? 'con key' : 'sin key'}</dd>
        </div>
        <div>
          <dt>Local</dt>
          <dd>{local ? 'instalado' : 'sin modelo (pide GPU de 16 GB)'}</dd>
        </div>
      </dl>
      <p className="admin-card-note">
        Si el proveedor falla, la cabina cae al respaldo XDoG sin romper la pantalla.
      </p>
    </section>
  )
}
