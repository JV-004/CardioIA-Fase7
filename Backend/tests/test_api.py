from app.config import AVISO, CONTEXTO_PADRAO
from tests.conftest import NOVO_CASO_F6


def test_health(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "modelo_carregado": True, "watson_configurado": False}


def test_novo_caso_f6_risco_alto(cliente):
    r = cliente.post("/api/risco", json=NOVO_CASO_F6)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["risco"] >= 0.95
    assert corpo["faixa"] == "alto"
    assert corpo["led"] == "vermelho"
    assert corpo["features_padrao"] == []
    assert "estado_emergencia" in corpo["protocolos_acionados"]
    assert corpo["aviso"] == AVISO


def test_chave_com_espaco_aceita(cliente):
    caso = {k: v for k, v in NOVO_CASO_F6.items() if k != "disponibilidade_recursos"}
    caso["disponibilidade recursos"] = 25
    r = cliente.post("/api/risco", json=caso)
    assert r.status_code == 200
    assert r.json()["features"]["disponibilidade_recursos"] == 25


def test_chave_desconhecida_rejeitada(cliente):
    assert cliente.post("/api/risco", json={"pressao_inventada": 1}).status_code == 422


def test_risco_nao_armazena(cliente):
    cliente.post("/api/risco", json=NOVO_CASO_F6)
    assert cliente.get("/api/leituras/ultima").status_code == 404


def test_sensor_normal_faixa_baixo(cliente):
    r = cliente.post("/api/sensores", json={"device_id": "esp32-01", "bpm": 72, "temperatura": 36.5})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["faixa"] == "baixo"
    assert corpo["led"] == "verde"
    assert corpo["protocolos_acionados"] == []
    # spo2 não veio: sai do padrão junto com as 7 features de contexto
    assert sorted(corpo["features_padrao"]) == sorted(CONTEXTO_PADRAO)
    assert corpo["features"]["fc_media"] == 72
    assert corpo["id"] == 1 and corpo["recebido_em"]


def test_sensor_mapeia_spo2_e_contexto(cliente):
    r = cliente.post("/api/sensores", json={
        "device_id": "esp32-01", "bpm": 130, "temperatura": 38.5, "spo2": 85,
        "contexto": {"Carga Sistema": 90},
    })
    corpo = r.json()
    assert corpo["features"]["spo2_media"] == 85
    assert corpo["features"]["carga_sistema"] == 90
    assert "spo2_media" not in corpo["features_padrao"]
    assert "carga_sistema" not in corpo["features_padrao"]
    for codigo in ("suporte_respiratorio", "monitoramento_intensivo",
                   "protocolo_infeccioso", "unidades_temporarias"):
        assert codigo in corpo["protocolos_acionados"]


def test_oled_ate_4_linhas_de_21(cliente):
    r = cliente.post("/api/risco", json=NOVO_CASO_F6)
    oled = r.json()["oled"]
    assert 1 <= len(oled) <= 4
    assert all(len(linha) <= 21 and linha.isascii() for linha in oled)
    assert oled[3] == "ESTADO DE EMERGENCIA"


def test_valores_fora_do_limite_422(cliente):
    base = {"device_id": "esp32-01", "bpm": 72, "temperatura": 36.5}
    for campo, valor in [("bpm", 250), ("bpm", 10), ("temperatura", 50),
                         ("umidade", 120), ("spo2", 40)]:
        r = cliente.post("/api/sensores", json={**base, campo: valor})
        assert r.status_code == 422, (campo, valor)


def test_chat_sem_credenciais_503(cliente):
    r = cliente.post("/api/chat", json={"mensagem": "Estou com dor no peito"})
    assert r.status_code == 503
    assert "não configurado" in r.json()["detail"]
    # o resto da API continua funcionando
    assert cliente.get("/health").status_code == 200


def test_lote_preserva_ordem(cliente):
    bpms = [60, 130, 90, 75, 110]
    leituras = [{"device_id": "esp32-01", "timestamp_ms": i * 5000, "bpm": b, "temperatura": 36.5}
                for i, b in enumerate(bpms)]
    r = cliente.post("/api/sensores/lote", json={"leituras": leituras})
    assert r.status_code == 200
    corpo = r.json()
    assert [x["bpm"] for x in corpo] == bpms
    assert [x["timestamp_ms"] for x in corpo] == [0, 5000, 10000, 15000, 20000]
    assert [x["id"] for x in corpo] == [1, 2, 3, 4, 5]


def test_historico(cliente):
    for bpm in (70, 80, 90):
        cliente.post("/api/sensores", json={"device_id": "esp32-01", "bpm": bpm, "temperatura": 36.5})
    assert cliente.get("/api/leituras/ultima").json()["bpm"] == 90
    lista = cliente.get("/api/leituras", params={"limite": 2}).json()
    assert [x["bpm"] for x in lista] == [90, 80]


def test_device_key(cliente_com_chave):
    corpo = {"device_id": "esp32-01", "bpm": 72, "temperatura": 36.5}
    assert cliente_com_chave.post("/api/sensores", json=corpo).status_code == 401
    r = cliente_com_chave.post("/api/sensores", json=corpo, headers={"X-Device-Key": "errada"})
    assert r.status_code == 403
    r = cliente_com_chave.post("/api/sensores/lote", json={"leituras": [corpo]})
    assert r.status_code == 401
    r = cliente_com_chave.post("/api/sensores", json=corpo, headers={"X-Device-Key": "chave-de-teste"})
    assert r.status_code == 200
    # /api/risco não exige a chave
    assert cliente_com_chave.post("/api/risco", json={}).status_code == 200


def test_cors_vercel_e_localhost(cliente):
    for origem in ("https://cardioia.vercel.app", "http://localhost:5173"):
        r = cliente.options("/api/risco", headers={
            "Origin": origem, "Access-Control-Request-Method": "POST"})
        assert r.headers.get("access-control-allow-origin") == origem
    r = cliente.options("/api/risco", headers={
        "Origin": "https://malicioso.com", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
