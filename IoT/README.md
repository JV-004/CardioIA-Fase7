# CardioIA Fase 7: IoT em MicroPython (ESP32 + Wokwi)

Esta é a conversão do firmware C++ da Fase 3 (`sketch.ino`) para MicroPython. Agora as leituras são enviadas ao backend Python, que devolve o risco calculado pelo modelo da F6.

```
DHT22 + potenciômetros ─► ESP32 (MicroPython) ─► POST /api/sensores ─► Backend ─► modelo F6
                              │  sem conexão: fila offline (20) ─► POST /api/sensores/lote ao reconectar
                              └► LED verde / LED vermelho / OLED (risco devolvido pelo backend)
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `main.py` | Parte que depende do hardware: pinos, ADC, DHT22, WiFi, HTTP, LEDs, OLED e loop de 5 s |
| `logica.py` | Lógica pura: limites de alerta, fila FIFO, payload, linhas do OLED e log. Roda também em CPython. |
| `ssd1306.py` | Driver do OLED (micropython-lib, licença MIT) |
| `diagram.json` | Circuito do Wokwi |
| `tests/test_logica.py` | Testes do `logica.py` com pytest |

## Circuito

| Componente | Pino ESP32 | Observação |
|---|---|---|
| DHT22 (temperatura/umidade) | GPIO4 | igual à F3 |
| Potenciômetro **BPM** | GPIO32 | mapeado de 40 a 180 BPM |
| Potenciômetro **SpO2** | GPIO33 | **novo**, mapeado de 70 a 100 % |
| LED verde + 220 Ω | GPIO2 | aceso quando WiFi e backend estão OK (o último POST deu certo) |
| LED vermelho + 220 Ω | GPIO15 | aceso com alerta local **ou** faixa `alto` devolvida pelo backend |
| OLED SSD1306 128×64 (I2C 0x3C) | SDA 21, SCL 22 | 4 linhas, detalhadas abaixo |

### Por que o potenciômetro da F3 lia sempre o máximo do ADC

O `diagram.json` da F3 ligava GND em `esp:GND`, mas no `board-esp32-devkit-c-v4` os pinos de terra se chamam `GND.1`, `GND.2` e `GND.3`. Com o GND sem ligação, o pino SIG ficava preso ao VCC e o ADC marcava 4095. Os LEDs da F3 também estavam ligados nesse pino inexistente e não tinham resistor.

Neste diagrama, todas as ligações usam os nomes corretos (`GND.1`/`GND.2`). Se mesmo assim o ADC continuar travado, verifique no editor do Wokwi se SIG, GND e VCC do potenciômetro estão ligados. Só depois disso use `BPM_ALEATORIO = True` em `main.py`, que gera BPM aleatório de 60 a 115 como na F3.

## Lógica (equivalente à F3)

- Leitura a cada **5 s**.
- Alertas locais com comparações estritas, como na F3: BPM > 120 (taquicardia), temperatura > 38 °C (febre), umidade < 40 % ou > 80 %, e o novo SpO2 < 88 % (mesmo limiar do protocolo do backend).
- **Fila offline FIFO de 20 registros.** Quando está cheia, descarta o registro mais antigo.
- Ao reconectar, envia a fila inteira em `/api/sensores/lote`. A fila só é limpa se o backend confirmar o recebimento. Depois disso, envia a leitura atual.
- `SIMULAR_OFFLINE_30S = True`: começa **offline** e alterna online/offline a cada 30 s, como na F3, para a demonstração mostrar a fila enchendo e sendo sincronizada. Com `False`, o dispositivo usa só o estado real do WiFi.
- Se o DHT22 falhar, a leitura não é enviada, porque o backend exige temperatura.

### OLED (16 caracteres por linha)

O `framebuf.text()` do MicroPython usa fonte 8×8, então cabem 128/8 = **16 colunas**. As linhas são montadas no próprio dispositivo:

```
BPM 72 T36.5C
SpO2 97% U60%
Risco 12% BAIXO      <- "Risco --" até o backend responder; faixas: BAIXO / MOD / ALTO
WiFi ON Fila 0       <- ou "OFFLINE Fila 3"
```

## Como rodar no Wokwi

1. Acesse <https://wokwi.com>, faça login e crie um projeto **ESP32 → MicroPython on ESP32**.
2. No editor, substitua o conteúdo de `main.py` e `diagram.json` pelo destes arquivos.
   - Se o template trouxer outro valor em `"env"` no `diagram.json`, mantenha o valor do template.
3. Crie dois arquivos pelo menu de arquivos (seta ▾ ao lado das abas → **New file…**): `logica.py` e `ssd1306.py`. Cole o conteúdo de cada um.
4. No topo do `main.py`, ajuste:
   ```python
   BACKEND_URL = "https://SEU-BACKEND.onrender.com"   # sem barra no final
   DEVICE_KEY = ""   # use o mesmo valor de DEVICE_KEY do Render, se tiver configurado
   ```
5. Clique em **▶ Start**. Antes da demonstração, abra `https://SEU-BACKEND.onrender.com/health` no navegador para acordar o Render free. Enquanto ele não responde, as leituras entram na fila.
6. Clique em um potenciômetro e arraste o controle deslizante para mudar o BPM ou o SpO2. Clique no DHT22 para mudar a temperatura e a umidade.

### Publicar o link público

Clique em **Save** e depois em **Share**. Copie o link (`https://wokwi.com/projects/<id>`) e confira se ele abre numa janela anônima. Esse é o link que vai no README da raiz e no relatório.

> O projeto Wokwi é público. Não coloque credenciais reais em `main.py`. A `DEVICE_KEY` é apenas de demonstração.

## Saída esperada no terminal

Exemplo **ilustrativo**, montado a partir do formato do `main.py` e de respostas reais do backend local. Não é uma captura do Wokwi: substitua por um print da sua execução no relatório.

```
========================================
  CardioIA - Fase 7 (MicroPython)
  Sensor -> MicroPython -> Backend -> IA
========================================
Backend: https://SEU-BACKEND.onrender.com
Simular offline a cada 30 s: True
[WIFI] Conectando em Wokwi-GUEST......
[WIFI] Conectado: 10.10.0.2

[WIFI] DESCONECTADO - armazenamento local (edge) ativo
[0ms] BPM: 110 | Temp: 36.5C | Umidade: 60.0% | SpO2: 85% | Status: OFFLINE fila 1/20
[5003ms] BPM: 110 | Temp: 36.5C | Umidade: 60.0% | SpO2: 85% | Status: OFFLINE fila 2/20
...
[WIFI] CONECTADO - modo online
========================================
[SYNC] Sincronizando 6 registro(s) offline...
  id=1 bpm=110.0 risco=0.00 faixa=baixo
  ...
[SYNC] Concluído. Fila limpa.
========================================
    -> Recomendação: Suporte respiratório imediato
[30012ms] BPM: 130 | Temp: 38.6C | Umidade: 60.0% | SpO2: 86% | Status: ONLINE | ALERTA: taquicardia, febre, spo2_baixa
    -> Risco 0.85 (alto)
```

Os valores dependem da posição dos potenciômetros e do DHT22. Com os potenciômetros no meio do curso, o BPM fica em ~110 e o SpO2 em ~85.

## Testes da lógica (no computador)

```bash
# a partir da raiz do repositório, com o venv do Backend ativado
python -m pytest IoT/tests
```
