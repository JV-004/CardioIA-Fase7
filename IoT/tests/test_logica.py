"""Testes da lógica pura do firmware (rodam em CPython)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import logica  # noqa: E402


def test_mapear_como_arduino():
    assert logica.mapear(0, 0, 4095, 40, 180) == 40
    assert logica.mapear(4095, 0, 4095, 40, 180) == 180
    assert logica.mapear(2048, 0, 4095, 70, 100) == 85
    assert logica.mapear(9999, 0, 4095, 40, 180) == 180  # satura


def test_sem_alertas_em_faixa_normal():
    assert logica.classificar_alertas(72, 36.5, 60, 97) == []


def test_alertas_individuais():
    assert logica.classificar_alertas(121, 36.5, 60) == ["taquicardia"]
    assert logica.classificar_alertas(72, 38.1, 60) == ["febre"]
    assert logica.classificar_alertas(72, 36.5, 39.9) == ["umidade_inadequada"]
    assert logica.classificar_alertas(72, 36.5, 80.1) == ["umidade_inadequada"]
    assert logica.classificar_alertas(72, 36.5, 60, 87) == ["spo2_baixa"]


def test_limites_sao_estritos_como_na_f3():
    assert logica.classificar_alertas(120, 38.0, 40.0, 88) == []
    assert logica.classificar_alertas(72, 36.5, 80.0) == []


def test_falha_do_dht_nao_gera_alerta():
    assert logica.classificar_alertas(72, None, None) == []


def test_varios_alertas():
    assert logica.classificar_alertas(150, 39, 90, 80) == [
        "taquicardia", "febre", "umidade_inadequada", "spo2_baixa"]


def test_fila_fifo_descarta_mais_antigo_na_21a():
    fila = logica.FilaOffline()
    for i in range(20):
        assert fila.adicionar({"n": i}) is False
    assert len(fila) == 20
    assert fila.adicionar({"n": 20}) is True  # 21ª leitura
    itens = fila.itens()
    assert len(itens) == 20
    assert itens[0] == {"n": 1} and itens[-1] == {"n": 20}
    fila.limpar()
    assert len(fila) == 0


def test_fila_itens_e_copia():
    fila = logica.FilaOffline(maximo=2)
    fila.adicionar(1)
    fila.itens().append(99)
    assert fila.itens() == [1]


def test_payload_completo_e_parcial():
    assert logica.montar_payload("esp", 5000, 72, 36.5, 60, 97) == {
        "device_id": "esp", "timestamp_ms": 5000, "bpm": 72,
        "temperatura": 36.5, "umidade": 60, "spo2": 97}
    parcial = logica.montar_payload("esp", 0, 72, 36.5)
    assert "umidade" not in parcial and "spo2" not in parcial


def test_wifi_simulado_comeca_offline_e_alterna():
    assert logica.wifi_simulado_online(0) is False
    assert logica.wifi_simulado_online(29999) is False
    assert logica.wifi_simulado_online(30000) is True
    assert logica.wifi_simulado_online(60000) is False


def test_led_alerta():
    assert logica.led_alerta_aceso([], "baixo") is False
    assert logica.led_alerta_aceso(["febre"], "baixo") is True
    assert logica.led_alerta_aceso([], "alto") is True
    assert logica.led_alerta_aceso([], None) is False


def test_oled_4_linhas_que_cabem_no_display():
    casos = [
        (72, 36.5, 97, 60, 0.12, "baixo", True, 0),
        (220, 45.0, 100, 100, 1.0, "moderado", False, 20),
        (40, None, 70, None, None, None, False, 5),
    ]
    for caso in casos:
        linhas = logica.linhas_oled(*caso)
        assert len(linhas) == 4
        for linha in linhas:
            assert len(linha) <= 21  # contrato
            assert len(linha) <= logica.LARGURA_OLED  # cabe na fonte 8x8 do framebuf
    assert logica.linhas_oled(72, 36.5, 97, 60, 0.12, "baixo", True, 0) == [
        "BPM 72 T36.5C", "SpO2 97% U60%", "Risco 12% BAIXO", "WiFi ON Fila 0"]
    assert logica.linhas_oled(40, None, 70, None, None, None, False, 5)[2] == "Risco --"


def test_log_formato_f3():
    texto = logica.formatar_log(5000, 130, 36.5, 60.0, 97, "ONLINE", ["taquicardia"])
    assert texto == ("[5000ms] BPM: 130 | Temp: 36.5C | Umidade: 60.0% | SpO2: 97% "
                     "| Status: ONLINE | ALERTA: taquicardia")


# ─── Limites do backend e descarte de leituras inválidas ───────────────────

def test_limites_iguais_aos_do_backend():
    pytest.importorskip("pydantic")  # lê os limites reais de Backend/app/schemas.py
    import importlib.util
    raiz = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("schemas_backend", raiz / "Backend/app/schemas.py")
    schemas = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schemas)
    for campo, (minimo, maximo) in logica.LIMITES_BACKEND.items():
        meta = schemas.LeituraSensor.model_fields[campo].metadata
        assert (minimo, maximo) == (
            next(m.ge for m in meta if hasattr(m, "ge")),
            next(m.le for m in meta if hasattr(m, "le")),
        ), campo


def test_payload_limita_valores_fora_da_faixa():
    p = logica.montar_payload("esp", 0, 250, 46.9, 105, 40)
    assert (p["bpm"], p["temperatura"], p["umidade"], p["spo2"]) == (220, 45, 100, 50)
    p = logica.montar_payload("esp", 0, 20, 5.0, -3, 49)
    assert (p["bpm"], p["temperatura"], p["umidade"], p["spo2"]) == (30, 10, 0, 50)


def test_payload_dentro_da_faixa_nao_muda():
    p = logica.montar_payload("esp", 0, 75, 36.5, 60.0, 94)
    assert (p["bpm"], p["temperatura"], p["umidade"], p["spo2"]) == (75, 36.5, 60.0, 94)
    assert logica.limitar("spo2", None) is None


def test_alertas_locais_usam_valor_bruto():
    # 46,9 °C vai limitado (45) para o backend, mas o alerta local vê o valor real
    assert logica.classificar_alertas(72, 46.9, 60) == ["febre"]
    assert logica.montar_payload("esp", 0, 72, 46.9)["temperatura"] == 45


@pytest.mark.parametrize("status,dados,destino", [
    (200, {"id": 1}, "aceita"),
    (200, None, "enfileirar"),  # 200 sem JSON válido: não perde a leitura
    (422, None, "descartar"),
    (400, None, "descartar"),
    (404, None, "descartar"),
    (401, None, "enfileirar"),  # DEVICE_KEY errada: o dado é válido
    (403, None, "enfileirar"),
    (408, None, "enfileirar"),
    (429, None, "enfileirar"),
    (500, None, "enfileirar"),
    (503, None, "enfileirar"),
    (None, None, "enfileirar"),  # falha de rede
])
def test_destino_resposta(status, dados, destino):
    assert logica.destino_resposta(status, dados) == destino
