"""El prompt de caricatura solo acepta ids conocidos."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.providers import PROMPT, build_prompt  # noqa: E402


def test_sin_rasgos_es_el_prompt_base():
    assert build_prompt(None) == PROMPT
    assert build_prompt([]) == PROMPT


def test_rasgo_conocido_se_agrega_y_el_desconocido_no():
    # Antes llevaba una corona, pero el chef ya ocupa la cabeza: dos sombreros
    # sobre el mismo cráneo es justo lo que ahora se descarta.
    prompt = build_prompt(["chef", "inventado", "lentes"])
    assert "plain toque" in prompt
    assert "round glasses" in prompt
    assert "inventado" not in prompt
    assert "NO hatching" in prompt


def test_oficio_y_accesorio_nuevos():
    prompt = build_prompt(["piloto", "lentes", "no-existe"])
    assert "peaked cap" in prompt
    assert "round glasses" in prompt
    assert "no-existe" not in prompt


def test_estilo_conocido_cambia_el_inicio():
    anime = build_prompt([], "anime")
    assert "anime line art" in anime
    assert "NO hatching" in anime
    assert "Slightly exaggerate" not in anime


def test_estilo_desconocido_sigue_siendo_caricatura():
    assert build_prompt(None, "oleo") == PROMPT
    assert build_prompt(["chef"], "caricatura") != PROMPT
    assert "plain toque" in build_prompt(["chef"], "retrato")
