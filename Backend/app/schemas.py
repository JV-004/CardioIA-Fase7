"""Modelos de entrada e saída da API (pydantic v2)."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def normalizar_chave(chave: str) -> str:
    """Mesma regra do predict.py da F6: " Disponibilidade  recursos " -> "disponibilidade_recursos"."""
    return "_".join(str(chave).strip().lower().split())


class _ChavesNormalizadas(BaseModel):
    """Aceita chaves com espaços/maiúsculas e rejeita chaves desconhecidas ou duplicadas."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalizar(cls, dados: Any) -> Any:
        if not isinstance(dados, dict):
            return dados
        normalizado = {}
        for chave, valor in dados.items():
            nova = normalizar_chave(chave)
            if nova in normalizado:
                raise ValueError(f"Chave duplicada após normalização: '{chave}' -> '{nova}'")
            normalizado[nova] = valor
        return normalizado


class Contexto(_ChavesNormalizadas):
    """Features do modelo que o sensor não mede. Todas opcionais."""

    idade_media: Optional[float] = Field(None, ge=0, le=120)
    carga_sistema: Optional[float] = Field(None, ge=0, le=100)
    tempo_espera: Optional[float] = Field(None, ge=0, le=1440)
    spo2_media: Optional[float] = Field(None, ge=50, le=100)
    pa_sistolica: Optional[float] = Field(None, ge=40, le=260)
    densidade_eventos: Optional[float] = Field(None, ge=0, le=100)
    eventos_24h: Optional[float] = Field(None, ge=0, le=1000)
    disponibilidade_recursos: Optional[float] = Field(None, ge=0, le=100)


class EntradaRisco(Contexto):
    """POST /api/risco: as 10 features do modelo, parciais ou completas."""

    fc_media: Optional[float] = Field(None, ge=30, le=220)
    temperatura: Optional[float] = Field(None, ge=10, le=45)


class LeituraSensor(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    timestamp_ms: Optional[int] = Field(None, ge=0, description="millis() do ESP32")
    bpm: float = Field(..., ge=30, le=220)
    temperatura: float = Field(..., ge=10, le=45)
    umidade: Optional[float] = Field(None, ge=0, le=100)
    spo2: Optional[float] = Field(None, ge=50, le=100)
    contexto: Optional[Contexto] = None


class LoteLeituras(BaseModel):
    leituras: list[LeituraSensor] = Field(..., min_length=1, max_length=100)


Faixa = Literal["baixo", "moderado", "alto"]
CorLed = Literal["verde", "amarelo", "vermelho"]


class ResultadoRisco(BaseModel):
    risco: float = Field(..., description="Probabilidade de pico de risco (0 a 1)")
    faixa: Faixa
    led: CorLed
    oled: list[str] = Field(..., description="Até 4 linhas de até 21 caracteres (ASCII)")
    protocolos_acionados: list[str]
    recomendacoes: list[str]
    features: dict[str, float] = Field(..., description="Valores efetivamente enviados ao modelo")
    features_padrao: list[str] = Field(..., description="Features preenchidas por valor padrão")
    aviso: str


class RespostaLeitura(ResultadoRisco):
    id: int
    recebido_em: str = Field(..., description="ISO 8601, UTC")
    device_id: str
    timestamp_ms: Optional[int] = None
    bpm: float
    temperatura: float
    umidade: Optional[float] = None
    spo2: Optional[float] = None


class Saude(BaseModel):
    status: Literal["ok"]
    modelo_carregado: bool
    watson_configurado: bool


class EntradaChat(BaseModel):
    mensagem: str = Field(..., min_length=1, max_length=2048)
    session_id: Optional[str] = Field(None, max_length=128)


class RespostaChat(BaseModel):
    resposta: str
    session_id: str


class Erro(BaseModel):
    detail: str
