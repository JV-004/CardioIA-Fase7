# CardioIA Fase 7: IoT em MicroPython (ESP32 + Wokwi)

Esta é a conversão do firmware C++ da Fase 3 (`sketch.ino`) para MicroPython. Agora as leituras são enviadas ao backend Python, que devolve o risco calculado pelo modelo da F6.

```
DHT22 + potenciômetros ─► ESP32 (MicroPython) ─► POST /api/sensores ─► Backend ─► modelo F6
                              │  sem conexão: fila offline (20) ─► POST /api/sensores/lote ao reconectar
                              └► LED verde / LED vermelho / OLED (risco devolvido pelo backend)
```

- **Simulação pública no Wokwi:** https://wokwi.com/projects/479256586222505985
- **Backend usado:** https://cardioia-backend-djsj.onrender.com (Render free: **hiberna após ~15 min; abra `/health` antes da demonstração**).

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `main.py` | Parte que depende do hardware: pinos, ADC, DHT22, WiFi, HTTP, LEDs, OLED e loop de 5 s |
| `logica.py` | Lógica pura: limites de alerta, fila FIFO, payload, linhas do OLED e log. Roda também em CPython. |
| `ssd1306.py` | Driver do OLED (micropython-lib, licença MIT) |
| `diagram.json` | Circuito do Wokwi |
| `tests/test_logica.py` | Testes do `logica.py` com pytest |
| `tests/test_post_json.py` | Testes da repetição do `post_json` do `main.py` (extrai as funções reais e usa um `requests` falso) |

## Circuito

| Componente | Pino ESP32 | Observação |
|---|---|---|
| DHT22 (temperatura/umidade) | GPIO4 | igual à F3 |
| Potenciômetro **BPM** | GPIO32 | mapeado de 40 a 180 BPM; começa em `value` 256 → **~75 BPM** |
| Potenciômetro **SpO2** | GPIO33 | **novo**, mapeado de 70 a 100 %; começa em `value` 820 → **~94 %** |
| LED verde + 220 Ω | GPIO2 | aceso quando WiFi e backend estão OK (o último POST deu certo) |
| LED vermelho + 220 Ω | GPIO15 | aceso com alerta local **ou** faixa `alto` devolvida pelo backend |
| OLED SSD1306 128×64 (I2C 0x3C) | SDA 21, SCL 22 | 4 linhas, detalhadas abaixo |

### Por que o potenciômetro da F3 lia sempre o máximo do ADC

O `diagram.json` da F3 ligava GND em `esp:GND`, mas no `board-esp32-devkit-c-v4` os pinos de terra se chamam `GND.1`, `GND.2` e `GND.3`. Com o GND sem ligação, o pino SIG ficava preso ao VCC e o ADC marcava 4095. Os LEDs da F3 também estavam ligados nesse pino inexistente e não tinham resistor.

Neste diagrama, todas as ligações usam os nomes corretos (`GND.1`/`GND.2`). Se mesmo assim o ADC continuar travado, verifique no editor do Wokwi se SIG, GND e VCC do potenciômetro estão ligados. Só depois disso use `BPM_ALEATORIO = True` em `main.py`, que gera BPM aleatório de 60 a 115 como na F3.

## Lógica (equivalente à F3)

- Leitura a cada **5 s**.
- Envio HTTP com timeout de 10 s. Antes de cada tentativa roda `gc.collect()` (o TLS precisa de RAM livre). Falha na conexão/envio (`OSError`, ou `ValueError` "BadStatusLine" do urequests quando o TLS cai no meio da resposta) ganha **mais uma tentativa**, 1 s depois, antes de a leitura ir para a fila. Status diferente de 200 e erro ao ler o corpo depois de um 200 não repetem (o backend já gravou).
- Alertas locais com comparações estritas, como na F3: BPM > 120 (taquicardia), temperatura > 38 °C (febre), umidade < 40 % ou > 80 %, e o novo SpO2 < 88 % (mesmo limiar do protocolo do backend).
- **Fila offline FIFO de 20 registros.** Quando está cheia, descarta o registro mais antigo.
- **Uma requisição HTTPS por ciclo.** Com a fila vazia, a leitura vai em `POST /api/sensores`. Com itens na fila (por exemplo, ao reconectar), a leitura atual vai **no fim do lote** em `POST /api/sensores/lote`, e o último resultado do lote é o dela. Duas requisições seguidas no mesmo ciclo faziam a segunda falhar no Wokwi (`OSError(16)` / `MBEDTLS_ERR_SSL_CONN_EOF`). A fila só é limpa se o backend confirmar; se o lote falhar, a leitura atual entra no fim da fila.
- **Limites e descarte:** antes do envio, cada valor é limitado à faixa aceita pelo backend (BPM 30–220, temperatura 10–45 °C, umidade 0–100 %, SpO2 50–100 %); os alertas locais continuam usando o valor bruto do sensor. Se mesmo assim o backend recusar com 4xx de dado inválido (ex.: 422), a leitura é descartada (`[DESCARTADO]`) ou, no lote, a fila inteira é descartada (`[SYNC] Lote recusado`), em vez de travar a fila para sempre. Falha de rede, 5xx e 4xx temporários (401/403 de `DEVICE_KEY` errada, 408, 429) mantêm a leitura na fila.
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
   - O `diagram.json` fixa o MicroPython em `"env": "micropython-20260406-v1.28.0"`. Se o Wokwi recusar esse valor, use o `"env"` que vier no template.
3. Crie dois arquivos pelo menu de arquivos (seta ▾ ao lado das abas → **New file…**): `logica.py` e `ssd1306.py`. Cole o conteúdo de cada um.
4. No topo do `main.py`, ajuste:
   ```python
   BACKEND_URL = "https://cardioia-backend-djsj.onrender.com"   # sem barra no final
   DEVICE_KEY = ""   # use o mesmo valor de DEVICE_KEY do Render, se tiver configurado
   ```
5. Clique em **▶ Start**. Antes da demonstração, abra `https://cardioia-backend-djsj.onrender.com/health` no navegador para acordar o Render free. Enquanto ele não responde, as leituras entram na fila.
6. Clique em um potenciômetro e arraste o controle deslizante para mudar o BPM ou o SpO2. Clique no DHT22 para mudar a temperatura e a umidade.

   Os potenciômetros já começam numa posição de repouso: **BPM ~75** e **SpO2 ~94 %**. No Wokwi, a posição (`value` no `diagram.json`) vai de **0 a 1023**, e o firmware a converte para o ADC de 12 bits (0–4095) antes de mapear para BPM 40–180 e SpO2 70–100. Para simular taquicardia, por exemplo, leve o potenciômetro de BPM a ~592 ou mais (BPM > 120); para SpO2 baixa, leve o de SpO2 a ~613 ou menos (SpO2 < 88).

### Publicar o link público

Projeto publicado: **https://wokwi.com/projects/479256586222505985**.

Para publicar uma cópia sua, clique em **Save** e depois em **Share**, copie o link (`https://wokwi.com/projects/<id>`) e confira se ele abre numa janela anônima.

> O projeto Wokwi é público. Não coloque credenciais reais em `main.py`. A `DEVICE_KEY` é apenas de demonstração.

## Saída real no terminal

Captura de uma execução no Wokwi (https://wokwi.com/projects/479256586222505985) contra o backend publicado, com os potenciômetros na posição inicial (BPM 75, SpO2 94 %, sem alerta):

```
[WIFI] Conectando em Wokwi-GUEST.........
[WIFI] Conectado: 10.10.0.2
[WIFI] DESCONECTADO - armazenamento local (edge) ativo
[0ms] BPM: 75 | Temp: 36.5C | Umidade: 60.0% | SpO2: 94% | Status: OFFLINE fila 1/20
[5001ms] BPM: 75 | Temp: 36.5C | Umidade: 60.0% | SpO2: 94% | Status: OFFLINE fila 2/20
...
[25001ms] BPM: 75 | Temp: 36.5C | Umidade: 60.0% | SpO2: 94% | Status: OFFLINE fila 6/20
[WIFI] CONECTADO - modo online
========================================
[SYNC] Sincronizando 6 registro(s) offline...
  id=49 bpm=75.0 risco=0.00 faixa=baixo
  ...
  id=54 bpm=75.0 risco=0.00 faixa=baixo
[SYNC] Concluído. Fila limpa.
========================================
[HTTP] Falha em /api/sensores -> OSError(-29312, 'MBEDTLS_ERR_SSL_CONN_EOF')
[30002ms] BPM: 75 | Temp: 36.5C | Umidade: 60.0% | SpO2: 94% | Status: FALHA HTTP fila 1/20
[SYNC] Sincronizando 1 registro(s) offline...
  id=55 bpm=75.0 risco=0.00 faixa=baixo
[SYNC] Concluído. Fila limpa.
[42915ms] BPM: 75 | Temp: 36.5C | Umidade: 60.0% | SpO2: 94% | Status: ONLINE
    -> Risco 0.00 (baixo)
```

O que a captura mostra:

- **Edge / fila offline:** nos primeiros 30 s (offline simulado), 6 leituras entram na fila e são sincronizadas em lote ao reconectar (ids 49–54).
- **Falha de TLS intermitente:** o `MBEDTLS_ERR_SSL_CONN_EOF` é um fechamento inesperado da conexão TLS, observado de forma intermitente no Wokwi. A leitura foi para a fila e entrou no lote seguinte (id 55), sem perda de dado. Com a repetição automática em caso de `OSError`, ele tende a não aparecer, e a fila cobre quando aparece.
- **Fluxo de envio:** a captura também é anterior à regra de uma requisição por ciclo. Hoje, ao reconectar, sai uma única linha `[SYNC] Enviando 6 registro(s) offline + leitura atual em lote...`, e o lote traz 7 resultados (a leitura atual é o último), sem um POST separado em seguida.
- **Formato da mensagem de falha:** a captura foi feita antes da repetição automática. Na versão atual, a falha aparece como `[HTTP] Falha de rede em /api/sensores (tentativa 1/2) -> OSError(...)`, seguida da segunda tentativa.
- **IDs a partir de 49:** o backend já tinha recebido leituras antes desta execução. Os ids recomeçam em 1 quando o Render reinicia.

Os valores dependem da posição dos potenciômetros e do DHT22. Na posição inicial do `diagram.json`, o BPM fica em ~75 e o SpO2 em ~94 %; com os potenciômetros no meio do curso (~512), ficam em ~110 e ~85 %.

## Testes da lógica (no computador)

```bash
# a partir da raiz do repositório, com o venv do Backend ativado
python -m pytest IoT/tests
```
