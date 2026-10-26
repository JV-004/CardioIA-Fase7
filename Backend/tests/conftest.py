import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings(**extra) -> Settings:
    # _env_file=None + valores explícitos: os testes não dependem do .env local
    base = dict(
        _env_file=None, ambiente="desenvolvimento", cors_origins="", device_key="",
        watson_api_key="", watson_service_url="", watson_assistant_id="",
    )
    return Settings(**{**base, **extra})


@pytest.fixture
def cliente():
    with TestClient(create_app(_settings())) as c:
        yield c


@pytest.fixture
def cliente_com_chave():
    with TestClient(create_app(_settings(device_key="chave-de-teste"))) as c:
        yield c


NOVO_CASO_F6 = {
    "idade_media": 62, "carga_sistema": 92, "tempo_espera": 75, "fc_media": 118,
    "spo2_media": 89, "pa_sistolica": 100, "temperatura": 37.5,
    "densidade_eventos": 7, "eventos_24h": 5, "disponibilidade_recursos": 25,
}
