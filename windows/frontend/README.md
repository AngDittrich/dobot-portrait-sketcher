# Frontend · Cabina de Retratos

App React 19 + Vite + TypeScript de la cabina de fotos: captura con webcam,
cuenta regresiva, vista previa del boceto y seguimiento del trabajo del robot.

## Arranque

```powershell
pnpm install
pnpm dev      # http://localhost:5173
```

El proxy de Vite reenvía `/api` al backend Python (`windows/backend`):

- por defecto → `http://127.0.0.1:8000`
- configurable → `VITE_API_PROXY=http://IP_DEL_PC:8000`

Si el frontend se sirve desde otro origen (no es el proxy de Vite), se define
`VITE_API_BASE=http://IP_DEL_PC:8000` en el `.env`.

## Scripts

| Script | Qué hace |
| --- | --- |
| `pnpm dev` | Servidor de desarrollo |
| `pnpm build` | `tsc -b` + build de producción en `dist/` |
| `pnpm lint` | ESLint |
| `pnpm preview` | Sirve el build de producción |

## De dónde sale el boceto

- `src/lib/api.ts` → cliente del backend: `POST /api/sketch`, `POST /api/jobs`,
  `GET /api/jobs/{id}`.
- `src/lib/sketch.ts` → `generateSketch()` pide el boceto al backend y, si el
  servidor no está levantado, cae a `generateSketchLocal()` (canvas del
  navegador) para que la demo siga viva.
- `src/hooks/usePhotobooth.ts` → máquina de estados de la cabina; al aprobar
  manda el boceto al robot y consulta el progreso cada segundo.
- `src/components/photobooth/RobotStatus.tsx` → barra de progreso del dibujo.
