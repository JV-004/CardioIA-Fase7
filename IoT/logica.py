"""CardioIA Fase 7 — lógica pura do dispositivo (sem acesso a hardware).

Convertida do sketch.ino da Fase 3 (C++). Roda igual em MicroPython (ESP32) e em
CPython, o que permite testar com pytest no computador. Não use aqui imports de
`machine`, `network`, `dht` etc. — isso fica em main.py.
"""

# ─── Limites de alerta local (mesmos da F3 + SpO2, sensor novo da F7) ────────
BPM_LIMITE_ALTO = 120  # taquicardia: > 120 BPM
TEMP_LIMITE_ALTO = 38.0  # febre: > 38 °C
UMIDADE_LIMITE_BAIXO = 40.0  # ambiente seco: < 40%
UMIDADE_LIMITE_ALTO = 80.0  # ambiente úmido: > 80%
SPO2_LIMITE_BAIXO = 88  # mesmo limiar do protocolo de suporte respiratório do backend

# Limites aceitos pelo backend (Backend/app/schemas.py, LeituraSensor). Fora deles a API
# responde 422, e a leitura nunca seria aceita; por isso o payload é limitado a essa faixa.
LIMITES_BACKEND = {
    "bpm": (30, 220),
    "temperatura": (10, 45),
    "umidade": (0, 100),
    "spo2": (50, 100),
}

MAX_REGISTROS_OFFLINE = 20
INTERVALO_WIFI_MS = 30000  # alternância online/offline simulada (igual à F3)

# Framebuf do MicroPython usa fonte 8x8: 128 px / 8 = 16 colunas no SSD1306.
LARGURA_OLED = 16

ABREVIACAO_FAIXA = {"baixo": "BAIXO", "moderado": "MOD", "alto": "ALTO"}


def mapear(valor, in_min, in_max, out_min, out_max):
    """Equivalente ao map() do Arduino, com saturação nas pontas."""
    valor = max(in_min, min(in_max, valor))
    return out_min + (valor - in_min) * (out_max - out_min) // (in_max - in_min)


def classificar_alertas(bpm, temperatura, umidade, spo2=None):
    """Lista de alertas locais. Leituras ausentes (None = falha do sensor) são ignoradas."""
    alertas = []
    if bpm is not None and bpm > BPM_LIMITE_ALTO:
        alertas.append("taquicardia")
    if temperatura is not None and temperatura > TEMP_LIMITE_ALTO:
        alertas.append("febre")
    if umidade is not None and (umidade < UMIDADE_LIMITE_BAIXO or umidade > UMIDADE_LIMITE_ALTO):
        alertas.append("umidade_inadequada")
    if spo2 is not None and spo2 < SPO2_LIMITE_BAIXO:
        alertas.append("spo2_baixa")
    return alertas


def limitar(campo, valor):
    """Traz o valor para dentro de LIMITES_BACKEND[campo]; None continua None."""
    if valor is None:
        return None
    minimo, maximo = LIMITES_BACKEND[campo]
    return max(minimo, min(maximo, valor))


def montar_payload(device_id, timestamp_ms, bpm, temperatura, umidade=None, spo2=None):
    """Corpo de POST /api/sensores (campos opcionais só entram se houver leitura).

    Os valores são limitados à faixa aceita pelo backend. Os alertas locais
    (classificar_alertas) usam o valor bruto do sensor, não este.
    """
    payload = {
        "device_id": device_id,
        "timestamp_ms": timestamp_ms,
        "bpm": limitar("bpm", bpm),
        "temperatura": limitar("temperatura", temperatura),
    }
    if umidade is not None:
        payload["umidade"] = limitar("umidade", umidade)
    if spo2 is not None:
        payload["spo2"] = limitar("spo2", spo2)
    return payload


# 4xx que NÃO significam dado inválido: chave do dispositivo errada (401/403) ou
# limite/espera do servidor (408/429). Corrigida a causa, a mesma leitura é aceita.
STATUS_4XX_TEMPORARIOS = (401, 403, 408, 429)


def destino_resposta(status_http, dados):
    """O que fazer com uma leitura depois do POST ao backend.

    "aceita"     -> 200 com corpo JSON;
    "descartar"  -> 4xx de dado inválido (ex.: 422): reenviar nunca vai funcionar;
    "enfileirar" -> falha de rede (status None), 5xx ou 4xx temporário: tentar de novo depois.
    """
    if status_http == 200 and dados is not None:
        return "aceita"
    if status_http is not None and 400 <= status_http < 500             and status_http not in STATUS_4XX_TEMPORARIOS:
        return "descartar"
    return "enfileirar"


class FilaOffline:
    """Fila FIFO de tamanho fixo: cheia, descarta o registro mais antigo (como na F3)."""

    def __init__(self, maximo=MAX_REGISTROS_OFFLINE):
        self.maximo = maximo
        self._itens = []

    def adicionar(self, item):
        """Enfileira. Retorna True se precisou descartar o mais antigo."""
        descartou = len(self._itens) >= self.maximo
        if descartou:
            self._itens.pop(0)
        self._itens.append(item)
        return descartou

    def itens(self):
        return list(self._itens)

    def limpar(self):
        self._itens = []

    def __len__(self):
        return len(self._itens)


def wifi_simulado_online(ms_desde_inicio, intervalo_ms=INTERVALO_WIFI_MS):
    """Começa OFFLINE e alterna a cada 30 s (comportamento da F3)."""
    return (ms_desde_inicio // intervalo_ms) % 2 == 1


def led_alerta_aceso(alertas, faixa=None):
    """LED vermelho: alerta local OU faixa "alto" devolvida pelo backend."""
    return bool(alertas) or faixa == "alto"


def _num(valor, formato):
    return "--" if valor is None else formato % valor


def linhas_oled(bpm, temperatura, spo2, umidade, risco, faixa, online, tamanho_fila):
    """4 linhas (<= 16 caracteres) para o SSD1306 128x64."""
    if risco is None or faixa is None:
        linha_risco = "Risco --"
    else:
        linha_risco = "Risco %d%% %s" % (round(risco * 100), ABREVIACAO_FAIXA.get(faixa, faixa.upper()))
    linhas = [
        "BPM %s T%sC" % (_num(bpm, "%d"), _num(temperatura, "%.1f")),
        "SpO2 %s%% U%s%%" % (_num(spo2, "%d"), _num(umidade, "%d")),
        linha_risco,
        "%s Fila %d" % ("WiFi ON" if online else "OFFLINE", tamanho_fila),
    ]
    return [linha[:LARGURA_OLED] for linha in linhas]


def formatar_log(timestamp_ms, bpm, temperatura, umidade, spo2, status, alertas):
    """Linha do monitor serial, no formato da F3 (+ SpO2)."""
    texto = "[%dms] BPM: %s | Temp: %sC | Umidade: %s%% | SpO2: %s%% | Status: %s" % (
        timestamp_ms, _num(bpm, "%d"), _num(temperatura, "%.1f"),
        _num(umidade, "%.1f"), _num(spo2, "%d"), status,
    )
    if alertas:
        texto += " | ALERTA: " + ", ".join(alertas)
    return texto
