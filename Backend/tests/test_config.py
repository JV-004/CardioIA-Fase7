"""Limpeza das variáveis de ambiente coladas com espaço, quebra de linha, aspas ou "/" final."""
import logging

import pytest

from app.config import Settings
from app.services.watson import TIMEOUT_S, ServicoWatson, WatsonIndisponivel

URL = "https://api.au-syd.assistant.watson.cloud.ibm.com/instances/abc-123"
UUID_A = "11111111-2222-3333-4444-555555555555"
UUID_E = "66666666-7777-8888-9999-000000000000"


def _s(**valores) -> Settings:
    return Settings(_env_file=None, **valores)


@pytest.mark.parametrize("bruto", [
    "chave-xyz ", "chave-xyz\n", "  chave-xyz\r\n", '"chave-xyz"', "'chave-xyz'", ' "chave-xyz" \n',
])
def test_api_key_espaco_quebra_de_linha_e_aspas(bruto):
    assert _s(watson_api_key=bruto).watson_api_key == "chave-xyz"


@pytest.mark.parametrize("bruto", [
    URL + "/", URL + "/\n", f'"{URL}/"', f"  '{URL}'  ", URL[:30] + " \n" + URL[30:],
])
def test_service_url_sem_whitespace_aspas_nem_barra_final(bruto):
    assert _s(watson_service_url=bruto).watson_service_url == URL


@pytest.mark.parametrize("campo,bruto,limpo", [
    ("watson_assistant_id", f" {UUID_A}\n", UUID_A),
    ("watson_assistant_id", f'"{UUID_A[:8]} {UUID_A[8:]}"', UUID_A),  # espaço no meio
    ("watson_environment_id", f"'{UUID_E}'\r\n", UUID_E),
    ("watson_environment_id", f"{UUID_E[:18]}\n{UUID_E[18:]}", UUID_E),  # quebra no meio
])
def test_ids_sem_nenhum_whitespace(campo, bruto, limpo):
    assert getattr(_s(**{campo: bruto}), campo) == limpo


@pytest.mark.parametrize("campo,bruto,limpo", [
    ("watson_user_id", ' "turma fiap" ', "turma fiap"),  # só as pontas: espaço interno fica
    ("watson_version", "2021-06-14\n", "2021-06-14"),
    ("device_key", "'demo-123' ", "demo-123"),
])
def test_demais_campos_so_nas_pontas(campo, bruto, limpo):
    assert getattr(_s(**{campo: bruto}), campo) == limpo


def test_valores_lidos_do_ambiente_tambem_sao_limpos(monkeypatch):
    monkeypatch.setenv("WATSON_SERVICE_URL", f' "{URL}/"\n')
    monkeypatch.setenv("WATSON_ENVIRONMENT_ID", f"{UUID_E}\n")
    s = Settings(_env_file=None)
    assert s.watson_service_url == URL
    assert s.watson_environment_id == UUID_E


@pytest.mark.parametrize("vazio", ["", "   ", "\n", '""', "''", ' "" \n'])
def test_vazio_continua_sem_watson(vazio):
    s = _s(watson_api_key=vazio, watson_service_url=vazio,
           watson_assistant_id=vazio, watson_environment_id=vazio)
    assert s.watson_configurado is False
    with pytest.raises(WatsonIndisponivel, match="não configurado"):
        ServicoWatson(s).conversar("oi")


def test_uma_variavel_vazia_apos_limpeza_desliga_watson():
    s = _s(watson_api_key="chave", watson_service_url=URL, watson_assistant_id=UUID_A,
           watson_environment_id=" \n ")
    assert s.watson_configurado is False


def test_cliente_watson_usa_timeout_curto():
    servico = ServicoWatson(_s(watson_api_key="chave-xyz", watson_service_url=URL,
                               watson_assistant_id=UUID_A, watson_environment_id=UUID_E))
    cliente = servico._obter_cliente()  # só monta o cliente; nenhuma chamada de rede
    assert cliente.http_config.get("timeout") == TIMEOUT_S == 15


def test_log_de_falha_tem_tipo_e_mensagem_sem_a_chave(caplog):
    chave = "chave-falsa-de-teste-xyz"

    class Quebrado:
        def create_session(self, *_, **__):
            raise ConnectionError(f"falhou ao autenticar com {chave} em {URL}")

    servico = ServicoWatson(_s(watson_api_key=chave, watson_service_url=URL,
                               watson_assistant_id=UUID_A, watson_environment_id=UUID_E))
    servico._cliente = Quebrado()
    with caplog.at_level(logging.WARNING), pytest.raises(WatsonIndisponivel):
        servico.conversar("oi")
    texto = caplog.text
    assert "ConnectionError" in texto and "falhou ao autenticar" in texto
    assert chave not in texto and "***" in texto
