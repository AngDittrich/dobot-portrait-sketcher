import { HEADWEAR, PROFESSIONS } from '../../lib/traits'
import type { TraitGroup, TraitSelection } from '../../lib/traits'

interface StylePickerProps {
  photo: string
  traits: TraitSelection
  onToggle: (group: TraitGroup, id: string) => void
}

/**
 * La foto ya elegida y los botones que arman el prompt.
 * Un toque elige; otro toque en el mismo botón lo quita.
 */
export function StylePicker({ photo, traits, onToggle }: StylePickerProps) {
  return (
    <div className="booth-style">
      <img src={photo} alt="Foto que se va a dibujar" className="booth-style-photo" draggable={false} />
      <div className="booth-style-options">
        <div className="booth-style-group">
          {PROFESSIONS.map((option) => (
            <button
              key={option.id}
              type="button"
              className={traits.profession === option.id ? 'is-on' : undefined}
              aria-pressed={traits.profession === option.id}
              onClick={() => onToggle('profession', option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="booth-style-group">
          {HEADWEAR.map((option) => (
            <button
              key={option.id}
              type="button"
              className={traits.head === option.id ? 'is-on' : undefined}
              aria-pressed={traits.head === option.id}
              onClick={() => onToggle('head', option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
