"""Accesorios nuevos y la flor que cambia de oreja.

El modelo tiene un sesgo fijo: con "behind one ear" siempre la dibujaba del
mismo lado, y en la cabina todos los retratos se veían calcados. El lado se
dice explícito y cambia por visita.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.providers import (  # noqa: E402
    TRAIT_LINES,
    build_prompt,
    filter_traits,
)


def test_flor_uses_the_ear_it_is_told():
    prompt = build_prompt(["flor"], "retrato", ear_side="right")
    assert "behind the right ear" in prompt
    assert "behind the left ear" not in prompt


def test_flor_picks_a_side_on_its_own():
    sides = {build_prompt(["flor"], "retrato") for _ in range(40)}
    joined = " ".join(sides)
    assert "behind the right ear" in joined
    assert "behind the left ear" in joined


def test_flower_never_lands_over_glasses_or_face():
    prompt = build_prompt(["flor"], "retrato", ear_side="left")
    assert "never over the glasses or the face" in prompt


def test_new_accessories_reach_the_prompt():
    for trait, word in (("aretes", "earring"), ("diadema", "headband")):
        assert trait in TRAIT_LINES
        assert word in build_prompt([trait], "cartoon")


def test_earrings_step_aside_for_headphones():
    # Los audífonos tapan la oreja: pedir ambos dibuja dos cosas encimadas.
    assert filter_traits(["musico", "aretes"]) == ["musico"]


def test_two_hair_pieces_do_not_stack():
    assert len(filter_traits(["flor", "diadema"])) == 1


def test_prompt_has_no_leftover_placeholder():
    prompt = build_prompt(["flor"], "anime", ear_side="right")
    assert not re.search(r"\{|\}", prompt)
