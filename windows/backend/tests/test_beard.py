"""Banda de barba: umbral estricto donde la barba corta hace grumos."""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline.sketch import beard_threshold_map, drop_isolated_blobs


def _landmarks(lip_y=60.0, chin_y=100.0, n=478):
    lm = np.zeros((n, 2), np.float32)
    lm[13] = (50.0, lip_y)   # UPPER_LIP
    lm[152] = (50.0, chin_y)  # CHIN
    return lm


def test_band_uses_strict_threshold_inside():
    zone = np.ones((120, 100), np.float32)
    m = beard_threshold_map(zone, _landmarks(), bg=0.28, face=0.12, beard=0.45)
    assert m.shape == zone.shape
    assert m[80, 50] == 0.45  # dentro de la banda labio->menton
    assert m[30, 50] == pytest.approx(0.12)  # cara arriba: umbral suave


def test_band_applies_below_chin_and_outside_stays_bg():
    zone = np.zeros((120, 100), np.float32)
    m = beard_threshold_map(zone, _landmarks(), bg=0.28, face=0.12, beard=0.45)
    assert m[80, 50] == 0.45
    assert m[10, 5] == 0.28  # arriba del labio: fondo


def test_none_landmarks_returns_base_map():
    zone = np.full((120, 100), 0.5, np.float32)
    m = beard_threshold_map(zone, None, bg=0.28, face=0.12, beard=0.45)
    assert np.allclose(m, 0.28 - (0.28 - 0.12) * 0.5)


def _ink_with_dot_and_bar():
    ink = np.zeros((100, 100), np.uint8)
    ink[50:55, 50:55] = 255  # puntito flotante 5x5
    ink[80, 10:90] = 255  # linea larga (boca/menton)
    touch = np.zeros((100, 100), bool)
    touch[78:83, :] = True  # la barra toca un rasgo
    band = np.zeros((100, 100), bool)
    band[40:, :] = True
    return ink, band, touch


def test_drop_isolated_blobs_kills_small_floaters():
    ink, band, touch = _ink_with_dot_and_bar()
    out = drop_isolated_blobs(ink, band, touch, max_area=80)
    assert out[50:55, 50:55].sum() == 0  # el punto muere
    assert (out[80, 10:90] == 255).all()  # la barra vive


def test_drop_isolated_blobs_keeps_big_ones():
    ink = np.zeros((100, 100), np.uint8)
    ink[50:70, 40:60] = 255  # mancha 20x20 = 400 px
    band = np.zeros((100, 100), bool)
    band[:, :] = True
    out = drop_isolated_blobs(ink, band, np.zeros((100, 100), bool), max_area=80)
    assert (out[50:70, 40:60] == 255).all()
