import {
  ChefHat,
  Crown,
  Flame,
  FlaskConical,
  Flower2,
  Gem,
  Glasses,
  Headphones,
  Palette,
  Plane,
  Rocket,
  SlidersHorizontal,
  Sparkles,
  Stethoscope,
  X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { TRAIT_CATEGORIES, traitConflicts } from '../../lib/traits'
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
  aretes: Gem,
  diadema: Sparkles,
}

interface StylePickerProps {
  photo: string
  traits: TraitSelection
  styleId: DrawingStyleId
  onToggle: (group: TraitGroup, id: string) => void
  onStyle: (id: DrawingStyleId) => void
}

type TabId = 'estilo' | TraitGroup

const TABS: { id: TabId; label: string }[] = [
  { id: 'estilo', label: 'Estilo' },
  ...TRAIT_CATEGORIES.map((category) => ({ id: category.id as TabId, label: category.title })),
]

/**
 * La foto ya elegida, el estilo y dos grupos: una profesión y un accesorio.
 * El estilo siempre tiene uno marcado. En los otros, un segundo toque lo quita.
 * Se elige por pestañas; cada pestaña enseña su carrusel de recuadros iguales.
 */
export function StylePicker({ photo, traits, styleId, onToggle, onStyle }: StylePickerProps) {
  const [tab, setTab] = useState<TabId>('estilo')
  const [open, setOpen] = useState(true)

  return (
    <div className={`booth-style${open ? '' : ' is-collapsed'}`}>
      <figure className="booth-style-photo-card">
        <img src={photo} alt="Foto que se va a dibujar" className="booth-style-photo" draggable={false} />
        {!open && (
          <button
            type="button"
            className="booth-style-toggle"
            aria-expanded={false}
            aria-controls="booth-style-panel"
            onClick={() => setOpen(true)}
          >
            <SlidersHorizontal size={16} aria-hidden="true" />
            <span className="booth-style-toggle-label">Estilos</span>
          </button>
        )}
      </figure>

      <div className="booth-style-panel" id="booth-style-panel">
        <div className="booth-style-groups">
          <section
            className={`booth-style-group${tab === 'estilo' ? ' is-active' : ''}`}
            aria-labelledby="booth-style-group-estilo"
          >
            <h3 className="booth-style-group-title" id="booth-style-group-estilo">
              Estilo
            </h3>
            <div className="booth-style-track" id="booth-style-track-estilo" role="tabpanel" tabIndex={0}>
              {DRAWING_STYLES.map((style) => {
                const selected = styleId === style.id
                return (
                  <button
                    key={style.id}
                    type="button"
                    className={`booth-style-tile${selected ? ' is-on' : ''}`}
                    aria-pressed={selected}
                    onClick={() => onStyle(style.id)}
                  >
                    <span className="booth-style-tile-art">
                      <img src={style.sample} alt="" draggable={false} />
                    </span>
                    <span className="booth-style-tile-label">{style.label}</span>
                  </button>
                )
              })}
            </div>
          </section>

          {TRAIT_CATEGORIES.map((category) => (
            <section
              key={category.id}
              className={`booth-style-group${tab === category.id ? ' is-active' : ''}`}
              aria-labelledby={`booth-style-group-${category.id}`}
            >
              <h3 className="booth-style-group-title" id={`booth-style-group-${category.id}`}>
                {category.title}
              </h3>
              <div
                className="booth-style-track"
                id={`booth-style-track-${category.id}`}
                role="tabpanel"
                tabIndex={0}
              >
                {category.options.map((option) => {
                  const selected = traits[category.id] === option.id
                  // Si el otro grupo ya ocupa ese espacio, el botón se apaga en
                  // vez de apilar dos sombreros sobre la misma cabeza.
                  const blocked = traitConflicts(traits, category.id, option.id)
                  return (
                    <button
                      key={option.id}
                      type="button"
                      className={`booth-style-tile${selected ? ' is-on' : ''}`}
                      aria-pressed={selected}
                      disabled={blocked}
                      onClick={() => onToggle(category.id, option.id)}
                    >
                      <span className="booth-style-tile-art">
                        <TraitGlyph id={option.id} />
                      </span>
                      <span className="booth-style-tile-label">{option.label}</span>
                    </button>
                  )
                })}
              </div>
            </section>
          ))}
        </div>

        <div className="booth-style-footer">
          <div className="booth-style-tabs" role="tablist" aria-label="Qué quieres elegir">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                aria-controls={`booth-style-track-${item.id}`}
                className={tab === item.id ? 'is-on' : undefined}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="booth-style-close"
            aria-label="Cerrar las opciones"
            aria-controls="booth-style-panel"
            aria-expanded
            onClick={() => setOpen(false)}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
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
