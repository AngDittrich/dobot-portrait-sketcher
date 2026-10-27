/** Ids que el backend traduce a una frase del prompt. No hay texto libre. */

export type TraitGroup = 'profession' | 'head'

export interface TraitOption {
  id: string
  label: string
}

export const PROFESSIONS: TraitOption[] = [
  { id: 'chef', label: 'Chef' },
  { id: 'medico', label: 'Médico' },
  { id: 'astronauta', label: 'Astronauta' },
  { id: 'musico', label: 'Músico' },
]

export const HEADWEAR: TraitOption[] = [
  { id: 'sombrero', label: 'Sombrero' },
  { id: 'gorra', label: 'Gorra' },
  { id: 'corona', label: 'Corona' },
]

export interface TraitSelection {
  profession: string | null
  head: string | null
}

export const EMPTY_TRAITS: TraitSelection = { profession: null, head: null }

export function selectedTraitIds(traits: TraitSelection): string[] {
  return [traits.profession, traits.head].filter((id): id is string => id !== null)
}
