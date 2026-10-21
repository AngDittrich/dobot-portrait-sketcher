# Windows · Cabina de Retratos

Proyecto de Windows: la cabina web que toma la foto, la convierte en boceto y
manda al robot Dobot MG400 a dibujarlo en papel.

```
windows/
├── frontend/   React 19 + Vite + TypeScript (la cabina de fotos)
└── backend/    Python + FastAPI + OpenCV/ONNX (boceto, vector y robot)
```

## Arranque rápido (dos terminales)

**1. Backend** (necesita los modelos ONNX, ver `backend/README.md`):

```powershell
cd windows/backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000 --reload
```

**2. Frontend**:

```powershell
cd windows/frontend
pnpm install
pnpm dev
```

La cabina queda en <http://localhost:5173> y el proxy de Vite manda `/api` al
backend en `http://127.0.0.1:8000`.

Para apuntar el frontend a otro equipo (por ejemplo, el PC con el robot
conectado) se define `VITE_API_BASE=http://IP_DEL_PC:8000`.

## Qué hace cada parte

- `frontend/` → captura con la webcam, cuenta regresiva, vista previa del
  boceto, aprobación y seguimiento del trabajo del robot.
- `backend/` → `POST /api/sketch` (foto → boceto en líneas + SVG + trazos) y
  `POST /api/jobs` (boceto → trabajo de dibujo) / `GET /api/jobs/{id}`
  (progreso). Hoy el robot es un simulador (`MockRobotClient`); falta
  enchufar el driver TCP/IP real del MG400.
