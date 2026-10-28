"""Configuração do backend (lida do ambiente e, em desenvolvimento, do arquivo .env)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DIR_BACKEND = Path(__file__).resolve().parents[1]

AVISO = "Protótipo acadêmico com dados sintéticos; não substitui avaliação médica."

# Features do modelo F6 que o sensor NÃO mede. Valores em faixa normal, escolhidos para
# não acionar nenhum limiar de protocolo. Quando usados, aparecem em `features_padrao`.
CONTEXTO_PADRAO = {
    "idade_media": 55,
    "carga_sistema": 50,
    "tempo_espera": 30,
    "spo2_media": 97,
    "pa_sistolica": 120,
    "densidade_eventos": 3,
    "eventos_24h": 2,
    "disponibilidade_recursos": 70,
}

# Usados só em POST /api/risco quando a requisição não traz os sinais que o sensor mediria.
SINAIS_PADRAO = {
    "fc_media": 75,
    "temperatura": 36.5,
}

# Mapeamento campo do sensor -> feature do modelo.
MAPA_SENSOR_FEATURE = {
    "bpm": "fc_media",
    "temperatura": "temperatura",
    "spo2": "spo2_media",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=DIR_BACKEND / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    ambiente: str = "desenvolvimento"  # "producao" desativa o CORS liberado para localhost
    cors_origins: str = ""  # lista separada por vírgula
    device_key: str = ""  # se preenchida, POST /api/sensores* exige o header X-Device-Key

    watson_api_key: str = ""
    watson_service_url: str = ""
    watson_assistant_id: str = ""
    watson_environment_id: str = ""
    watson_version: str = "2021-06-14"
    watson_user_id: str = "cardioia-anonimo"  # enviado em toda mensagem (exigido pela API)

    # Faixas de risco: baixo < moderado <= ... < alto (modelo avaliado com threshold 0.5)
    limiar_moderado: float = 0.30
    limiar_alto: float = 0.50

    max_leituras: int = 200

    @property
    def lista_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def em_desenvolvimento(self) -> bool:
        return self.ambiente.strip().lower() != "producao"

    @property
    def watson_configurado(self) -> bool:
        return all([
            self.watson_api_key, self.watson_service_url,
            self.watson_assistant_id, self.watson_environment_id,
        ])


@lru_cache
def get_settings() -> Settings:
    return Settings()
