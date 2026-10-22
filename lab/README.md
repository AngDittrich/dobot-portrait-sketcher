# Lab v2 · foto → fondo → (luego SVG MG400)

Empezado desde cero en CPU, solo OpenCV. Sin ONNX por ahora.

## Arranque

```powershell
cd lab
python -m pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Abrir http://127.0.0.1:8000 → Comenzar (webcam) → Tomar foto → ver recorte sin fondo.

## Qué hay (paso 1)

- `server.py`: `POST /api/remove-bg` (dataURL → cutout PNG + máscara + bbox + tiempos).
- `pipeline/__init__.py`: `BgResult`, utilidades (componente mayor, bbox).
- `pipeline/bg_opencv.py`: cara Haar → rect ampliado (pelo+hombros) → GrabCut → limpieza. Interfaz `remove_background(bgr)`.
- `static/`: UI mínima sin build.
- `samples/`: 4 fotos fixtures locales (no se suben).

## Siguiente (cuando el recorte esté bien)

1. Contorno de la máscara → SVG simple de previsualización.
2. Comparar contra `windows/backend` (140 mm, 80 mm/s) para el formato que espera el MG400.
3. Solo si OpenCV no da el pelo bien → `pipeline/bg_onnx.py` con la misma firma.
