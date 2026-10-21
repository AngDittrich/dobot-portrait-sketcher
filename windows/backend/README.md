# Backend de la Cabina de Retratos

API en Python (FastAPI) que convierte la foto de la cabina en un boceto de
líneas y prepara la trayectoria que dibuja el Dobot MG400.

## Qué hace

1. **Foto -> retrato**: U2Net (persona) ∩ elipse de la cara (YuNet) deja la
   cabeza sin fondo ni ropa.
2. **Líneas**: XDoG + landmarks de MediaPipe (mandíbula, cejas, ojos, nariz,
   labios) → máscara de líneas de 1 px.
3. **Vector**: thinning (esqueleto) → polilíneas → RDP → orden de dibujo
   (vecino más cercano + 2-opt).
4. **Trayectoria**: puntos en milímetros (el ancho del dibujo es
   configurable, 140 mm por defecto) y segmentos `draw` / `travel`.

## Puesta en marcha

```powershell
cd windows\backend
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe download_models.py
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Los modelos (unos 180 MB) no están en el repo: `download_models.py` los deja
en `windows/backend/models/`. Si ya están descargados en otro sitio, se puede
apuntar con la variable de entorno `MODELS_DIR`.

## API

| Método | Ruta | Qué hace |
| --- | --- | --- |
| `GET` | `/api/health` | Estado del backend y de los modelos |
| `POST` | `/api/sketch` | Foto (data URL) → boceto + SVG + trayectoria |
| `POST` | `/api/jobs` | Boceto aprobado → trabajo de dibujo |
| `GET` | `/api/jobs/{id}` | Progreso del trabajo |

`POST /api/sketch`:

```json
{ "image": "data:image/jpeg;base64,...", "params": { "target_width_mm": 140 } }
```

Respuesta: `{ "id": "sk_...", "image": "data:image/png;base64,...",
"svg": "<svg .../>", "stats": {...}, "strokes": [...] }`.

`POST /api/jobs` acepta `{ "sketch_id": "sk_..." }` (o `image` para procesar
la foto otra vez) y devuelve `{ "job_id": "job_...", "status": "drawing" }`.

## Robot

Hoy el "robot" es `MockRobotClient`: reproduce la misma línea de tiempo que
el MG400 (misma velocidad, mismos viajes con el lápiz arriba) sin hardware.
`ROBOT_TIME_SCALE=0.2` acelera la demo. Cuando llegue el robot, se añade
`MG400Client` en `app/robot/client.py` con el SDK TCP/IP oficial
(Dobot-Arm/TCP-IP-4Axis-Python) sin tocar la API.
