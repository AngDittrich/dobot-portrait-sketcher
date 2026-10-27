/** Ids que el backend traduce a una frase del prompt. No hay texto libre. */

export type TraitGroup = 'profession' | 'accessory'

/**
 * Qué parte del cuerpo ocupa un rasgo. Dos rasgos que comparten espacio se
 * enciman en el dibujo: bombero ya trae casco, así que sumarle un sombrero
 * significa dos sombreros sobre la misma cabeza.
 */
export type TraitSlot = 'head' | 'eyes' | 'ears' | 'neck' | 'hair' | 'body'

const SLOTS: Record<string, TraitSlot[]> = {
  chef: ['head', 'body'],
  medico: ['body'],
  astronauta: ['head', 'body'],
  musico: ['ears', 'body'],
  piloto: ['head', 'body'],
  bombero: ['head', 'body'],
  cientifico: ['body'],
  artista: ['head', 'body'],
  sombrero: ['head'],
  gorra: ['head'],
  corona: ['head'],
  lentes: ['eyes'],
  mono: ['neck'],
  flor: ['hair'],
}

export function traitSlots(id: string): TraitSlot[] {
  return SLOTS[id] ?? []
}

/** Si elegir `id` choca con lo que ya está puesto en el otro grupo. */
export function traitConflicts(traits: TraitSelection, group: TraitGroup, id: string): boolean {
  const other = group === 'profession' ? traits.accessory : traits.profession
  if (!other || other === id) return false
  const mine = traitSlots(id)
  return traitSlots(other).some((slot) => mine.includes(slot))
}

/** Un toque pone, otro quita, y lo que se encimaría se retira. */
export function toggleTrait(
  traits: TraitSelection,
  group: TraitGroup,
  id: string,
): TraitSelection {
  const next: TraitSelection = { ...traits, [group]: traits[group] === id ? null : id }
  if (next[group] === null) return next
  const mine = traitSlots(id)
  const other: TraitGroup = group === 'profession' ? 'accessory' : 'profession'
  const rival = next[other]
  if (rival && traitSlots(rival).some((slot) => mine.includes(slot))) next[other] = null
  return next
}

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
