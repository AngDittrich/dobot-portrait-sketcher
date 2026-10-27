/** Estilos de línea. La muestra es siempre la misma persona. */

export const DEFAULT_STYLE = 'caricatura'

export const DRAWING_STYLES = [
  { id: 'retrato', label: 'Retrato', sample: '/styles/retrato.jpg' },
  { id: 'caricatura', label: 'Caricatura', sample: '/styles/caricatura.jpg' },
  { id: 'anime', label: 'Anime', sample: '/styles/anime.jpg' },
  { id: 'cartoon', label: 'Cartoon', sample: '/styles/cartoon.jpg' },
] as const

export type DrawingStyleId = (typeof DRAWING_STYLES)[number]['id']

export function isDrawingStyle(id: string): id is DrawingStyleId {
  return DRAWING_STYLES.some((style) => style.id === id)
}
