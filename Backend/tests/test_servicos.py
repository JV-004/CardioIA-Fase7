from types import SimpleNamespace

import pytest
from ibm_cloud_sdk_core import ApiException

from app.config import Settings
from app.services.leituras import RepositorioLeituras
from app.services.protocolos import avaliar_protocolos
from app.services.risco import classificar_faixa
from app.services.watson import ServicoWatson, WatsonIndisponivel

S = Settings(_env_file=None)


@pytest.mark.parametrize("risco,faixa", [
    (0.0, "baixo"), (0.2999, "baixo"), (0.30, "moderado"), (0.4999, "moderado"),
    (0.50, "alto"), (1.0, "alto"),
])
def test_faixas(risco, faixa):
    assert classificar_faixa(risco, S) == faixa


@pytest.mark.parametrize("feature,valor,codigo", [
    ("spo2_media", 87, "suporte_respiratorio"),
    ("carga_sistema", 86, "unidades_temporarias"),
    ("fc_media", 121, "monitoramento_intensivo"),
    ("eventos_24h", 6, "resposta_rapida"),
    ("disponibilidade_recursos", 29, "redistribuir_insumos"),
    ("tempo_espera", 91, "triagem_emergencial"),
    ("temperatura", 38.1, "protocolo_infeccioso"),
    ("densidade_eventos", 7, "plano_contingencia"),
    ("pa_sistolica", 89, "protocolo_choque"),
])
def test_cada_protocolo(feature, valor, codigo):
    assert [p.codigo for p in avaliar_protocolos({feature: valor}, "baixo")] == [codigo]


def test_limiares_sao_estritos():
    # exatamente no limiar não aciona (inclusive SpO2 = 88, mantido literal da F6)
    no_limiar = {"spo2_media": 88, "carga_sistema": 85, "fc_media": 120, "eventos_24h": 5,
                 "disponibilidade_recursos": 30, "tempo_espera": 90, "temperatura": 38,
                 "densidade_eventos": 6, "pa_sistolica": 90}
    assert avaliar_protocolos(no_limiar, "moderado") == []
    assert [p.codigo for p in avaliar_protocolos(no_limiar, "alto")] == ["estado_emergencia"]


def test_repositorio_limite():
    repo = RepositorioLeituras(max_leituras=3)
    base = dict(risco=0.1, faixa="baixo", led="verde", oled=[], protocolos_acionados=[],
                recomendacoes=[], features={}, features_padrao=[], aviso="x",
                recebido_em="t", device_id="d", temperatura=36.5)
    for bpm in range(5):
        repo.adicionar({**base, "bpm": 60 + bpm})
    assert [r.id for r in repo.listar(10)] == [5, 4, 3]


class _ClienteFalso:
    """Simula o AssistantV2 (assinaturas do ibm-watson 11.x) e registra cada chamada.

    A primeira mensagem falha com sessão expirada (404) para exercitar a recriação.
    """

    def __init__(self):
        self.sessoes = 0
        self.falhar = True
        self.chamadas = []

    def create_session(self, assistant_id, environment_id, *, analytics=None):
        self.chamadas.append(("create_session", assistant_id, environment_id, None))
        self.sessoes += 1
        return SimpleNamespace(get_result=lambda: {"session_id": f"s{self.sessoes}"})

    def message(self, assistant_id, environment_id, session_id, *, input=None, context=None,
                user_id=None):
        self.chamadas.append(("message", assistant_id, environment_id, session_id))
        if self.falhar:
            self.falhar = False
            raise ApiException(404, message="Invalid Session")
        resultado = {"output": {"generic": [{"response_type": "text", "text": "Olá!"}]}}
        return SimpleNamespace(get_result=lambda: resultado)


def _watson_com(cliente):
    servico = ServicoWatson(Settings(_env_file=None, watson_api_key="k", watson_service_url="u",
                                     watson_assistant_id="a", watson_environment_id="env-1"))
    servico._cliente = cliente
    return servico


def test_watson_recria_sessao_expirada_repassando_environment_id():
    cliente = _ClienteFalso()
    resposta, sessao = _watson_com(cliente).conversar("oi", "sessao-velha")
    assert resposta == "Olá!" and sessao == "s1"
    assert cliente.chamadas == [
        ("message", "a", "env-1", "sessao-velha"),  # 404: sessão expirada
        ("create_session", "a", "env-1", None),  # recriação
        ("message", "a", "env-1", "s1"),
    ]


def test_watson_cria_sessao_com_environment_id():
    cliente = _ClienteFalso()
    cliente.falhar = False
    resposta, sessao = _watson_com(cliente).conversar("oi")
    assert (resposta, sessao) == ("Olá!", "s1")
    assert cliente.chamadas == [
        ("create_session", "a", "env-1", None),
        ("message", "a", "env-1", "s1"),
    ]


def test_watson_sem_environment_id_nao_configurado():
    servico = ServicoWatson(Settings(_env_file=None, watson_api_key="k", watson_service_url="u",
                                     watson_assistant_id="a", watson_environment_id=""))
    assert servico.configurado is False
    with pytest.raises(WatsonIndisponivel, match="WATSON_ENVIRONMENT_ID"):
        servico.conversar("oi")


def test_watson_erro_de_rede_vira_indisponivel():
    class Quebrado(_ClienteFalso):
        def message(self, *_, **__):
            raise ConnectionError("sem rede")

    with pytest.raises(WatsonIndisponivel, match="falha de comunicação"):
        _watson_com(Quebrado()).conversar("oi", "s")
