import { Gamepad2, Gauge, History, Settings } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** Compartido entre `AdminArea` (lee la URL) y `AdminPage` (pinta la barra). */
export type SectionId = 'estado' | 'control' | 'configuracion' | 'actividad'

export const SECTIONS: { id: SectionId; label: string; icon: LucideIcon }[] = [
  { id: 'estado', label: 'Estado', icon: Gauge },
  { id: 'control', label: 'Control', icon: Gamepad2 },
  { id: 'configuracion', label: 'Configuración', icon: Settings },
  { id: 'actividad', label: 'Actividad', icon: History },
]

export const DEFAULT_SECTION: SectionId = 'estado'

export function isSectionId(value: string): value is SectionId {
  return SECTIONS.some((item) => item.id === value)
}
