# AGENTS

Cabina de fotos que convierte un retrato en boceto de líneas y lo dibuja con un Dobot MG400.

## Decisión: el boceto lo genera una IA. XDoG está descartado

No se sigue afinando la ruta por umbrales ni por matemática. Ya se intentó durante tres días y este es su techo: ojos huecos, bigotes tramados, ropa en guiones y una cara que se desalinea en cuanto el visitante gira la cabeza, se acerca o se aleja. **Es una decisión cerrada del dueño del producto: no volver a proponerlo como camino principal.**

- **Por qué falla**: XDoG detecta cambios de brillo, no sabe qué es una cara. No puede dibujar una boca que no está en los gradientes, así que la dibuja hueca cuando hay sombra. Ningún parámetro arregla eso; es otra clase de programa.
- **Qué se usa en su lugar**: un modelo de IA de **edición** (foto → dibujo de líneas).
  - **`openrouter`** es el camino con el que se opera hoy (`google/gemini-nano-banana-2.1`): ~3.8 ¢ y ~11 s por retrato, sin GPU. Es la decisión tomada entre probar modelos en la laptop y quedarse esperando hardware.
  - **`local`** queda disponible como opción para cuando haya una PC con GPU (16 GB de VRAM). Mientras no exista ese modelo instalado, el proveedor local no está disponible y el sistema no lo intenta.
  - **Gemini queda fuera** (decisión del dueño). OpenRouter ya sirve modelos equivalentes con una sola key.
- **Qué sobrevive de todo lo anterior**: solo PNG → trazos → robot. `portrait.py` y `sketch.py` (XDoG, landmarks, fundido del torso, umbrales) dejan de ser la ruta principal y quedan **congelados** como respaldo sin red: siguen funcionando, no se les añaden mejoras.
- **Trazador**: la IA devuelve la línea con un grosor de 2–3 px, así que se traza por su **línea central** (`strokes_from_centerline`), que recorre cada trazo una sola vez. Trazarla por contorno recorría los dos bordes y el robot dibujaba **doble línea** donde el modelo aprieta la pluma (pelo, aros, solapas). El contorno sobrevive solo para el respaldo XDoG, que produce manchas y no líneas.
- **Criterio de aceptación**: no es que el PNG se vea bonito. Es que el **render en papel** se parezca a la persona y que el robot lo dibuje en menos de 150 s. Ese es el número que se discute, no la impresión.

### Lo que ya se midió (RTX 500 Ada Laptop, 4 GB)

- **SD1.5, DreamShaper8 e Inkpunk no sirven**: devuelven ilustración con sombreado en gris, no líneas, y cambian la cara. DreamShaper le borró el bigote al sujeto. Filtran la identidad, que es lo único que no se puede negociar en una cabina.
- 3.48 GB de VRAM y 8.6–10.8 s a 16 pasos: ni siquiera entra en la ruta crítica de 6–8 s.
- **Los 4 GB son máquina de desarrollo, no de producción.** Para FLUX.2 klein o Qwen-Image-Edit a 1024 px hacen falta **16 GB de VRAM**; con 12 GB se puede, con 8 GB se sufre. Mientras tanto el boceto se pide por API.


## Reglas del dueño (no negociables)

- **Rama**: comprobar con `git branch --show-current` antes de tocar nada. Angel Ortega trabaja en su rama, Angel Dittrich en la suya; `main` es producción.
- **Commits**: commits pequeños y temáticos (una funcionalidad, un bug, una integración), nunca uno de 30+ archivos. Después de cada tanda: push a la rama y preguntar si quiere Pull Request a `main`.
- **Diseño**: prohibidos los badges/labels genéricos ("EN VIVO", círculo verde, dots de estado, pills decorativas, pasos "1/4"). El estado se comunica con composición, luz y movimiento.
- Las fotos del robot no se invierten; el filtro blanco es solo para el logo SYSCOM.

## Mapa del repo

- `windows/` — el producto de la cabina. `windows/frontend/` (React 19 + Vite + TS) y `windows/backend/` (FastAPI + OpenCV/ONNX + robot).
- `lab/` — ya **no** es parte del producto: se borró la app del laboratorio al decidir el boceto por IA. Solo quedan ahí unos archivos sin commitear de otro desarrollador (`pipeline/draw.py`, `features.py`, `hatch.py`, `plot.py`, `preview.py`, `silhouette.py`, `tools/`): no son del producto, no se tocan y no están versionados. Los modelos ONNX que usaba se movieron a `windows/backend/models/`.
- `android/` — vacío en esta rama (solo `.gitkeep`); el APK no está aquí.
- `docs/design-standards.md` — describe el portal SYSCOM, **no** esta cabina (sus rutas `frontend/src/...` no existen aquí). Para la cabina manda la sección de diseño de este archivo.

## Comandos

Backend (`windows/backend/`):

```powershell
python -m pytest -q                       # 28 tests, ~1 s, sin modelos (ONNX se cargan perezosos)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
.venv\Scripts\python.exe download_models.py   # ~180 MB a windows/backend/models/ (fuera del repo); MODELS_DIR lo cambia
```

`--reload-dir app` no es opcional: sin él, WatchFiles vigila `.venv` y los reinicios por la telemetría de FastAPI tiran las peticiones en curso.

La key del proveedor va en `windows/backend/.env` (`OPENROUTER_API_KEY`, plantilla en `.env.example`). `SKETCH_PROVIDER=auto|local|openrouter` elige ruta y `SKETCH_DEBUG_DIR=<carpeta>` guarda la referencia, el PNG del modelo y la máscara de cada foto para depurar.

Frontend (`windows/frontend/`): `pnpm install`, `pnpm dev`, `pnpm build` (`tsc -b && vite build`), `pnpm lint`. La API va al mismo origen por defecto; `VITE_API_BASE=http://IP:8000` apunta al PC del robot.

## Pipeline del boceto (`windows/backend/app/pipeline/`)

1. **Proveedor de IA** (`providers.py`): recorta cabeza y hombros con YuNet, manda la referencia a OpenRouter y devuelve una **máscara de tinta** (255 = línea). Binariza con umbral fijo 200 y cierra huecos de 3 px, porque el modelo no dibuja con el mismo grosor en todas las caras. Si el proveedor falla se cae al respaldo XDoG sin romper la pantalla.
2. **Trazador de línea central** (`vectorize.py`): `trim_to_ink` (recorta el aire del lienzo 3:4 para que la cara llene los 140 mm) → `strokes_from_centerline` (`MORPH_CLOSE` → `skeletonize` → `_centerline_paths` → `bridge_aligned_strokes`) → `simplify_and_smooth` (Chaikin + RDP) → `order_strokes` (vecino + 2-opt) → `prune_to_budget` (150 s, reservando el rótulo) → `append_caption` (`caption.py`, escribe SYSCOM ROBOTICS debajo, en trazo simple, y alarga el lienzo sin achicar la cara) → `build_trajectory` (mm, 140 mm de ancho).
3. `robot/client.py` es `MockRobotClient`, sin hardware; `ROBOT_TIME_SCALE=0.2` acelera la demo.
4. **Respaldo sin red** (congelado, no mejorar): `portrait.py` (`PortraitRenderer.render`) → `sketch.lab_portrait_lines` (XDoG + landmarks) → `strokes_from_mask` (contornos).

Trampas que cuestan tiempo:

- `_centerline_paths` camina el esqueleto con **memoria de dirección**: en cada paso elige el vecino que mejor continúa el trazo, así atraviesa los cruces en vez de morir en ellos. Sin memoria, el dibujo se parte en cada intersección.
- Para detectar cruces usa `_crossing_number` (≥3), **no** `_neighbour_count`: con 8 conexiones el vecindario cuenta los escalones del esqueleto como cruces y fragmenta el dibujo en miles de trozos.
- `bridge_aligned_strokes` se vuelve el cuello de botella si hay cientos de trazos: con 1500 trazos tarda ~69 s y con 2600, ~216 s. Si aparece esa lentitud, la causa está en la fragmentación, no en el puenteo.
- El contorno (`strokes_from_mask`) **solo** sirve para manchas (respaldo XDoG). Aplicado a las líneas de la IA recorre los dos bordes y el robot dibuja doble línea.
- Los defaults de los parámetros del respaldo están duplicados en **tres** sitios que hay que cambiar juntos: `SketchParams` (`app/main.py`), `PortraitRenderer.render` (`portrait.py`) y `lab_portrait_lines` (`sketch.py`).
- `TARGET_PX = 900` y la salida de los ONNX se recorta a múltiplos de 4 (si no, el dibujo se desplaza unos píxeles).
- Todo el pipeline trabaja en px del recorte; los mm solo aparecen en `build_trajectory`. La vista previa se dibuja con los mismos trazos que recibe el robot.

## Wizard de la cabina (`windows/`)

Wizard de una sola pantalla, sin scroll. Estados en `src/hooks/usePhotobooth.ts`:

1. `attract` — el robot saluda (`assets/robot/dobotsayinghello.webp`) y el botón COMENZAR.
2. `camera` → `countdown` → `capture` — visor y cuenta regresiva.
3. `review` — se muestra la foto. TOMAR OTRA vuelve a `camera`. ME GUSTA sigue. Todavía no se llama a la IA.
4. `style` — dos grupos, Profesión y Accesorios, un id por grupo. Cada botón lleva icono. CONTINUAR es el único momento de `POST /api/sketch`.
5. `reveal` — la foto entra en iris y se transforma a sketch.
6. `confirm` — "¿Listo para ser dibujado?" con TOMAR OTRA (vuelve a `camera`) a la izquierda y ¡SÍ! a la derecha.
7. `drawing` (3 s, `assets/robot/dobotidlemarker.webp`) → `thanks`: "LISTO. TOMA TU DIBUJO." y "SYSCOM agradece tu visita." Vuelve solo a `attract`.

En `camera`, `review`, `style` y `confirm` se ve un anillo de 3 minutos. Pulsarlo vuelve a llenar el tiempo. Al llegar a cero, todo se reinicia a `attract`.
