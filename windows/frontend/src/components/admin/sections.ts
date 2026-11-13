import { Crosshair, Gauge, History, Joystick, Layers, PenLine, Settings, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/** Compartido entre `AdminArea` (lee la URL) y `AdminPage` (pinta la barra). */
export type SectionId =
  | 'estado'
  | 'control'
  | 'calibracion'
  | 'dibujar'
  | 'ia'
  | 'configuracion'
  | 'actividad'
  | 'depuracion'

export const SECTIONS: { id: SectionId; label: string; icon: LucideIcon }[] = [
  { id: 'estado', label: 'Estado', icon: Gauge },
  { id: 'control', label: 'Control', icon: Joystick },
  { id: 'calibracion', label: 'Calibración', icon: Crosshair },
  { id: 'dibujar', label: 'Dibujar', icon: PenLine },
  { id: 'ia', label: 'IA', icon: Sparkles },
  { id: 'configuracion', label: 'Configuración', icon: Settings },
  { id: 'actividad', label: 'Actividad', icon: History },
  { id: 'depuracion', label: 'Depuración', icon: Layers },
]

export const DEFAULT_SECTION: SectionId = 'estado'

export function isSectionId(value: string): value is SectionId {
  return SECTIONS.some((item) => item.id === value)
}
