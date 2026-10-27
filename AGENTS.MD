# AGENTS

Cabina de fotos que convierte un retrato en boceto de líneas y lo dibuja con un Dobot MG400.

## Decisión: el boceto lo genera una IA. XDoG está descartado

No se sigue afinando la ruta por umbrales ni por matemática. Ya se intentó durante tres días y este es su techo: ojos huecos, bigotes tramados, ropa en guiones y una cara que se desalinea en cuanto el visitante gira la cabeza, se acerca o se aleja. **Es una decisión cerrada del dueño del producto: no volver a proponerlo como camino principal.**

- **Por qué falla**: XDoG detecta cambios de brillo, no sabe qué es una cara. No puede dibujar una boca que no está en los gradientes, así que la dibuja hueca cuando hay sombra. Ningún parámetro arregla eso; es otra clase de programa.
- **Qué se usa en su lugar**: un modelo de IA de **edición** (foto → dibujo de líneas).
  - **`local`** en la PC de la cabina: es el camino normal, no cuesta por visita.
  - **`openrouter`** como respaldo cuando no hay red, falla el local o se pasa del tiempo.
  - **Gemini queda fuera** (decisión del dueño). OpenRouter ya sirve modelos equivalentes con una sola key.
- **Qué sobrevive de todo lo anterior**: solo PNG → trazos → robot. `portrait.py` y `sketch.py` (XDoG, landmarks, fundido del torso, umbrales) dejan de ser la ruta principal y quedan **congelados** como respaldo sin red: siguen funcionando, no se les añaden mejoras.
- **Consecuencia en el trazador**: la IA devuelve líneas de 1 px. El trazador de contornos (`strokes_from_mask`) les saca el borde por ambos lados y el robot dibuja **doble línea**. Hace falta el **esqueleto**: `skeletonize` → `extract_strokes` → `bridge_aligned_strokes`, que ya están escritos en `vectorize.py` y nadie llama.
- **Criterio de aceptación**: no es que el PNG se vea bonito. Es que el **render en papel** se parezca a la persona y que el robot lo dibuje en menos de 150 s. Ese es el número que se discute, no la impresión.

### Lo que ya se midió (RTX 500 Ada Laptop, 4 GB)

- **SD1.5, DreamShaper8 e Inkpunk no sirven**: devuelven ilustración con sombreado en gris, no líneas, y cambian la cara. DreamShaper le borró el bigote al sujeto. Filtran la identidad, que es lo único que no se puede negociar en una cabina.
- 3.48 GB de VRAM y 8.6–10.8 s a 16 pasos: ni siquiera entra en la ruta crítica de 6–8 s.
- **Los 4 GB son máquina de desarrollo, no de producción.** Para FLUX.2 klein o Qwen-Image-Edit a 1024 px hacen falta **16 GB de VRAM**; con 12 GB se puede, con 8 GB se sufre.
- El marcador es `windows/backend/spike_gpu/bench.py`: mide parecido por landmarks faciales, continuidad del trazo y segundos de robot, sobre el render en papel. Se corre después de `spike_gpu/probe_gpu.py`.


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

1. **Proveedor de IA** (`providers.py`, por escribir): la foto va al modelo **local**; si falla, tarda de más o no hay red, cae a **OpenRouter**. Devuelve líneas negras sobre blanco. `SKETCH_PROVIDER=local|openrouter|auto`.
2. **Trazador de esqueleto** (`vectorize.py`): `skeletonize` → `extract_strokes` → `bridge_aligned_strokes` → `simplify_and_smooth` (Chaikin + RDP) → `order_strokes` (vecino + 2-opt) → `prune_to_budget` (150 s) → `build_trajectory` (mm, 140 mm de ancho).
3. `robot/client.py` es `MockRobotClient`, sin hardware; `ROBOT_TIME_SCALE=0.2` acelera la demo.
4. **Respaldo sin red** (congelado, no mejorar): `portrait.py` (`PortraitRenderer.render`) → `sketch.lab_portrait_lines` (XDoG + landmarks) → `strokes_from_mask` (contornos).

Trampas que cuestan tiempo:

- El trazador de contornos (`strokes_from_mask`) **no sirve** para la salida de una IA: a una línea de 1 px le traza el borde de los dos lados. Para eso está el esqueleto. El contorno sobrevive solo porque el respaldo XDoG produce manchas.
- `extract_strokes` **descarta los píxeles de cruce** (grado ≥3), así que un dibujo con líneas que se tocan se parte en muchas polilíneas cortas (~40 px de media). Si el robot necesita trazos largos, hay que reconstruir las uniones; `bridge_aligned_strokes` solo une extremos alineados y no alcanza.
- Los defaults de los parámetros del respaldo están duplicados en **tres** sitios que hay que cambiar juntos: `SketchParams` (`app/main.py`), `PortraitRenderer.render` (`portrait.py`) y `lab_portrait_lines` (`sketch.py`).
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
