"""Testa post_json e sincronizar_fila de main.py em CPython.

main.py importa machine/network/dht e chama main() ao ser carregado, então não dá para
importá-lo aqui. Extraímos só as funções _post, post_json e sincronizar_fila (código real,
sem cópia) e as executamos com um `requests` falso e a FilaOffline de verdade.
"""
import ast
import sys
from pathlib import Path

import pytest

DIR_IOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIR_IOT))

import logica  # noqa: E402

CAMINHO_MAIN = DIR_IOT / "main.py"
FUNCOES = {"_post", "post_json", "sincronizar_fila"}


class _Resposta:
    def __init__(self, status=200, corpo=None, json_invalido=False):
        self.status_code = status
        self.text = "erro"
        self._corpo = corpo if corpo is not None else {"ok": True}
        self._json_invalido = json_invalido
        self.fechada = False

    def json(self):
        if self._json_invalido:
            raise ValueError("JSON inválido")
        return self._corpo

    def close(self):
        self.fechada = True


class _RequestsFalso:
    """Cada item de `roteiro` é uma exceção a levantar ou uma _Resposta a devolver."""

    def __init__(self, *roteiro):
        self.roteiro = list(roteiro)
        self.chamadas = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        item = self.roteiro.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _carregar(requests_falso, device_key="", fila=None):
    arvore = ast.parse(CAMINHO_MAIN.read_text(encoding="utf-8"))
    nos = [n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name in FUNCOES]
    assert {n.name for n in nos} == FUNCOES
    constantes = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in arvore.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in {"TIMEOUT_HTTP_S", "TENTATIVAS_HTTP"}
    }
    escopo = {
        **constantes, "requests": requests_falso, "logica": logica,
        "fila": fila if fila is not None else logica.FilaOffline(),
        "BACKEND_URL": "https://backend.teste", "DEVICE_KEY": device_key,
    }
    exec(compile(ast.Module(body=nos, type_ignores=[]), str(CAMINHO_MAIN), "exec"), escopo)
    return escopo, constantes


def _fila_com(n):
    fila = logica.FilaOffline()
    for i in range(n):
        fila.adicionar(logica.montar_payload("esp", i, 72, 36.5))
    return fila


# ─── post_json: devolve (status_http, dados) ────────────────────────────────

def test_constantes():
    _, constantes = _carregar(_RequestsFalso())
    assert constantes == {"TIMEOUT_HTTP_S": 10, "TENTATIVAS_HTTP": 2}


def test_sucesso_na_primeira_tentativa():
    resp = _Resposta(corpo={"risco": 0.1})
    req = _RequestsFalso(resp)
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {"bpm": 72}) == (200, {"risco": 0.1})
    assert len(req.chamadas) == 1 and resp.fechada
    assert req.chamadas[0]["url"] == "https://backend.teste/api/sensores"
    assert req.chamadas[0]["timeout"] == 10


def test_oserror_tenta_de_novo_e_recupera(capsys):
    resp = _Resposta(corpo={"risco": 0.2})
    req = _RequestsFalso(OSError(-202), resp)
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {"bpm": 72}) == (200, {"risco": 0.2})
    assert len(req.chamadas) == 2 and resp.fechada
    assert "tentativa 1/2" in capsys.readouterr().out


def test_oserror_duas_vezes_sem_status(capsys):
    req = _RequestsFalso(OSError(110), OSError(110))
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {}) == (None, None)
    assert len(req.chamadas) == 2
    saida = capsys.readouterr().out
    assert "tentativa 1/2" in saida and "tentativa 2/2" in saida


@pytest.mark.parametrize("status", [422, 400, 503, 500])
def test_status_diferente_de_200_devolve_o_status_sem_repetir(status):
    resp = _Resposta(status=status)
    req = _RequestsFalso(resp, _Resposta())
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {}) == (status, None)
    assert len(req.chamadas) == 1 and resp.fechada


@pytest.mark.parametrize("item", [_Resposta(json_invalido=True), RuntimeError("outra falha")])
def test_falhas_que_nao_sao_oserror_nao_repetem(item):
    req = _RequestsFalso(item, _Resposta())
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {}) == (None, None)
    assert len(req.chamadas) == 1


def test_urequests_sem_timeout_usa_fallback():
    class SemTimeout(_RequestsFalso):
        def post(self, url, json=None, headers=None, **kwargs):
            if "timeout" in kwargs:
                raise TypeError("unexpected keyword argument 'timeout'")
            return super().post(url, json=json, headers=headers)

    req = SemTimeout(_Resposta())
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {}) == (200, {"ok": True})
    assert len(req.chamadas) == 1


def test_envia_device_key_quando_configurada():
    req = _RequestsFalso(_Resposta())
    escopo, _ = _carregar(req, device_key="demo-123")
    escopo["post_json"]("/api/sensores", {})
    assert req.chamadas[0]["headers"]["X-Device-Key"] == "demo-123"


# ─── sincronizar_fila: 4xx descarta, rede/5xx mantém ────────────────────────

def test_lote_aceito_limpa_a_fila():
    fila = _fila_com(3)
    resultados = [{"id": i, "bpm": 72.0, "risco": 0.0, "faixa": "baixo"} for i in (1, 2, 3)]
    req = _RequestsFalso(_Resposta(corpo=resultados))
    escopo, _ = _carregar(req, fila=fila)
    assert escopo["sincronizar_fila"]() is True
    assert len(fila) == 0
    assert req.chamadas[0]["url"].endswith("/api/sensores/lote")
    assert len(req.chamadas[0]["json"]["leituras"]) == 3


def test_lote_422_descarta_a_fila(capsys):
    fila = _fila_com(4)
    req = _RequestsFalso(_Resposta(status=422))
    escopo, _ = _carregar(req, fila=fila)
    assert escopo["sincronizar_fila"]() is True  # fila vazia: pode seguir com a leitura atual
    assert len(fila) == 0
    assert "[SYNC] Lote recusado (status 422); fila descartada" in capsys.readouterr().out


@pytest.mark.parametrize("roteiro", [
    (OSError(-29312), OSError(-29312)),  # rede/TLS nas duas tentativas
    (_Resposta(status=503),),  # servidor indisponível
    (_Resposta(status=500),),
    (_Resposta(status=401),),  # DEVICE_KEY errada: o dado é válido
    (_Resposta(status=429),),  # limite de requisições
])
def test_lote_com_falha_temporaria_mantem_a_fila(roteiro, capsys):
    fila = _fila_com(5)
    escopo, _ = _carregar(_RequestsFalso(*roteiro), fila=fila)
    assert escopo["sincronizar_fila"]() is False
    assert len(fila) == 5
    assert "fila mantida" in capsys.readouterr().out


def test_fila_vazia_nao_chama_o_backend():
    req = _RequestsFalso()
    escopo, _ = _carregar(req)
    assert escopo["sincronizar_fila"]() is True
    assert req.chamadas == []


def test_main_loop_usa_destino_resposta_para_descartar():
    """O loop principal não é executável em CPython: confere que ele decide via logica."""
    fonte = CAMINHO_MAIN.read_text(encoding="utf-8")
    inicio = fonte.index("def main():")
    loop = fonte[inicio:]
    assert 'status_http, resultado = post_json("/api/sensores", payload)' in loop
    assert "logica.destino_resposta(status_http, resultado)" in loop
    assert '[DESCARTADO] leitura recusada pelo backend (status %d)' in loop
    assert "if not backend_ok and not descartada:" in loop  # descartada não vai para a fila
