"""Testa post_json e enviar_ciclo de main.py em CPython.

main.py importa machine/network/dht e chama main() ao ser carregado, então não dá para
importá-lo aqui. Extraímos só as funções _post, post_json, enfileirar e enviar_ciclo (código real,
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
FUNCOES = {"_post", "post_json", "enfileirar", "enviar_ciclo"}


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


class _Relogio:
    """Substitui gc e time do MicroPython; registra a ordem das chamadas."""

    def __init__(self, eventos):
        self.eventos = eventos

    def collect(self):
        self.eventos.append("gc")

    def sleep_ms(self, ms):
        self.eventos.append(("sleep", ms))


def _carregar(requests_falso, device_key="", fila=None, eventos=None):
    arvore = ast.parse(CAMINHO_MAIN.read_text(encoding="utf-8"))
    nos = [n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name in FUNCOES]
    assert {n.name for n in nos} == FUNCOES
    constantes = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in arvore.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id in {"TIMEOUT_HTTP_S", "TENTATIVAS_HTTP", "PAUSA_RETRY_MS"}
    }
    relogio = _Relogio(eventos if eventos is not None else [])
    if eventos is not None:  # registra cada POST na mesma linha do tempo
        original = requests_falso.post

        def post(*args, **kwargs):
            eventos.append("post")
            return original(*args, **kwargs)
        requests_falso.post = post
    escopo = {
        **constantes, "requests": requests_falso, "logica": logica, "gc": relogio, "time": relogio,
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
    assert constantes == {"TIMEOUT_HTTP_S": 10, "TENTATIVAS_HTTP": 2, "PAUSA_RETRY_MS": 1000}


def test_gc_antes_de_cada_tentativa_e_pausa_so_entre_tentativas():
    eventos = []
    escopo, _ = _carregar(_RequestsFalso(OSError(16), _Resposta()), eventos=eventos)
    assert escopo["post_json"]("/api/sensores", {}) == (200, {"ok": True})
    assert eventos == ["gc", "post", ("sleep", 1000), "gc", "post"]


def test_sem_pausa_depois_da_ultima_tentativa():
    eventos = []
    escopo, _ = _carregar(_RequestsFalso(OSError(16), OSError(16)), eventos=eventos)
    assert escopo["post_json"]("/api/sensores", {}) == (None, None)
    assert eventos == ["gc", "post", ("sleep", 1000), "gc", "post"]  # nada depois do último


def test_sucesso_sem_pausa():
    eventos = []
    escopo, _ = _carregar(_RequestsFalso(_Resposta()), eventos=eventos)
    escopo["post_json"]("/api/sensores", {})
    assert eventos == ["gc", "post"]


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


def test_valueerror_badstatusline_na_1a_e_200_na_2a(capsys):
    # (a) urequests lança ValueError('HTTP error: BadStatusLine') quando o TLS cai
    eventos = []
    resp = _Resposta(corpo={"id": 7})
    req = _RequestsFalso(ValueError("HTTP error: BadStatusLine"), resp)
    escopo, _ = _carregar(req, eventos=eventos)
    assert escopo["post_json"]("/api/sensores/lote", {}) == (200, {"id": 7})
    assert len(req.chamadas) == 2 and resp.fechada
    assert eventos == ["gc", "post", ("sleep", 1000), "gc", "post"]
    assert "BadStatusLine" in capsys.readouterr().out


def test_valueerror_nas_duas_tentativas():
    # (b)
    req = _RequestsFalso(ValueError("HTTP error: BadStatusLine"),
                         ValueError("HTTP error: BadStatusLine"))
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores/lote", {}) == (None, None)
    assert len(req.chamadas) == 2


def test_200_com_json_invalido_nao_repete(capsys):
    # (c) o backend já gravou: repetir duplicaria o registro
    resp = _Resposta(json_invalido=True)
    req = _RequestsFalso(resp, _Resposta())
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {}) == (None, None)
    assert len(req.chamadas) == 1 and resp.fechada
    assert "Resposta inválida" in capsys.readouterr().out


def test_oserror_ao_ler_o_corpo_depois_do_200_nao_repete():
    class CorpoCortado(_Resposta):
        def json(self):
            raise OSError(-29312)  # TLS caiu lendo o corpo, depois do 200

    resp = CorpoCortado()
    req = _RequestsFalso(resp, _Resposta())
    escopo, _ = _carregar(req)
    assert escopo["post_json"]("/api/sensores", {}) == (None, None)
    assert len(req.chamadas) == 1 and resp.fechada


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


# ─── enviar_ciclo: uma requisição por ciclo ─────────────────────────────────

ATUAL = logica.montar_payload("esp", 99, 80, 36.6, 55.0, 95)


def _resultado(i, faixa="baixo"):
    return {"id": i, "bpm": 72.0, "risco": 0.1, "faixa": faixa, "recomendacoes": []}


def test_fila_vazia_envia_so_a_leitura_atual():
    req = _RequestsFalso(_Resposta(corpo=_resultado(1)))
    fila = logica.FilaOffline()
    escopo, _ = _carregar(req, fila=fila)
    assert escopo["enviar_ciclo"](ATUAL) == ("aceita", _resultado(1))
    assert len(req.chamadas) == 1
    assert req.chamadas[0]["url"].endswith("/api/sensores")
    assert req.chamadas[0]["json"] == ATUAL
    assert len(fila) == 0


def test_fila_com_itens_faz_uma_unica_requisicao_de_lote_com_a_leitura_atual_no_fim():
    fila = _fila_com(3)
    antigos = fila.itens()
    resultados = [_resultado(1), _resultado(2), _resultado(3), _resultado(4, "alto")]
    req = _RequestsFalso(_Resposta(corpo=resultados))
    escopo, _ = _carregar(req, fila=fila)
    destino, atual = escopo["enviar_ciclo"](ATUAL)
    assert len(req.chamadas) == 1  # nenhum POST /api/sensores depois do lote
    assert req.chamadas[0]["url"].endswith("/api/sensores/lote")
    assert req.chamadas[0]["json"]["leituras"] == antigos + [ATUAL]  # ordem cronológica
    assert (destino, atual) == ("aceita", _resultado(4, "alto"))  # último = leitura atual
    assert len(fila) == 0


def test_fila_nao_muda_antes_da_resposta():
    fila = _fila_com(2)
    vistos = []

    class Espiao(_RequestsFalso):
        def post(self, url, json=None, headers=None, timeout=None):
            vistos.append(len(fila))  # tamanho da fila no momento do envio
            return super().post(url, json=json, headers=headers, timeout=timeout)

    escopo, _ = _carregar(Espiao(_Resposta(corpo=[_resultado(i) for i in range(3)])), fila=fila)
    escopo["enviar_ciclo"](ATUAL)
    assert vistos == [2]


@pytest.mark.parametrize("roteiro", [
    (OSError(16), OSError(16)),  # o OSError(16) visto no Wokwi, nas duas tentativas
    (OSError(-29312), OSError(-29312)),  # MBEDTLS_ERR_SSL_CONN_EOF
    (_Resposta(status=503),),
    (_Resposta(status=401),),  # DEVICE_KEY errada: o dado é válido
])
def test_lote_que_falha_mantem_a_fila_e_enfileira_a_leitura_atual_no_fim(roteiro, capsys):
    fila = _fila_com(3)
    antigos = fila.itens()
    escopo, _ = _carregar(_RequestsFalso(*roteiro), fila=fila)
    assert escopo["enviar_ciclo"](ATUAL) == ("enfileirar", None)
    assert fila.itens() == antigos + [ATUAL]  # FIFO preservada
    assert "fila mantida" in capsys.readouterr().out


def test_falha_com_fila_cheia_descarta_o_mais_antigo(capsys):
    fila = _fila_com(20)
    antigos = fila.itens()
    escopo, _ = _carregar(_RequestsFalso(_Resposta(status=503)), fila=fila)
    escopo["enviar_ciclo"](ATUAL)
    assert len(fila) == 20
    assert fila.itens() == antigos[1:] + [ATUAL]
    assert "registro mais antigo descartado" in capsys.readouterr().out


def test_fila_vazia_e_falha_de_rede_enfileira_a_leitura_atual():
    fila = logica.FilaOffline()
    escopo, _ = _carregar(_RequestsFalso(OSError(16), OSError(16)), fila=fila)
    assert escopo["enviar_ciclo"](ATUAL) == ("enfileirar", None)
    assert fila.itens() == [ATUAL]


def test_fila_vazia_e_422_descarta_sem_enfileirar(capsys):
    fila = logica.FilaOffline()
    escopo, _ = _carregar(_RequestsFalso(_Resposta(status=422)), fila=fila)
    assert escopo["enviar_ciclo"](ATUAL) == ("descartar", None)
    assert len(fila) == 0
    assert "[DESCARTADO] leitura recusada pelo backend (status 422)" in capsys.readouterr().out


def test_lote_422_descarta_a_fila_e_a_leitura_atual(capsys):
    fila = _fila_com(4)
    escopo, _ = _carregar(_RequestsFalso(_Resposta(status=422)), fila=fila)
    assert escopo["enviar_ciclo"](ATUAL) == ("descartar", None)
    assert len(fila) == 0
    assert "[SYNC] Lote recusado (status 422); fila descartada" in capsys.readouterr().out


def test_ciclos_seguidos_falha_e_depois_sucesso_mantem_a_ordem():
    fila = _fila_com(2)
    antigos = fila.itens()
    segunda = logica.montar_payload("esp", 100, 81, 36.6)
    req = _RequestsFalso(OSError(16), OSError(16),  # ciclo 1: lote falha
                         _Resposta(corpo=[_resultado(i) for i in range(4)]))  # ciclo 2: ok
    escopo, _ = _carregar(req, fila=fila)
    escopo["enviar_ciclo"](ATUAL)
    assert escopo["enviar_ciclo"](segunda)[0] == "aceita"
    assert req.chamadas[-1]["json"]["leituras"] == antigos + [ATUAL, segunda]
    assert len(fila) == 0


def test_main_loop_faz_uma_requisicao_por_ciclo():
    """O loop principal não é executável em CPython: confere a estrutura no código."""
    fonte = CAMINHO_MAIN.read_text(encoding="utf-8")
    loop = fonte[fonte.index("def main():"):]
    assert "post_json(" not in loop  # toda requisição passa por enviar_ciclo
    assert loop.count("enviar_ciclo(payload)") == 1
    assert "sincronizar_fila" not in fonte
