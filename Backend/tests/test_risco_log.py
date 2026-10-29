"""Falhas do modelo F6 ficam registradas no log com a causa (antes eram engolidas)."""
import logging

import pytest

from app.config import Settings
from app.services import risco

CAUSA = "arquivo .joblib corrompido (teste)"


def _quebrar(*_, **__):
    raise OSError(CAUSA)


def test_carregar_registra_causa_e_retorna_false(monkeypatch, caplog):
    monkeypatch.setattr(risco, "carregar_modelo", _quebrar)
    with caplog.at_level(logging.ERROR, logger="app.services.risco"):
        assert risco.carregar() is False
    registro = caplog.records[-1]
    assert "Falha ao carregar o modelo" in registro.getMessage()
    assert registro.exc_info and CAUSA in str(registro.exc_info[1])


def test_avaliar_registra_causa_e_levanta_modelo_indisponivel(monkeypatch, caplog):
    monkeypatch.setattr(risco, "prever_risco", _quebrar)
    features, padrao = risco.montar_features({"bpm": 72, "temperatura": 36.5})
    with caplog.at_level(logging.ERROR, logger="app.services.risco"), \
            pytest.raises(risco.ModeloIndisponivel):
        risco.avaliar(features, padrao, Settings(_env_file=None))
    registro = caplog.records[-1]
    assert "Falha ao executar o modelo" in registro.getMessage()
    assert registro.exc_info and CAUSA in str(registro.exc_info[1])


def test_valueerror_do_modelo_nao_vira_modelo_indisponivel(monkeypatch, caplog):
    def _valor_invalido(*_, **__):
        raise ValueError("feature ausente")

    monkeypatch.setattr(risco, "prever_risco", _valor_invalido)
    features, padrao = risco.montar_features({"bpm": 72, "temperatura": 36.5})
    with caplog.at_level(logging.ERROR, logger="app.services.risco"), pytest.raises(ValueError):
        risco.avaliar(features, padrao, Settings(_env_file=None))
    assert not caplog.records  # erro de entrada não é falha do modelo
