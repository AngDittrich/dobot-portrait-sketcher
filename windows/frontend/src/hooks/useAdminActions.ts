import { useCallback } from 'react'
import {
  adminArea,
  adminCalibration,
  adminClearJobs,
  adminCommand,
  adminGoto,
  adminPose,
  adminTestDraw,
  cancelActiveJob,
  saveAdminBooth,
} from '../lib/api'
import type {
  AdminCommand,
  BoothSettings,
  Calibration,
  CornerPose,
  Corners,
  RobotPose,
  SpotId,
} from '../lib/api'

/**
 * Acciones del panel admin en un solo lugar.
 *
 * Antes cada sección llamaba a `lib/api` por su cuenta con su propio
 * try/catch, así que el mismo botón se comportaba distinto según la pestaña
 * (el 401 por reinicio de uvicorn solo lo detectaba el sondeo de estado).
 * Ahora todas las secciones usan estas funciones: mismo llamado, mismo
 * manejo de aviso y de sesión expirada, se llame desde donde se llame.
 */
export function isExpiredError(error: unknown): boolean {
  return error instanceof Error && error.message.startsWith('Backend 401')
}

export interface AdminActionsOptions {
  onNotice: (message: string) => void
  onExpired: () => void
  /** Recarga la bitácora (la actividad de `AdminPage`) tras borrarla. */
  reloadActivity?: () => Promise<unknown>
}

function complete(corners: Partial<Corners>): corners is Corners {
  return Boolean(corners.tl && corners.tr && corners.bl)
}

export function useAdminActions(token: string, options: AdminActionsOptions) {
  const { onNotice, onExpired, reloadActivity } = options

  const fail = useCallback(
    (error: unknown, fallback: string) => {
      if (isExpiredError(error)) onExpired()
      onNotice(error instanceof Error ? error.message : fallback)
    },
    [onNotice, onExpired],
  )

  /** Orden genérica al robot (energía, flujo, jog, pasos, MovL, paro…). */
  const send = useCallback(
    async (command: AdminCommand): Promise<void> => {
      try {
        await adminCommand(token, command)
        onNotice('')
      } catch (error) {
        fail(error, 'el robot rechazó la orden')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Borra la bitácora ya cerrada y recarga la actividad. Devuelve cuántos quitó. */
  const clearLogs = useCallback(async (): Promise<number> => {
    try {
      const { removed } = await adminClearJobs(token)
      if (reloadActivity) await reloadActivity()
      onNotice(removed > 0 ? `Bitácora borrada: ${removed} trabajo(s).` : 'La bitácora ya estaba vacía.')
      return removed
    } catch (error) {
      fail(error, 'no se pudo borrar la bitácora')
      throw error
    }
  }, [token, reloadActivity, onNotice, fail])

  /** Corta el dibujo en curso. Lo usa la cabina (sin PIN) y el panel. */
  const cancelDraw = useCallback(async (): Promise<void> => {
    try {
      await cancelActiveJob()
      onNotice('')
    } catch (error) {
      fail(error, 'no se pudo cancelar el dibujo')
      throw error
    }
  }, [onNotice, fail])

  /** Lee DI1–DI4 y lo deja en el aviso (Control → Entradas). */
  const readInputs = useCallback(async (): Promise<void> => {
    try {
      const bits: string[] = []
      for (const index of [1, 2, 3, 4]) {
        try {
          const result = await adminCommand(token, { action: 'di', index })
          bits.push(`DI${index} ${result.value || 'sin valor'}`)
        } catch {
          bits.push(`DI${index} sin respuesta`)
        }
      }
      onNotice(bits.join(' · '))
    } catch (error) {
      fail(error, 'no se pudieron leer las entradas')
      throw error
    }
  }, [token, onNotice, fail])

  /** Lee ToolDI1–ToolDI2 y lo deja en el aviso (Control → Entradas). */
  const readToolInput = useCallback(
    async (index: number): Promise<void> => {
      try {
        const result = await adminCommand(token, { action: 'tooldi', index })
        onNotice(`ToolDI${index} ${result.value || 'sin valor'}`)
      } catch (error) {
        fail(error, 'no se pudo leer la entrada de la herramienta')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Lleva la muñeca de toda la hoja al ángulo pedido, o al guardado si no viene. */
  const homeJ4 = useCallback(
    async (j4?: number): Promise<void> => {
      try {
        const result = await adminCommand(token, j4 === undefined ? { action: 'j4home' } : { action: 'j4home', j4 })
        onNotice(result.value || '')
      } catch (error) {
        fail(error, 'no se pudo poner J4')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Lleva el brazo con el lápiz arriba a una esquina o al centro. */
  const go = useCallback(
    async (target: SpotId, corners: Partial<Corners>, liftMm: number, j4?: number): Promise<void> => {
      try {
        if (complete(corners)) {
          await adminGoto(token, { corner: target, corners }, liftMm, j4)
        } else {
          const point: CornerPose | undefined = target === 'center' ? undefined : corners[target]
          if (!point) throw new Error('escribe esa esquina primero')
          await adminGoto(token, { point }, liftMm, j4)
        }
        onNotice('')
      } catch (error) {
        fail(error, 'el brazo no pudo ir a ese punto')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Recorre el borde guardado con el lápiz arriba. */
  const markArea = useCallback(async (): Promise<void> => {
    try {
      const area = await adminArea(token)
      onNotice(
        `Área recorrida: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm con el lápiz arriba.`,
      )
    } catch (error) {
      fail(error, 'no se pudo marcar el área')
      throw error
    }
  }, [token, onNotice, fail])

  /** Recorre el marco de una hoja estándar, centrado en las esquinas enseñadas. */
  const markSheet = useCallback(
    async (sheet: string, corners: Partial<Corners> | undefined, liftMm: number, j4?: number): Promise<void> => {
      try {
        const area = await adminArea(token, {
          sheet,
          corners: corners && complete(corners) ? corners : undefined,
          lift_mm: liftMm,
          j4,
        })
        onNotice(
          `Marco de ${area.label}: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm, centrado en las esquinas, con el lápiz arriba.`,
        )
      } catch (error) {
        fail(error, 'no se pudo marcar el marco')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Recorre las cuatro esquinas de la hoja enseñada, con el lápiz arriba. */
  const tracePerimeter = useCallback(
    async (corners: Partial<Corners> | undefined, liftMm: number, j4?: number): Promise<void> => {
      try {
        const area = await adminArea(token, {
          corners: corners && complete(corners) ? corners : undefined,
          lift_mm: liftMm,
          j4,
        })
        onNotice(
          `Perímetro de las esquinas de esta pantalla: ${Math.round(area.width_mm)} × ${Math.round(area.height_mm)} mm, con el lápiz arriba.`,
        )
      } catch (error) {
        fail(error, 'no se pudo recorrer el perímetro')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Escribe SYSCOM en el centro de la hoja enseñada. */
  const drawTest = useCallback(
    async (
      corners: Partial<Corners> | undefined,
      liftMm: number,
      marginMm: number,
      j4?: number,
    ): Promise<void> => {
      try {
        await adminTestDraw(token, {
          corners: corners && complete(corners) ? corners : undefined,
          lift_mm: liftMm,
          margin_mm: marginMm,
          j4,
        })
        onNotice('Dibujando SYSCOM en el centro de la hoja.')
      } catch (error) {
        fail(error, 'no se pudo dibujar la prueba')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Guarda la cabina (conexión, hoja, esquinas…). */
  const saveBooth = useCallback(
    async (booth: BoothSettings): Promise<void> => {
      try {
        await saveAdminBooth(token, booth)
        onNotice('Cabina guardada. El siguiente dibujo usa esta hoja.')
      } catch (error) {
        fail(error, 'no se pudo guardar la cabina')
        throw error
      }
    },
    [token, onNotice, fail],
  )

  /** Medida y avisos de unas esquinas todavía sin guardar (vista previa del mapa). */
  const calibrate = useCallback(
    async (corners: Corners, marginMm: number): Promise<Calibration> => {
      try {
        return await adminCalibration(token, corners, marginMm)
      } catch (error) {
        if (isExpiredError(error)) onExpired()
        throw error
      }
    },
    [token, onExpired],
  )

  /** Pose fresca, ya en el usuario y la herramienta de la cabina. */
  const readPose = useCallback(async (): Promise<RobotPose> => {
    try {
      return await adminPose(token)
    } catch (error) {
      fail(error, 'no se pudo leer la pose')
      throw error
    }
  }, [token, fail])

  /** Enseña una esquina con una pose recién leída, no con el sondeo. */
  const teachCorner = useCallback(
    async (label: string): Promise<RobotPose> => {
      const pose = await readPose()
      onNotice(`Esquina ${label} tomada. Falta Guardar cabina.`)
      return pose
    },
    [readPose, onNotice],
  )

  return {
    send,
    note: onNotice,
    clearLogs,
    cancelDraw,
    readInputs,
    readToolInput,
    homeJ4,
    go,
    markArea,
    markSheet,
    tracePerimeter,
    drawTest,
    saveBooth,
    readPose,
    teachCorner,
    calibrate,
  }
}

export type AdminActions = ReturnType<typeof useAdminActions>
