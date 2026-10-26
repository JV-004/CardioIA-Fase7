"""Inferência do modelo de pico_risco — contrato com o Agente Analista de Risco.

    from predict import prever_risco
    prever_risco({"idade_media": 62, ..., "disponibilidade_recursos": 25})  # -> float entre 0 e 1
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

DIR_MODELO = Path(__file__).resolve().parent
CAMINHO_MODELO = DIR_MODELO / "modelo_pico_risco.joblib"
CAMINHO_FEATURES = DIR_MODELO / "features.json"


@lru_cache(maxsize=None)
def carregar_modelo(caminho=None):
    """Carrega o Pipeline treinado (uma vez por processo; resultado fica em cache)."""
    # joblib usa pickle: carregar apenas o .joblib gerado por treinar.py, nunca arquivo de terceiros.
    return joblib.load(Path(caminho) if caminho else CAMINHO_MODELO)


@lru_cache(maxsize=None)
def carregar_features() -> tuple:
    """Colunas na ordem usada no treino."""
    return tuple(json.loads(CAMINHO_FEATURES.read_text(encoding="utf-8")))


def _normalizar_chave(chave: str) -> str:
    # " Disponibilidade  recursos " -> "disponibilidade_recursos"
    return "_".join(str(chave).strip().lower().split())


def prever_risco(paciente: dict) -> float:
    """Probabilidade (0 a 1) de pico de risco para um paciente.

    Chaves são normalizadas (strip, minúsculas, espaços -> "_"); chaves extras são ignoradas.
    Levanta ValueError se faltar feature, se houver chave duplicada após normalizar
    ou se algum valor não for numérico.
    """
    if not isinstance(paciente, dict):
        raise ValueError(f"paciente deve ser dict, recebido {type(paciente).__name__}")

    normalizado = {}
    for chave, valor in paciente.items():
        nova = _normalizar_chave(chave)
        if nova in normalizado:
            raise ValueError(f"Chave duplicada após normalização: '{chave}' -> '{nova}'")
        normalizado[nova] = valor

    features = carregar_features()
    faltando = [f for f in features if f not in normalizado]
    if faltando:
        raise ValueError(f"Features ausentes: {faltando}. Esperadas: {list(features)}")

    linha = {}
    for f in features:
        try:
            v = float(normalizado[f])
        except (TypeError, ValueError):
            raise ValueError(f"Valor não numérico para '{f}': {normalizado[f]!r}") from None
        if math.isnan(v) or math.isinf(v):
            raise ValueError(f"Valor inválido para '{f}': {v}")
        linha[f] = v

    X = pd.DataFrame([linha], columns=list(features))
    return float(carregar_modelo().predict_proba(X)[0, 1])


if __name__ == "__main__":
    exemplo = {
        "idade_media": 62, "carga_sistema": 92, "tempo_espera": 75, "fc_media": 118,
        "spo2_media": 89, "pa_sistolica": 100, "temperatura": 37.5,
        "densidade_eventos": 7, "eventos_24h": 5, "disponibilidade recursos": 25,
    }
    print(f"RISCO PREVISTO: {prever_risco(exemplo):.2f}")
