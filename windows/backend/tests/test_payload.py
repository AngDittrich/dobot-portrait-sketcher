"""El pedido a la API solo lleva lo que el modelo acepta.

Mandarlo todo costó una corrida entera de pruebas: gpt-image-1-mini respondió
400 por `aspect_ratio` 3:4 y ese intento se cobra igual.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.providers import build_payload  # noqa: E402

REF = "data:image/jpeg;base64,AAAA"

# Tal como los declara el catálogo de OpenRouter.
NANO_BANANA = {
    "resolution": {"type": "enum", "values": ["1K", "2K", "4K"]},
    "aspect_ratio": {"type": "enum", "values": ["1:1", "3:4", "4:3"]},
    "n": {"type": "range", "min": 1, "max": 1},
    "input_references": {"type": "range", "min": 0, "max": 14},
}

FLUX_KLEIN = {
    "aspect_ratio": {"type": "enum", "values": ["1:1", "3:4", "4:3"]},
    "n": {"type": "range", "min": 1, "max": 4},
}

GPT_IMAGE_MINI = {
    "aspect_ratio": {"type": "enum", "values": ["1:1", "3:2", "2:3", "auto"]},
    "n": {"type": "range", "min": 1, "max": 10},
}


def test_modelo_completo_lleva_los_cuatro_parametros():
    payload = build_payload("google/gemini-nano-banana-2.1", NANO_BANANA, "p", REF)
    assert payload["resolution"] == "1K"
    assert payload["aspect_ratio"] == "3:4"
    assert payload["n"] == 1
    assert payload["input_references"][0]["image_url"]["url"] == REF


def test_sin_resolution_se_omite_pero_se_conserva_el_resto():
    payload = build_payload("black-forest-labs/flux.2-klein-4b", FLUX_KLEIN, "p", REF)
    assert "resolution" not in payload
    assert payload["aspect_ratio"] == "3:4"


def test_aspect_ratio_no_soportado_se_omite():
    payload = build_payload("openai/gpt-image-1-mini", GPT_IMAGE_MINI, "p", REF)
    assert "aspect_ratio" not in payload
    assert "resolution" not in payload
    assert payload["n"] == 1


def test_modelo_desconocido_solo_lleva_lo_indispensable():
    payload = build_payload("modelo/raro", {}, "p", REF)
    assert set(payload) == {"model", "prompt", "input_references"}


def test_catalogo_caido_manda_el_pedido_de_siempre():
    payload = build_payload("google/gemini-nano-banana-2.1", None, "p", REF)
    assert payload["resolution"] == "1K"
    assert payload["aspect_ratio"] == "3:4"
    assert payload["output_format"] == "png"
