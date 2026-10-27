/** Ids que el backend traduce a una frase del prompt. No hay texto libre. */

export type TraitGroup = 'profession' | 'accessory'

export interface TraitOption {
  id: string
  label: string
}

export interface TraitCategory {
  id: TraitGroup
  title: string
  options: TraitOption[]
}

export const TRAIT_CATEGORIES: TraitCategory[] = [
  {
    id: 'profession',
    title: 'Profesión',
    options: [
      { id: 'chef', label: 'Chef' },
      { id: 'medico', label: 'Médico' },
      { id: 'astronauta', label: 'Astronauta' },
      { id: 'musico', label: 'Músico' },
      { id: 'piloto', label: 'Piloto' },
      { id: 'bombero', label: 'Bombero' },
      { id: 'cientifico', label: 'Científico' },
      { id: 'artista', label: 'Artista' },
    ],
  },
  {
    id: 'accessory',
    title: 'Accesorios',
    options: [
      { id: 'sombrero', label: 'Sombrero' },
      { id: 'gorra', label: 'Gorra' },
      { id: 'corona', label: 'Corona' },
      { id: 'lentes', label: 'Lentes' },
      { id: 'mono', label: 'Moño' },
      { id: 'flor', label: 'Flor' },
    ],
  },
]

export interface TraitSelection {
  profession: string | null
  accessory: string | null
}

export const EMPTY_TRAITS: TraitSelection = { profession: null, accessory: null }

export function selectedTraitIds(traits: TraitSelection): string[] {
  return [traits.profession, traits.accessory].filter((id): id is string => id !== null)
}
