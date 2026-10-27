# Ditlab

Una foto y cada capa del boceto que dibuja la cabina. El código es el de `windows/backend` (YuNet, U2Net, XDoG, vectorizado). `lab/` no se toca.

## Arranque

Con el entorno del backend, que ya tiene OpenCV, ONNX, MediaPipe y los modelos:

```powershell
cd ditlab
..\windows\backend\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8010 --reload
```

Abrir http://127.0.0.1:8010

Si faltan modelos: `windows/backend/download_models.py`, o la variable `MODELS_DIR`.

Los controles de abajo rehacen el boceto y los trazos. No vuelven a correr U2Net.
