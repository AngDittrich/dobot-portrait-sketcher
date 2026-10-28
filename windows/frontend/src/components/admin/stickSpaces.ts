/** Espacios de movimiento de los dos joysticks del panel admin. */

export type Axes = { up: string; down: string; left: string; right: string }
export type StickId = 'primary' | 'secondary'

export const PLANE: Record<StickId, { title: string; axes: Axes }> = {
  primary: { title: 'Plano XY', axes: { up: 'Y+', down: 'Y-', left: 'X-', right: 'X+' } },
  secondary: { title: 'Altura y muñeca', axes: { up: 'Z+', down: 'Z-', left: 'R-', right: 'R+' } },
}

export const JOINTS: Record<StickId, { title: string; axes: Axes }> = {
  primary: { title: 'J1 y J2', axes: { up: 'J1+', down: 'J1-', left: 'J2-', right: 'J2+' } },
  secondary: { title: 'J3 y J4', axes: { up: 'J3+', down: 'J3-', left: 'J4-', right: 'J4+' } },
}
