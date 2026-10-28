"""Descarga los pesos que usa el backend.

Uso:
    .venv\\Scripts\\python.exe download_models.py

Los archivos quedan en `windows/backend/models/` y están excluidos de git
(son unos 9 MB: detección de cara, U2Net de retrato y landmarks). Se puede
apuntar a otra carpeta con la variable de entorno MODELS_DIR.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

MODELS = {
    # Detector de rostro de OpenCV Zoo (~230 KB)
    "yunet": (
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "face_detection_yunet_2023mar.onnx",
    ),
    # El que usa la cabina y el respaldo: U2Net retrato, 320 px (~4.7 MB).
    "u2netp": (
        "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
        "u2netp.onnx",
    ),
    # Landmarks faciales de MediaPipe (~3.7 MB)
    "face_landmarker": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
        "face_landmarker.task",
        "face_landmarker.task",
    ),
    # Modelo de line art (Paint2Sketch, Apache-2.0): convierte la foto en un
    # boceto a lapiz con pelo, barba y textura (~17 MB)
    "line_drawings": (
        "https://huggingface.co/Luoaho/image-to-line-drawing-onnx/resolve/main/line-drawings.onnx",
        "line-drawings.onnx",
    ),
}


def download(name: str, url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"[ok] {name}: ya existe ({dest.stat().st_size / 1e6:.1f} MB)")
        return

    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"[..] {name}: descargando {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as response, open(tmp, "wb") as fh:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r     {done / 1e6:6.1f} / {total / 1e6:6.1f} MB", end="")
    tmp.replace(dest)
    print(f"\n[ok] {name}: {dest} ({dest.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    root = Path(__file__).resolve().parent
    models_dir = root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    only = set(sys.argv[1:])
    for name, (url, filename) in MODELS.items():
        if only and name not in only:
            continue
        try:
            download(name, url, models_dir / filename)
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {name}: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
