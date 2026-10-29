/**
 * Botón de entrada al panel del MG400. El PIN y el panel en sí los maneja
 * `AdminArea` por ruta (`/admin`); este componente solo navega ahí.
 */
export function AdminDesk({ onOpenAdmin }: { onOpenAdmin: () => void }) {
  return (
    <button type="button" className="booth-admin-entry admin-press" onClick={onOpenAdmin}>
      Admin
    </button>
  )
}
