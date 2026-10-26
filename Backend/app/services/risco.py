"""Avaliação de risco: monta as features, chama o modelo F6, classifica e aplica protocolos."""
import unicodedata
from typing import Optional

from app.config import (
    AVISO, CONTEXTO_PADRAO, MAPA_SENSOR_FEATURE, SINAIS_PADRAO, Settings,
)
from app.schemas import ResultadoRisco
from app.services.protocolos import avaliar_protocolos
from modelo.predict import carregar_modelo, prever_risco

LARGURA_OLED = 21
COR_POR_FAIXA = {"baixo": "verde", "moderado": "amarelo", "alto": "vermelho"}


class ModeloIndisponivel(RuntimeError):
    pass


def carregar() -> bool:
    """Carrega o modelo uma vez (cache do predict.py). Retorna False se falhar."""
    try:
        carregar_modelo()
        return True
    except Exception:
        return False


def montar_features(
    sinais: dict[str, Optional[float]],
    contexto: Optional[dict[str, Optional[float]]] = None,
    usar_sinais_padrao: bool = False,
) -> tuple[dict[str, float], list[str]]:
    """Combina sinais do sensor + contexto + padrões. Devolve (features, features_padrao).

    Prioridade: sinal do sensor > contexto da requisição > valor padrão.
    `sinais` usa os nomes do sensor (bpm, temperatura, spo2) ou já os nomes das features.
    """
    features: dict[str, float] = {}
    for chave, valor in (contexto or {}).items():
        if valor is not None:
            features[chave] = float(valor)
    for chave, valor in sinais.items():
        if valor is not None:
            features[MAPA_SENSOR_FEATURE.get(chave, chave)] = float(valor)

    padroes = {**CONTEXTO_PADRAO, **(SINAIS_PADRAO if usar_sinais_padrao else {})}
    features_padrao = []
    for chave, valor in padroes.items():
        if chave not in features:
            features[chave] = float(valor)
            features_padrao.append(chave)
    return features, features_padrao


def classificar_faixa(risco: float, settings: Settings) -> str:
    if risco >= settings.limiar_alto:
        return "alto"
    if risco >= settings.limiar_moderado:
        return "moderado"
    return "baixo"


def _ascii(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def linhas_oled(risco: float, faixa: str, features: dict[str, float], rotulos: list[str]) -> list[str]:
    """4 linhas para o SSD1306 128x64 (fonte 8x8 = 21 colunas úteis com margem)."""
    linhas = [
        f"Risco {risco * 100:.0f}% {faixa.upper()}",
        f"FC{features['fc_media']:.0f} T{features['temperatura']:.1f} O2 {features['spo2_media']:.0f}",
        f"Protocolos: {len(rotulos)}",
        rotulos[0] if rotulos else "Sem protocolos",
    ]
    return [_ascii(linha)[:LARGURA_OLED] for linha in linhas]


def enriquecer_com_agentes(features: dict[str, float], resultado: ResultadoRisco) -> ResultadoRisco:
    """PONTO DE EXTENSÃO — orquestrador multiagente da F6 (não implementado nesta fase).

    Para plugar os agentes da F6 (Analista de Risco, Planejador de Protocolos etc.):
      1. copie o pacote dos agentes para Backend/agentes/ (o código não está neste repo);
      2. aqui, chame o orquestrador com `features` e `resultado.risco` e devolva um
         `resultado.model_copy(update={...})` com as recomendações enriquecidas;
      3. mantenha `aviso` e `features_padrao` — a UI depende deles.
    Não adicione dependência de LLM externo sem atualizar requirements.txt e .env.example.
    Hoje devolve o resultado sem alterações.
    """
    return resultado


def avaliar(features: dict[str, float], features_padrao: list[str], settings: Settings) -> ResultadoRisco:
    try:
        risco = prever_risco(features)
    except ValueError:
        raise
    except Exception as exc:  # arquivo ausente, versão incompatível do scikit-learn etc.
        raise ModeloIndisponivel("Modelo preditivo indisponível no servidor.") from exc

    faixa = classificar_faixa(risco, settings)
    protocolos = avaliar_protocolos(features, faixa)
    # No OLED só cabe um rótulo: o de emergência (último da lista) tem prioridade.
    rotulos_oled = [p.rotulo_oled for p in reversed(protocolos)] if faixa == "alto" else [
        p.rotulo_oled for p in protocolos
    ]
    resultado = ResultadoRisco(
        risco=round(risco, 4),
        faixa=faixa,
        led=COR_POR_FAIXA[faixa],
        oled=linhas_oled(risco, faixa, features, rotulos_oled),
        protocolos_acionados=[p.codigo for p in protocolos],
        recomendacoes=[p.acao for p in protocolos],
        features=features,
        features_padrao=features_padrao,
        aviso=AVISO,
    )
    return enriquecer_com_agentes(features, resultado)
