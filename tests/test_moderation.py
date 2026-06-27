"""Tests de la orquestación de moderación (app/moderation.py).

No cargan modelos reales: se mockean los detectores para validar la lógica de
`moderar()` (NSFW corta primero, gore marca flag, y el switch de habilitado/deshabilitado).
"""

import app.moderation as moderation
from app.config import get_settings


def _reset_settings_cache():
    get_settings.cache_clear()


def test_moderacion_deshabilitada_devuelve_limpio(monkeypatch):
    """Con MODERATION_ENABLED=false, moderar() no llama a ningún detector."""
    monkeypatch.setenv("MODERATION_ENABLED", "false")
    _reset_settings_cache()

    def _boom(*a, **k):  # no debe llamarse
        raise AssertionError("no debería correr ningún detector")

    monkeypatch.setattr(moderation, "_detectar_nsfw", _boom)
    monkeypatch.setattr(moderation, "_detectar_sensible", _boom)

    v = moderation.moderar(b"cualquier-cosa")
    assert v.nsfw is False
    assert v.sensible is False
    _reset_settings_cache()


def test_nsfw_corta_antes_de_gore(monkeypatch):
    """Si es NSFW, se devuelve nsfw=True sin evaluar gore."""
    monkeypatch.setenv("MODERATION_ENABLED", "true")
    _reset_settings_cache()

    monkeypatch.setattr(
        moderation,
        "_detectar_nsfw",
        lambda data, umbral: (True, 0.9, ["FEMALE_BREAST_EXPOSED"]),
    )

    def _no_gore(*a, **k):
        raise AssertionError("gore no debe evaluarse si ya es NSFW")

    monkeypatch.setattr(moderation, "_detectar_sensible", _no_gore)

    v = moderation.moderar(b"img")
    assert v.nsfw is True
    assert v.sensible is False
    assert v.etiquetas == ["FEMALE_BREAST_EXPOSED"]
    _reset_settings_cache()


def test_gore_marca_flag_sin_nsfw(monkeypatch):
    """No NSFW pero con gore: nsfw=False, sensible=True con etiquetas."""
    monkeypatch.setenv("MODERATION_ENABLED", "true")
    _reset_settings_cache()

    monkeypatch.setattr(moderation, "_detectar_nsfw", lambda data, umbral: (False, 0.0, []))
    monkeypatch.setattr(
        moderation,
        "_detectar_sensible",
        lambda data, umbral: (True, 0.8, ["a graphic photo with blood and gore"]),
    )

    v = moderation.moderar(b"img")
    assert v.nsfw is False
    assert v.sensible is True
    assert v.sensible_score == 0.8
    assert "blood" in v.etiquetas[0]
    _reset_settings_cache()


def test_imagen_limpia(monkeypatch):
    """Sin NSFW ni gore: veredicto totalmente limpio."""
    monkeypatch.setenv("MODERATION_ENABLED", "true")
    _reset_settings_cache()

    monkeypatch.setattr(moderation, "_detectar_nsfw", lambda data, umbral: (False, 0.0, []))
    monkeypatch.setattr(moderation, "_detectar_sensible", lambda data, umbral: (False, 0.1, []))

    v = moderation.moderar(b"img")
    assert v.nsfw is False
    assert v.sensible is False
    _reset_settings_cache()
