# Dobot Portrait Sketcher

Cabina de fotos: el visitante se toma una foto, una IA la convierte en un dibujo
de líneas y un **Dobot MG400** lo dibuja en papel con plumón.

El sistema completo vive en `windows/`:

| Carpeta | Qué es |
| --- | --- |
| `windows/frontend/` | La app de la cabina: React 19 + Vite + TypeScript. Una sola pantalla, sin scroll. |
| `windows/backend/` | FastAPI + OpenCV/ONNX. Genera el boceto, lo vectoriza y mueve el robot. |
| `windows/backend/models/` | Los ONNX que usa la IA (~8 MB). Fuera del repo: se bajan con `download_models.py`. |
| `assets/` | Imágenes del robot y la marca SYSCOM que muestra la cabina. |
| `ditlab/` | Visor de depuración: muestra la foto y cada capa del boceto. No es el producto. |
| `android/` | Vacío en esta rama. |
| `lab/` | Archivos sin versionar de otro desarrollador. **No se toca.** |

---

## Cómo funciona la visita

El wizard tiene un solo estado a la vez, sin scroll (`src/hooks/usePhotobooth.ts`):

1. `attract` — el robot saluda (`assets/robot/dobotsayinghello.webp`) y aparece COMENZAR.
2. `camera` → `countdown` → `capture` — visor y cuenta regresiva.
3. `review` — se muestra la foto. TOMAR OTRA vuelve a la cámara; ME GUSTA sigue.
4. `style` — retrato, caricatura, anime o cartoon, más profesión y accesorios.
   Aquí, y solo aquí, se pide el boceto a la IA (`POST /api/sketch`).
5. `reveal` — la foto entra en iris y se transforma en el dibujo.
6. `confirm` — «¿Listo para ser dibujado?» con TOMAR OTRA a la izquierda y ¡SÍ! a la derecha.
7. `drawing` → `thanks` — el robot dibuja y la pantalla avisa de que el dibujo ya está.

En `camera`, `review`, `style` y `confirm` corre un anillo de 3 minutos. Si la
persona se va, todo vuelve solo a `attract`.

**Regla de diseño del producto:** nada de badges genéricos («EN VIVO»), puntos de
estado, píldoras decorativas ni pasos «1/4». El estado se comunica con la
composición, la luz y el movimiento.

---

## Cómo se genera el dibujo

Decisión cerrada del producto: **el boceto lo genera un modelo de IA de edición**
(foto → dibujo de líneas). La ruta por umbrales (XDoG) se probó durante días y su
techo son ojos huecos, bigotes tramados y caras que se desalinean; queda
**congelada** como respaldo sin red.

1. **Proveedor** (`app/pipeline/providers.py`): recorta cabeza y hombros con
   YuNet, manda la referencia a OpenRouter y recibe una **máscara de tinta**
   (255 = línea). Binariza a 200 y cierra huecos de 3 px.
   - Principal: `google/gemini-nano-banana-2.1` (~3.8 ¢ y ~11 s por retrato).
   - Respaldo: `openai/gpt-image-2`.
   - Si el proveedor falla, el sistema cae al respaldo XDoG sin romper la pantalla.
2. **Trazador** (`app/pipeline/vectorize.py`): recorta el aire del lienzo para que
   la cara llene los 140 mm → `strokes_from_centerline` (esqueleto + caminata con
   memoria de dirección) → `simplify_and_smooth` → `order_strokes` →
   `prune_to_budget` (150 s) → `append_caption` (SYSCOM ROBOTICS) →
   `build_trajectory` (mm).
3. **Robot** (`app/robot/`): convierte la trayectoria en `MovL` y la dibuja.

Se traza por **línea central**, no por contorno: la IA devuelve líneas de 2-3 px y
recorrer el contorno haría doble línea donde la pluma aprieta (pelo, aros,
solapas). El contorno solo se usa en el respaldo XDoG, que produce manchas.

**Criterio de aceptación:** no es que el PNG se vea bonito, es que el **dibujo en
papel se parezca a la persona** y que el robot tarde **menos de 150 s**.

---

## Puesta en marcha

### Backend

```powershell
cd windows/backend
python -m venv .venv                      # si no existe
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe download_models.py   # ~8 MB de ONNX

copy .env.example .env                    # y pon tu OPENROUTER_API_KEY
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir app
```

`--reload-dir app` no es opcional: sin él, WatchFiles vigila `.venv` y los
reinicios por telemetría tiran las peticiones en curso.

### Frontend

```powershell
cd windows/frontend
pnpm install
pnpm dev        # cabina en http://localhost:5173
pnpm build      # tsc -b && vite build
pnpm lint
```

Por defecto la API va al mismo origen. Para apuntar al PC del robot:
`VITE_API_BASE=http://192.168.10.3:8000`.

---

## Variables de entorno (`windows/backend/.env`)

**Boceto**

| Variable | Para qué |
| --- | --- |
| `OPENROUTER_API_KEY` | Key del proveedor. |
| `SKETCH_PROVIDER` | `openrouter`, `local` o `auto` (prueba local y cae a remoto). |
| `OPENROUTER_SKETCH_MODEL` | Modelo principal (por defecto nano-banana 2.1). |
| `OPENROUTER_SKETCH_FALLBACK` | Modelo de respaldo (por defecto gpt-image-2). |
| `SKETCH_TIMEOUT_S` | Si el proveedor tarda más, se cae al respaldo. |
| `SKETCH_DEBUG_DIR` | Guarda referencia, PNG del modelo y máscara de cada foto. |
| `SAVE_RAW=1` | Guarda la foto cruda en `captures/` para calibrar. |

**Robot**

| Variable | Para qué |
| --- | --- |
| `ROBOT_BACKEND` | `mock` (no mueve nada) o `mg400`. |
| `ROBOT_HOST` | IP del controlador (en la cabina, `192.168.10.55`). |
| `ROBOT_Z_DRAW` / `ROBOT_Z_TRAVEL` | Altura con el plumón apoyado y levantado. **Se miden en la cabina.** |
| `ROBOT_R` | Giro de la muñeca. `90` deja la punta del marcador al frente, a 5-8 cm del centro del tool. |
| `ROBOT_ORIGIN_X` / `ROBOT_ORIGIN_Y` | Solo antes de enseñar las esquinas. El centro de la banda útil es `319.24, -27.20`. |
| `ROBOT_X_SIGN` / `ROBOT_Y_SIGN` | `-1` si esas coordenadas bajan al avanzar por el dibujo. |
| `ROBOT_SPEED_FACTOR` | Porcentaje de velocidad del controlador. |
| `ROBOT_CP_DRAW` | Suavizado de esquinas. `100`; con `0` el brazo frena en cada punto. |
| `ROBOT_ACC_MM_S2` | Aceleración. Techo del firmware: `100` (más da `-40005`). |
| `ROBOT_STEP_MM` | Paso mínimo entre puntos de un trazo (8). |
| `ROBOT_JOIN_MM` | Une trazos más cercanos que esto sin levantar el lápiz (6). |
| `ROBOT_SHEET` | Hoja horizontal: `a6`, `a5`, `media_carta`, `a4` o `carta`. El lado largo va de izquierda a derecha. Las esquinas enseñadas mandan en el tamaño. |
| `ROBOT_PIPELINE` | Órdenes en vuelo (3). |
| `ROBOT_DRY_RUN` | Arma los `MovL` sin abrir socket. |
| `ROBOT_LOG_LEVEL` | `INFO` imprime cada paso; `DEBUG`, todos. |
| `ADMIN_PIN` | PIN del panel admin de la cabina. |

---

## El robot: lo que costó aprender

Todo esto está medido contra el MG400 real, no deducido de la documentación.

- **`Sync()` es tóxico.** Llamarlo tras cada trazo mató las conexiones en la
  primera o segunda llamada, por cualquiera de los dos puertos. Fue la causa de
  que el dibujo se cortara a los 2 s con la pantalla en error.
- **Flujo continuo de `MovL` tumba el socket** a los 2-3 s, sin importar el ritmo.
  Lo único que aguantó 40 órdenes seguidas fue mandar y confirmar la llegada.
- **`-30000` es cola llena**, y llega **pegado al eco** (`-30000MovL(...)`, sin
  coma): hay que parsearlo aparte o se lee como «sin respuesta del controlador».
- **`-99999` no siempre es una conexión muerta:** también aparece cuando la
  lectura expira. Un socket caído da `10053` o una respuesta vacía inmediata.
- **La cola se traba** y el controlador acepta órdenes con código 0 sin mover el
  brazo. `Stop()` devuelve `-10000` y `ClearError()` no basta: se destraba con
  **`ResetRobot()`**, que el cliente manda solo cuando detecta que el brazo no se
  movió ni medio milímetro.
- **La velocidad depende de la aceleración, no de `SpeedL`.** Con `AccL` igual a
  `SpeedL` (20) el brazo no pasaba de 4 mm/s en trazos cortos. Con `AccL=100` y
  pasos de 6 mm llega a ~10 mm/s, y con tres órdenes en vuelo a **19.6 mm/s**.
- **Cada cambio de altura cuesta ~3 s** porque obliga a vaciar la cola. Por eso
  los trazos cercanos se encadenan sin levantar el lápiz.
- **Errores de eje:** una recta larga mal calculada dio `Controller error 18`
  («target position triggers joint limit»). El cliente valida que todo caiga
  dentro del papel antes de moverse.

Con todo eso, el retrato completo (847 órdenes, 110 trazos) se dibujó **entero por
primera vez** sin cortarse; el tiempo sigue por encima de los 150 s y es lo que
se está afinando.

### El área de trabajo, medida

El alcance no es un rectángulo: de frente al fondo manda primero el codo y
después el radio de 440 mm; a lo ancho sobra sitio. Estos son los números
medidos paseando el brazo hasta que un tope lo detuvo (z = -95, R = 90), y son
los que hay que usar como valores por defecto sin volver a calcular:

| | |
|---|---|
| Fondo útil (X) | `199.24` a `439.24` — 240 mm |
| A lo ancho (Y) | `-247.20` a `192.80` — 440 mm |
| Centro de la hoja | `319.24, -27.20` |
| A5 horizontal (210 × 148) | lado largo a lo ancho, lado corto de frente al fondo |
| A4 horizontal (297 × 210) | entra: 210 mm de fondo caben en 240 |

La hoja va **horizontal** y el retrato se queda de pie: arriba es la esquina
que se enseña en el panel, así que no se gira 90°. Con el lado largo de frente
al fondo A4 no entraría (297 mm en un fondo de 240). `R = 90` deja la punta
del marcador al frente, a 5-8 cm del centro del tool; como es un desfase fijo,
el dibujo sale **corrido** ese tanto pero del mismo tamaño.

El botón **Marcar el área** del panel recorre esas cuatro esquinas con el lápiz
arriba: va primero al centro, después al borde y cierra el cuadro, 16 s.

---

## Tests

```powershell
cd windows/backend
python -m pytest -q        # 102 tests, ~3 s, sin modelos: los ONNX cargan perezosos
```

Los tests del robot usan un enlace falso: no hace falta el brazo conectado.
Frontend: `pnpm build` hace de verificación de tipos.

---

## Estado

Funciona: captura, wizard completo, boceto por IA, panel admin con joystick y
dibujo completo sin cortarse.

Pendiente:

- Medir `ROBOT_Z_DRAW` / `ROBOT_Z_TRAVEL` con plumón y papel (las pruebas fueron
  3 mm arriba, sin tocar la hoja).
- Fijar el origen del papel en el `.env` de la cabina (hoy el script de pruebas
  centra el dibujo en la pose actual del brazo).
- Bajar el tiempo del retrato a los 150 s del criterio.
