"""CardioIA Fase 7 — firmware MicroPython para ESP32 (simulado no Wokwi).

Conversão do sketch.ino da Fase 3: lê DHT22 + potenciômetros (BPM e SpO2), envia ao
backend Python, guarda em fila offline quando não há conexão e sincroniza em lote ao
reconectar. Feedback: LED verde (WiFi/backend OK), LED vermelho (alerta), OLED SSD1306.

A lógica testável fica em logica.py; aqui só o que depende do hardware.
"""
import time

import dht
import network
from machine import ADC, I2C, Pin

import logica
import ssd1306

try:
    import urequests as requests
except ImportError:
    import requests

# ─── Configuração (edite antes de rodar) ────────────────────────────────────
BACKEND_URL = "https://SEU-BACKEND.onrender.com"
# Chave de DEMONSTRAÇÃO: o projeto Wokwi é público, então ela não é segredo.
# Deixe "" se o backend não tiver DEVICE_KEY configurada.
DEVICE_KEY = ""
DEVICE_ID = "esp32-wokwi-01"

WIFI_SSID = "Wokwi-GUEST"
WIFI_SENHA = ""

INTERVALO_LEITURA_MS = 5000
TIMEOUT_HTTP_S = 10  # o Render free pode levar ~50 s para acordar; a leitura vai para a fila
SIMULAR_OFFLINE_30S = True  # reproduz a alternância online/offline da F3 na demonstração
BPM_ALEATORIO = False  # só use se o potenciômetro continuar travado no máximo do ADC

# ─── Pinos (mesmos da F3 + SpO2 e OLED) ─────────────────────────────────────
PINO_DHT22 = 4
PINO_BPM = 32
PINO_SPO2 = 33
PINO_LED_WIFI = 2
PINO_LED_ALERTA = 15
PINO_SDA = 21
PINO_SCL = 22

# ─── Hardware ───────────────────────────────────────────────────────────────
sensor_dht = dht.DHT22(Pin(PINO_DHT22))
led_wifi = Pin(PINO_LED_WIFI, Pin.OUT, value=0)
led_alerta = Pin(PINO_LED_ALERTA, Pin.OUT, value=0)


def criar_adc(pino):
    adc = ADC(Pin(pino))
    adc.atten(ADC.ATTN_11DB)  # faixa de 0 a ~3,3 V
    return adc


adc_bpm = criar_adc(PINO_BPM)
adc_spo2 = criar_adc(PINO_SPO2)

try:
    oled = ssd1306.SSD1306_I2C(128, 64, I2C(0, sda=Pin(PINO_SDA), scl=Pin(PINO_SCL)))
except OSError:
    oled = None
    print("[ERRO] OLED não encontrado no I2C (SDA 21, SCL 22)")

fila = logica.FilaOffline()


def ler_adc_12bits(adc):
    return adc.read_u16() >> 4  # 0..4095, igual ao analogRead do Arduino


def ler_bpm():
    if BPM_ALEATORIO:
        import random
        return random.randint(60, 115)  # fallback da F3
    return logica.mapear(ler_adc_12bits(adc_bpm), 0, 4095, 40, 180)


def ler_spo2():
    return logica.mapear(ler_adc_12bits(adc_spo2), 0, 4095, 70, 100)


def ler_dht():
    """(temperatura, umidade) ou (None, None) se o DHT22 falhar."""
    try:
        sensor_dht.measure()
        return sensor_dht.temperature(), sensor_dht.humidity()
    except OSError:
        print("[ERRO] Falha na leitura do DHT22")
        return None, None


def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("[WIFI] Conectando em", WIFI_SSID, end="")
        wlan.connect(WIFI_SSID, WIFI_SENHA)
        for _ in range(40):
            if wlan.isconnected():
                break
            print(".", end="")
            time.sleep(0.25)
        print()
    print("[WIFI]", "Conectado:", wlan.ifconfig()[0] if wlan.isconnected() else "FALHOU")
    return wlan


def post_json(rota, corpo):
    """POST no backend. Retorna o JSON da resposta ou None em qualquer falha."""
    headers = {"Content-Type": "application/json"}
    if DEVICE_KEY:
        headers["X-Device-Key"] = DEVICE_KEY
    resposta = None
    try:
        try:
            resposta = requests.post(BACKEND_URL + rota, json=corpo, headers=headers,
                                     timeout=TIMEOUT_HTTP_S)
        except TypeError:  # urequests antigo sem parâmetro timeout
            resposta = requests.post(BACKEND_URL + rota, json=corpo, headers=headers)
        if resposta.status_code != 200:
            print("[HTTP]", rota, "status", resposta.status_code, resposta.text[:120])
            return None
        return resposta.json()
    except Exception as exc:
        print("[HTTP] Falha em", rota, "->", repr(exc))
        return None
    finally:
        if resposta is not None:
            resposta.close()


def sincronizar_fila():
    """Envia a fila offline em /api/sensores/lote. Só limpa se o backend confirmar."""
    if not len(fila):
        return True
    print("========================================")
    print("[SYNC] Sincronizando %d registro(s) offline..." % len(fila))
    resultados = post_json("/api/sensores/lote", {"leituras": fila.itens()})
    if resultados is None:
        print("[SYNC] Falhou; fila mantida.")
        return False
    for r in resultados:
        print("  id=%s bpm=%s risco=%.2f faixa=%s" % (r["id"], r["bpm"], r["risco"], r["faixa"]))
    fila.limpar()
    print("[SYNC] Concluído. Fila limpa.")
    print("========================================")
    return True


def atualizar_oled(linhas):
    if oled is None:
        return
    oled.fill(0)
    for i, linha in enumerate(linhas):
        oled.text(linha, 0, i * 16)  # 4 linhas espaçadas em 64 px
    oled.show()


def main():
    print("========================================")
    print("  CardioIA - Fase 7 (MicroPython)")
    print("  Sensor -> MicroPython -> Backend -> IA")
    print("========================================")
    print("Backend:", BACKEND_URL)
    print("Simular offline a cada 30 s:", SIMULAR_OFFLINE_30S)
    atualizar_oled(["CardioIA F7", "Conectando...", "", ""])
    wlan = conectar_wifi()

    inicio = time.ticks_ms()
    estava_online = None
    ultimo_risco = ultima_faixa = None

    while True:
        ciclo = time.ticks_ms()
        agora_ms = time.ticks_diff(ciclo, inicio)

        online = wlan.isconnected()
        if SIMULAR_OFFLINE_30S:
            online = online and logica.wifi_simulado_online(agora_ms)
        if online != estava_online:
            print("\n[WIFI]", "CONECTADO - modo online" if online else
                  "DESCONECTADO - armazenamento local (edge) ativo")
            estava_online = online

        bpm = ler_bpm()
        spo2 = ler_spo2()
        temperatura, umidade = ler_dht()
        alertas = logica.classificar_alertas(bpm, temperatura, umidade, spo2)
        backend_ok = False
        status = "OFFLINE"

        if temperatura is None:
            status = "SEM DHT22"  # o backend exige temperatura: leitura descartada
        else:
            payload = logica.montar_payload(DEVICE_ID, agora_ms, bpm, temperatura, umidade, spo2)
            if online and sincronizar_fila():
                resultado = post_json("/api/sensores", payload)
                if resultado is not None:
                    backend_ok = True
                    status = "ONLINE"
                    ultimo_risco, ultima_faixa = resultado["risco"], resultado["faixa"]
                    for rec in resultado["recomendacoes"]:
                        print("    -> Recomendação:", rec)
            if not backend_ok:
                if fila.adicionar(payload):
                    print("[EDGE] Fila cheia - registro mais antigo descartado")
                status = "%s fila %d/%d" % (status if not online else "FALHA HTTP",
                                            len(fila), logica.MAX_REGISTROS_OFFLINE)

        print(logica.formatar_log(agora_ms, bpm, temperatura, umidade, spo2, status, alertas))
        if backend_ok:
            print("    -> Risco %.2f (%s)" % (ultimo_risco, ultima_faixa))

        led_wifi.value(1 if backend_ok else 0)
        led_alerta.value(1 if logica.led_alerta_aceso(alertas, ultima_faixa) else 0)
        atualizar_oled(logica.linhas_oled(bpm, temperatura, spo2, umidade,
                                          ultimo_risco, ultima_faixa, online, len(fila)))

        espera = INTERVALO_LEITURA_MS - time.ticks_diff(time.ticks_ms(), ciclo)
        if espera > 0:
            time.sleep_ms(espera)


main()
