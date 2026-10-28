"""La actividad del panel admin: pide token, ordena reciente primero y expone el proveedor."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import main  # noqa: E402
from app.admin_ops import drop_tokens, issue_token  # noqa: E402
from app.store import Job, Sketch  # noqa: E402


@pytest.fixture(autouse=True)
def limpia_los_stores():
    main.jobs._items.clear()
    main.sketches._items.clear()
    main.activity_totals.update({"done": 0, "error": 0})
    yield
    main.jobs._items.clear()
    main.sketches._items.clear()
    main.activity_totals.update({"done": 0, "error": 0})


def _token() -> str:
    drop_tokens()
    return issue_token()


def test_la_actividad_pide_token():
    with pytest.raises(main.HTTPException) as excinfo:
        main.admin_activity(x_admin_token=None)
    assert excinfo.value.status_code == 401


def test_los_trabajos_salen_reciente_primero():
    main.jobs.put("job_viejo", Job(id="job_viejo", sketch_id="sk1"))
    main.jobs.put("job_nuevo", Job(id="job_nuevo", sketch_id="sk2"))
    data = main.admin_activity(x_admin_token=_token())
    assert [job["job_id"] for job in data["jobs"]][:2] == ["job_nuevo", "job_viejo"]


def test_el_job_nace_sin_finished_at():
    job = Job(id="job_1", sketch_id="sk1")
    assert job.finished_at is None


def test_el_bloque_provider_tiene_la_forma_del_panel():
    data = main.admin_activity(x_admin_token=_token())
    provider = data["provider"]
    assert provider["configured"] in {"auto", "local", "openrouter"}
    assert isinstance(provider["model"], str)
    assert set(provider["available"]) == {"local", "openrouter"}
    assert provider["available"]["local"] is False
    assert data["totals"] == {"done": 0, "error": 0}


def test_la_miniatura_pide_token():
    with pytest.raises(main.HTTPException) as excinfo:
        main.admin_sketch_preview("sk1", token="", x_admin_token=None)
    assert excinfo.value.status_code == 401


def test_la_miniatura_devuelve_el_png_del_boceto():
    main.sketches.put("sk1", Sketch(id="sk1", preview="data:image/png;base64,aG9sYQ==", svg=""))
    response = main.admin_sketch_preview("sk1", token=_token(), x_admin_token=None)
    assert response.media_type == "image/png"
    assert response.body == b"hola"


def test_la_miniatura_de_un_boceto_que_no_existe_es_404():
    with pytest.raises(main.HTTPException) as excinfo:
        main.admin_sketch_preview("no", token=_token(), x_admin_token=None)
    assert excinfo.value.status_code == 404
