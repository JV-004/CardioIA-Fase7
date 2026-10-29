"""Testa a repetição do post_json de main.py em CPython.

main.py importa machine/network/dht e chama main() ao ser carregado, então não dá para
importá-lo aqui. Extraímos só as funções _post e post_json (código real, sem cópia) e as
executamos com um `requests` falso.
"""
import ast
from pathlib import Path

import pytest

CAMINHO_MAIN = Path(__file__).resolve().parents[1] / "main.py"
FUNCOES = {"_post", "post_json"}


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


def _carregar(requests_falso, device_key=""):
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
        **constantes, "requests": requests_falso,
        "BACKEND_URL": "https://backend.teste", "DEVICE_KEY": device_key,
    }
    exec(compile(ast.Module(body=nos, type_ignores=[]), str(CAMINHO_MAIN), "exec"), escopo)
    return escopo["post_json"], constantes


def test_constantes():
    _, constantes = _carregar(_RequestsFalso())
    assert constantes == {"TIMEOUT_HTTP_S": 10, "TENTATIVAS_HTTP": 2}


def test_sucesso_na_primeira_tentativa():
    resp = _Resposta(corpo={"risco": 0.1})
    req = _RequestsFalso(resp)
    post_json, _ = _carregar(req)
    assert post_json("/api/sensores", {"bpm": 72}) == {"risco": 0.1}
    assert len(req.chamadas) == 1 and resp.fechada
    assert req.chamadas[0]["url"] == "https://backend.teste/api/sensores"
    assert req.chamadas[0]["timeout"] == 10


def test_oserror_tenta_de_novo_e_recupera(capsys):
    resp = _Resposta(corpo={"risco": 0.2})
    req = _RequestsFalso(OSError(-202), resp)
    post_json, _ = _carregar(req)
    assert post_json("/api/sensores", {"bpm": 72}) == {"risco": 0.2}
    assert len(req.chamadas) == 2 and resp.fechada
    assert "tentativa 1/2" in capsys.readouterr().out


def test_oserror_duas_vezes_retorna_none(capsys):
    req = _RequestsFalso(OSError(110), OSError(110))
    post_json, _ = _carregar(req)
    assert post_json("/api/sensores", {}) is None
    assert len(req.chamadas) == 2
    saida = capsys.readouterr().out
    assert "tentativa 1/2" in saida and "tentativa 2/2" in saida


@pytest.mark.parametrize("item", [
    _Resposta(status=503),  # erro HTTP: não repete
    _Resposta(json_invalido=True),  # corpo inválido: não repete
    RuntimeError("outra falha"),  # erro que não é de rede: não repete
])
def test_falhas_que_nao_sao_oserror_nao_repetem(item):
    req = _RequestsFalso(item, _Resposta())
    post_json, _ = _carregar(req)
    assert post_json("/api/sensores", {}) is None
    assert len(req.chamadas) == 1
    if isinstance(item, _Resposta):
        assert item.fechada


def test_urequests_sem_timeout_usa_fallback():
    class SemTimeout(_RequestsFalso):
        def post(self, url, json=None, headers=None, **kwargs):
            if "timeout" in kwargs:
                raise TypeError("unexpected keyword argument 'timeout'")
            return super().post(url, json=json, headers=headers)

    req = SemTimeout(_Resposta())
    post_json, _ = _carregar(req)
    assert post_json("/api/sensores", {}) == {"ok": True}
    assert len(req.chamadas) == 1


def test_envia_device_key_quando_configurada():
    req = _RequestsFalso(_Resposta())
    post_json, _ = _carregar(req, device_key="demo-123")
    post_json("/api/sensores", {})
    assert req.chamadas[0]["headers"]["X-Device-Key"] == "demo-123"
