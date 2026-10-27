import {
  ChefHat,
  Crown,
  Flame,
  FlaskConical,
  Flower2,
  Glasses,
  Headphones,
  Palette,
  Plane,
  Rocket,
  Stethoscope,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { TRAIT_CATEGORIES } from '../../lib/traits'
import type { TraitGroup, TraitSelection } from '../../lib/traits'
import { DRAWING_STYLES } from '../../lib/drawingStyles'
import type { DrawingStyleId } from '../../lib/drawingStyles'

const ICONS: Record<string, LucideIcon> = {
  chef: ChefHat,
  medico: Stethoscope,
  astronauta: Rocket,
  musico: Headphones,
  piloto: Plane,
  bombero: Flame,
  cientifico: FlaskConical,
  artista: Palette,
  corona: Crown,
  lentes: Glasses,
  flor: Flower2,
}

interface StylePickerProps {
  photo: string
  traits: TraitSelection
  styleId: DrawingStyleId
  onToggle: (group: TraitGroup, id: string) => void
  onStyle: (id: DrawingStyleId) => void
}

/**
 * La foto ya elegida, el estilo y dos grupos: una profesión y un accesorio.
 * El estilo siempre tiene uno marcado. En los otros, un segundo toque lo quita.
 */
export function StylePicker({ photo, traits, styleId, onToggle, onStyle }: StylePickerProps) {
  return (
    <div className="booth-style">
      <img src={photo} alt="Foto que se va a dibujar" className="booth-style-photo" draggable={false} />
      <div className="booth-style-options">
        <section className="booth-style-group" aria-label="Estilo">
          <h2>Estilo</h2>
          <div className="booth-style-samples">
            {DRAWING_STYLES.map((style) => {
              const selected = styleId === style.id
              return (
                <button
                  key={style.id}
                  type="button"
                  className={selected ? 'is-on' : undefined}
                  aria-pressed={selected}
                  onClick={() => onStyle(style.id)}
                >
                  <img src={style.sample} alt="" draggable={false} />
                  <span>{style.label}</span>
                </button>
              )
            })}
          </div>
        </section>
        {TRAIT_CATEGORIES.map((category) => (
          <section key={category.id} className="booth-style-group" aria-label={category.title}>
            <h2>{category.title}</h2>
            <div className="booth-style-grid">
              {category.options.map((option) => {
                const selected = traits[category.id] === option.id
                return (
                  <button
                    key={option.id}
                    type="button"
                    className={selected ? 'is-on' : undefined}
                    aria-pressed={selected}
                    onClick={() => onToggle(category.id, option.id)}
                  >
                    <TraitGlyph id={option.id} />
                    <span>{option.label}</span>
                  </button>
                )
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

function TraitGlyph({ id }: { id: string }) {
  if (id === 'sombrero') return <SombreroIcon />
  if (id === 'gorra') return <GorraIcon />
  if (id === 'mono') return <MonoIcon />
  const Icon = ICONS[id]
  if (!Icon) return null
  return <Icon aria-hidden="true" />
}

function SombreroIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 16.2c2.2-1.3 4.8-2 9-2s6.8.7 9 2" />
      <path d="M8 14.4c.5-3.2 2-6.2 4-6.2s3.5 3 4 6.2" />
      <path d="M2.5 17.4h19" />
    </svg>
  )
}

function GorraIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6.5 15.2c.7-4 2.8-6.4 6-6.4 2.7 0 4.6 1.7 5.4 4.4" />
      <path d="M6.2 15h12" />
      <path d="M17.2 14.4c1.6.5 3.2 1.6 4 3.2" />
    </svg>
  )
}

function MonoIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 12 6.2 8.4C4 10.2 4 13.8 6.2 15.6L12 12l5.8-3.6c2.2 1.8 2.2 5.4 0 7.2L12 12z" />
      <circle cx="12" cy="12" r="1.15" />
    </svg>
  )
}
