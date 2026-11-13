import { useEffect, useState } from 'react'
import type { AdminStatus, BoothSettings, CornerId, CornerPose, Corners } from '../../lib/api'

/**
 * Borrador de la cabina compartido por Calibración y Configuración.
 * Solo una de las dos está montada, así que el módulo recuerda lo que
 * todavía no se guardó al cambiar de sección.
 */

export type BoothForm = {
  backend: string
  host: string
  dry_run: boolean
  user: string
  tool: string
  speed_factor: string
  cp_draw: string
  lift_mm: string
  margin_mm: string
  sheet: string
  j4: string
}

export type Xyz = { x: string; y: string; z: string }
export type CornerKey = CornerId | 'br'

type Draft = {
  booth: BoothForm
  corners: Partial<Corners>
  brManual: boolean
  drafts: Partial<Record<CornerKey, Xyz>>
}

let draft: Draft | null = null

function text(value: unknown, fallback: string): string {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

export function formFrom(frame: NonNullable<AdminStatus['frame']>): BoothForm {
  return {
    backend: text(frame.backend, 'mg400'),
    host: text(frame.host, ''),
    dry_run: frame.dry_run === true,
    user: text(frame.user, '0'),
    tool: text(frame.tool, '0'),
    speed_factor: text(frame.speed_factor, '20'),
    cp_draw: text(frame.cp_draw, '0'),
    lift_mm: text(frame.lift_mm, '8'),
    margin_mm: text(frame.margin_mm, '8'),
    sheet: text(frame.sheet, 'a5'),
    j4: text(frame.j4, '-50'),
  }
}

export function num(value: number): string {
  return String(Math.round(value * 1000) / 1000)
}

export function xyzOf(pose: CornerPose): Xyz {
  return { x: num(pose.x), y: num(pose.y), z: num(pose.z) }
}

export function readXyz(fields: Xyz, r: number): CornerPose | null {
  if ([fields.x, fields.y, fields.z].some((part) => part.trim() === '')) return null
  const x = Number(fields.x)
  const y = Number(fields.y)
  const z = Number(fields.z)
  if (![x, y, z].every((value) => Number.isFinite(value))) return null
  return { x, y, z, r }
}

export function emptyXyz(): Xyz {
  return { x: '', y: '', z: '' }
}

function xyzDrafts(corners: Partial<Corners>): Partial<Record<CornerKey, Xyz>> {
  const seeded: Partial<Record<CornerKey, Xyz>> = {}
  for (const key of ['tl', 'tr', 'bl', 'br'] as const) {
    const pose = corners[key]
    if (pose) seeded[key] = xyzOf(pose)
  }
  return seeded
}

function taught(corners: Partial<Corners>): corners is Corners {
  return Boolean(corners.tl && corners.tr && corners.bl)
}

export function sheetOf(corners: Partial<Corners>, brManual: boolean): Corners | null {
  if (!taught(corners)) return null
  return brManual && corners.br ? corners : { tl: corners.tl, tr: corners.tr, bl: corners.bl }
}

export function settingsFrom(booth: BoothForm, corners: Partial<Corners>, brManual: boolean): BoothSettings {
  const j4 = Number(booth.j4)
  return {
    backend: booth.backend,
    host: booth.host.trim(),
    dry_run: booth.dry_run,
    user: Number(booth.user),
    tool: Number(booth.tool),
    speed_factor: Number(booth.speed_factor),
    cp_draw: Number(booth.cp_draw),
    corners: sheetOf(corners, brManual),
    lift_mm: Number(booth.lift_mm),
    margin_mm: Number(booth.margin_mm),
    sheet: booth.sheet,
    j4: Number.isFinite(j4) ? j4 : undefined,
  }
}

export function useBoothForm(status: AdminStatus | null) {
  const [booth, setBooth] = useState<BoothForm | null>(() => draft?.booth ?? null)
  const [corners, setCorners] = useState<Partial<Corners>>(() => draft?.corners ?? {})
  const [brManual, setBrManual] = useState(() => draft?.brManual ?? false)
  const [drafts, setDrafts] = useState<Partial<Record<CornerKey, Xyz>>>(() => draft?.drafts ?? {})

  const seed = status?.frame
  if (booth === null && seed?.backend) {
    const next = formFrom(seed)
    setBooth(next)
    if (seed.corners) {
      setCorners(seed.corners)
      setBrManual(Boolean(seed.corners.br))
      setDrafts(xyzDrafts(seed.corners))
    }
  }

  useEffect(() => {
    draft = booth ? { booth, corners, brManual, drafts } : null
  }, [booth, corners, brManual, drafts])

  function patch<K extends keyof BoothForm>(key: K, value: BoothForm[K]) {
    setBooth((state) => (state ? { ...state, [key]: value } : state))
  }

  return { booth, corners, setCorners, brManual, setBrManual, drafts, setDrafts, patch }
}
