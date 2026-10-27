"""Un rasgo por espacio del cuerpo.

El caso real: el visitante elige bombero y además gorro, y el modelo dibuja
dos sombreros sobre la misma cabeza. El backend no confía en que el frontend
lo haya evitado.
"""

from app.pipeline import providers


def test_hat_on_top_of_firefighter_is_dropped():
    kept = providers.filter_traits(["bombero", "gorra"])
    assert kept == ["bombero"]


def test_costume_wins_even_if_the_hat_comes_first():
    assert providers.filter_traits(["gorra", "bombero"]) == ["bombero"]


def test_accessories_in_different_slots_live_together():
    assert providers.filter_traits(["bombero", "lentes"]) == ["bombero", "lentes"]


def test_two_hats_never_survive_together():
    assert providers.filter_traits(["sombrero", "corona"]) == ["sombrero"]


def test_flower_and_crown_are_different_slots():
    assert providers.filter_traits(["corona", "flor"]) == ["corona", "flor"]


def test_unknown_ids_are_ignored():
    assert providers.filter_traits(["dragon", "mono"]) == ["mono"]


def test_prompt_never_asks_for_two_heads_of_headwear():
    prompt = providers.build_prompt(["bombero", "gorra", "sombrero"], "caricatura")
    assert "firefighter" in prompt
    assert "baseball cap" not in prompt
    assert "wide-brim hat" not in prompt


def test_caricature_asks_for_an_exaggerated_but_drawable_paper():
    prompt = providers.build_prompt(None, "caricatura")
    assert "caricature" in prompt
    assert "oversized" in prompt
    assert "no scenery" in prompt
    assert "NO hatching" in prompt
