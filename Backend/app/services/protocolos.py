"""Protocolos clínicos da F6, como dados + função pura.

Os limiares foram implementados literalmente como definidos na F6, incluindo o de SpO2
(< 88). O enunciado da F6 traz um exemplo inconsistente com esse limiar; ele NÃO foi
"corrigido" aqui (ver README).
"""
import operator
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Protocolo:
    codigo: str
    feature: Optional[str]  # None = regra baseada na faixa de risco
    operador: str  # "<" ou ">"
    limiar: float
    acao: str
    rotulo_oled: str  # ASCII, <= 21 caracteres


_OPERADORES = {"<": operator.lt, ">": operator.gt}

PROTOCOLOS: tuple[Protocolo, ...] = (
    Protocolo("suporte_respiratorio", "spo2_media", "<", 88,
              "Suporte respiratório imediato", "Suporte respiratorio"),
    Protocolo("unidades_temporarias", "carga_sistema", ">", 85,
              "Abrir unidades temporárias", "Abrir unid. temp."),
    Protocolo("monitoramento_intensivo", "fc_media", ">", 120,
              "Monitoramento intensivo", "Monitor. intensivo"),
    Protocolo("resposta_rapida", "eventos_24h", ">", 5,
              "Acionar equipe de resposta rápida", "Equipe resp. rapida"),
    Protocolo("redistribuir_insumos", "disponibilidade_recursos", "<", 30,
              "Redistribuir insumos", "Redistribuir insumos"),
    Protocolo("triagem_emergencial", "tempo_espera", ">", 90,
              "Priorizar triagem emergencial", "Triagem emergencial"),
    Protocolo("protocolo_infeccioso", "temperatura", ">", 38,
              "Protocolo infeccioso", "Protocolo infeccioso"),
    Protocolo("plano_contingencia", "densidade_eventos", ">", 6,
              "Plano de contingência", "Plano contingencia"),
    Protocolo("protocolo_choque", "pa_sistolica", "<", 90,
              "Protocolo de choque", "Protocolo de choque"),
)

PROTOCOLO_EMERGENCIA = Protocolo(
    "estado_emergencia", None, "==", 0, "Ativar estado de emergência", "ESTADO DE EMERGENCIA"
)


def avaliar_protocolos(features: dict[str, float], faixa: str) -> list[Protocolo]:
    """Retorna os protocolos acionados, na ordem da tabela (emergência por último)."""
    acionados = [
        p for p in PROTOCOLOS
        if p.feature in features and _OPERADORES[p.operador](features[p.feature], p.limiar)
    ]
    if faixa == "alto":
        acionados.append(PROTOCOLO_EMERGENCIA)
    return acionados
