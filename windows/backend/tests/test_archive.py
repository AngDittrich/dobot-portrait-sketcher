"""El archivo de visitas guarda las etapas y no acepta rutas ajenas."""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import archive as archive_ops  # noqa: E402


def test_una_visita_guarda_las_etapas_que_llegaron(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(archive_ops, "ARCHIVE_DIR", tmp_path)
    image = np.full((8, 8, 3), 255, dtype=np.uint8)
    raw = b"\x89PNG\r\n"

    folder = archive_ops.save_visit(
        "sk_abc1234567",
        {"01-original.jpg": image, "03-ia.png": raw, "06-vector.png": image},
        {
            "model": "google/gemini-nano-banana-2.1",
            "strokes_before": 98,
            "strokes_after": 40,
            "estimated_seconds": 150.0,
            "notes": {"06-vector.png": "40 trazos, estimado 150.0 s."},
        },
    )

    saved = tmp_path / folder
    assert (saved / "01-original.jpg").is_file()
    assert (saved / "03-ia.png").read_bytes() == raw
    assert not (saved / "02-referencia.png").exists()
    meta = json.loads((saved / "meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "google/gemini-nano-banana-2.1"
    assert meta["strokes_before"] == 98
    names = [step["file"] for step in meta["steps"]]
    assert names == ["01-original.jpg", "03-ia.png", "06-vector.png"]
    assert meta["steps"][-1]["note"] == "40 trazos, estimado 150.0 s."

    visits = archive_ops.list_visits()
    assert visits[0]["folder"] == folder
    assert archive_ops.image_path(folder, "03-ia.png") == (saved / "03-ia.png").resolve()


def test_un_nombre_ajeno_no_abre_un_archivo(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(archive_ops, "ARCHIVE_DIR", tmp_path)
    assert archive_ops.image_path("../.env", "01-original.jpg") is None
    assert archive_ops.image_path("20261030_093012_sk_abc1234567", "../meta.json") is None
    assert archive_ops.image_path("20261030_093012_sk_abc1234567", "01-original.jpg") is None
