"""El prompt de caricatura solo acepta ids conocidos."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.providers import PROMPT, build_prompt  # noqa: E402


def test_sin_rasgos_es_el_prompt_base():
    assert build_prompt(None) == PROMPT
    assert build_prompt([]) == PROMPT


def test_rasgo_conocido_se_agrega_y_el_desconocido_no():
    prompt = build_prompt(["chef", "inventado", "corona"])
    assert "plain toque" in prompt
    assert "three-point crown" in prompt
    assert "inventado" not in prompt
    assert "NO hatching" in prompt


def test_oficio_y_accesorio_nuevos():
    prompt = build_prompt(["piloto", "lentes", "no-existe"])
    assert "peaked cap" in prompt
    assert "round glasses" in prompt
    assert "no-existe" not in prompt
