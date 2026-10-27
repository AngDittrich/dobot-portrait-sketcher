# AGENTS

Cabina de fotos que convierte un retrato en boceto de líneas y lo dibuja con un Dobot MG400.

## Reglas del dueño (no negociables)

- **Rama**: comprobar con `git branch --show-current` antes de tocar nada. Angel Ortega trabaja en su rama, Angel Dittrich en la suya; `main` es producción.
- **Commits**: commits pequeños y temáticos (una funcionalidad, un bug, una integración), nunca uno de 30+ archivos. Después de cada tanda: push a la rama y preguntar si quiere Pull Request a `main`.
- **Diseño**: prohibidos los badges/labels genéricos ("EN VIVO", círculo verde, dots de estado, pills decorativas, pasos "1/4"). El estado se comunica con composición, luz y movimiento.
- Las fotos del robot no se invierten; el filtro blanco es solo para el logo SYSCOM.

## Mapa del repo

- `windows/` — el producto de la cabina. `windows/frontend/` (React 19 + Vite + TS) y `windows/backend/` (FastAPI + OpenCV/ONNX + robot).
- `lab/` — app FastAPI **aparte** donde se está rediseñando el boceto por capas (`pipeline/draw.py`, `silhouette.py`, `features.py`, `hatch.py`). `lab/server.py` todavía sirve el boceto viejo (`pipeline/sketch.py`), no la versión por capas.
- `android/` — vacío en esta rama (solo `.gitkeep`); el APK no está aquí.
- `docs/design-standards.md` — describe el portal SYSCOM, **no** esta cabina (sus rutas `frontend/src/...` no existen aquí). Para la cabina manda la sección de diseño de este archivo.

## Comandos

Backend (`windows/backend/`):

```powershell
python -m pytest -q                       # 24 tests, ~2 s, sin modelos (ONNX se cargan perezosos)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
.venv\Scripts\python.exe download_models.py   # ~180 MB a windows/backend/models/ (fuera del repo); MODELS_DIR lo cambia
```

Frontend (`windows/frontend/`): `pnpm install`, `pnpm dev`, `pnpm build` (`tsc -b && vite build`), `pnpm lint`. La API va al mismo origen por defecto; `VITE_API_BASE=http://IP:8000` apunta al PC del robot.

Lab (`lab/`): `python -m uvicorn server:app --port 8000 --reload` y `python tools/render_samples.py [--captures]` (escribe en `lab/out`). Usa el **mismo puerto** que el backend: no correr los dos a la vez.

## Pipeline del boceto (`windows/backend/app/pipeline/`)

1. `portrait.py` → `PortraitRenderer.render`: YuNet (cara) + U2Net (persona) → recorte cabeza/hombros → `sketch.lab_portrait_lines`.
2. `sketch.py` → XDoG (ruta por defecto) o `lineart.py` (ONNX `line-drawings.onnx`, opt-in con `use_lineart`); landmarks de MediaPipe, fundido del torso, umbral más suave dentro de la cara → máscara de tinta.
3. `vectorize.py` → `strokes_from_mask` → `simplify_and_smooth` (Chaikin + RDP) → `order_strokes` (vecino + 2-opt) → `prune_to_budget` (150 s) → `build_trajectory` (mm, 140 mm de ancho).
4. `robot/client.py` es `MockRobotClient`, sin hardware; `ROBOT_TIME_SCALE=0.2` acelera la demo.

Trampas que cuestan tiempo:

- `skeletonize`, `extract_strokes` y `bridge_aligned_strokes` viven en `vectorize.py` pero **main.py no los llama**: el camino real es el contorno de la tinta. Consecuencia: cada banda gruesa se traza por fuera y por dentro (doble línea) y los huecos no se puentean. El esqueleto se abandonó porque borraba ojos/nariz/pelo (manchas cortas).
- Los defaults de los parámetros están duplicados en **tres** sitios que hay que cambiar juntos: `SketchParams` (`app/main.py`), `PortraitRenderer.render` (`portrait.py`) y `lab_portrait_lines` (`sketch.py`).
- `TARGET_PX = 900` y la salida de los ONNX se recorta a múltiplos de 4 (si no, el dibujo se desplaza unos píxeles).
- Todo el pipeline trabaja en px del recorte; los mm solo aparecen en `build_trajectory`. La vista previa se dibuja con los mismos contornos que recibe el robot.

## Wizard de la cabina (`windows/`)

Wizard de una sola pantalla, sin scroll. Estados en `src/hooks/usePhotobooth.ts`:

1. `attract` — el robot saluda (`assets/robot/dobotsayinghello.webp`) y el botón COMENZAR.
2. `camera` → `countdown` → `capture` — visor y cuenta regresiva.
3. `reveal` — la foto entra en iris y se transforma a sketch.
4. `confirm` — "¿Listo para ser dibujado?" con TOMAR OTRA (vuelve a `camera`) a la izquierda y ¡SÍ! a la derecha.
5. `drawing` (3 s, `assets/robot/dobotidlemarker.webp`) → `thanks`: "LISTO. TOMA TU DIBUJO." y "SYSCOM agradece tu visita." Vuelve solo a `attract`.

Si una pantalla que espera al usuario no cambia en 3 minutos, todo se reinicia a `attract`.
