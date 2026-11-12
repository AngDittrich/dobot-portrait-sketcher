import { Gamepad2, Gauge, History, Joystick, Layers, PenLine, Settings } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** Compartido entre `AdminArea` (lee la URL) y `AdminPage` (pinta la barra). */
export type SectionId = 'estado' | 'control' | 'mando' | 'dibujar' | 'configuracion' | 'actividad' | 'depuracion'

export const SECTIONS: { id: SectionId; label: string; icon: LucideIcon }[] = [
  { id: 'estado', label: 'Estado', icon: Gauge },
  { id: 'control', label: 'Control', icon: Gamepad2 },
  { id: 'mando', label: 'Mando', icon: Joystick },
  { id: 'dibujar', label: 'Dibujar', icon: PenLine },
  { id: 'configuracion', label: 'Configuración', icon: Settings },
  { id: 'actividad', label: 'Actividad', icon: History },
  { id: 'depuracion', label: 'Depuración', icon: Layers },
]

export const DEFAULT_SECTION: SectionId = 'estado'

export function isSectionId(value: string): value is SectionId {
  return SECTIONS.some((item) => item.id === value)
}
