"""Calcar una imagen: lo oscuro es tinta, sin modelo y sin el rótulo."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import SketchParams, build_sketch  # noqa: E402


def _linea() -> np.ndarray:
    imagen = np.full((80, 220, 3), 255, np.uint8)
    imagen[36:44, 30:190] = 0
    return imagen


def test_calcar_no_llama_al_modelo_ni_escribe_el_rotulo() -> None:
    resultado = build_sketch(_linea(), SketchParams(), source="ink")

    assert resultado["stats"]["ai"]["provider"] == "tinta"
    assert resultado["stats"]["ai"]["model"] == "calco"
    assert resultado["strokes"], "una línea negra tiene que salir como trazo"
    # El rótulo SYSCOM ROBOTICS son unas veinte letras. Una raya no puede
    # convertirse en eso, ni alargar el lienzo por debajo de la tinta.
    assert len(resultado["strokes"]) < 8
    assert resultado["stats"]["height"] <= 80


def test_un_papel_en_blanco_no_se_calca() -> None:
    blanco = np.full((40, 40, 3), 255, np.uint8)
    with pytest.raises(ValueError, match="líneas oscuras"):
        build_sketch(blanco, SketchParams(), source="ink")
