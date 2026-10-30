# CardioIA Fase 7: entrega do Integrante 2 (Backend, IoT e Watson)

Documento único de entrega da parte do Integrante 2. Os números de testes, a validação do Watson, a varredura de segredos e o teste em produção foram verificados em 30/10/2026 sobre o commit `8a3a6c2` da `main`.

## 1. Resumo

| Entrega | O que é | Onde |
|---|---|---|
| API integradora | FastAPI que recebe as leituras do ESP32, calcula o risco com o modelo da F6 (RandomForest, scikit-learn 1.6.1), aplica os protocolos clínicos e conversa com o Watson | [`Backend/`](..) |
| Modelo preditivo | Artefatos da F6 copiados sem alteração (`predict.py`, `features.json`, `modelo_pico_risco.joblib`) | [`Backend/modelo/`](../modelo) |
| Firmware | MicroPython para ESP32 no Wokwi: DHT22, 2 potenciômetros (BPM e SpO2), 2 LEDs e OLED; fila offline e envio HTTPS ao backend | [`IoT/`](../../IoT) |
| Assistente | Dialog skill do Watson Assistant (F5), com saudação e despedida, pronto para upload | [`Backend/docs/watson/`](watson/cardioia-dialog-skill.json) |
| Contrato da API | Rotas, campos, limites e códigos de erro para o front-end e o firmware | [`CONTRATO_API.md`](CONTRATO_API.md) |

## 2. Links

| Recurso | Endereço |
|---|---|
| Repositório | https://github.com/JV-004/CardioIA-Fase7 |
| Backend em produção | https://cardioia-backend-djsj.onrender.com |
| Documentação interativa (Swagger) | https://cardioia-backend-djsj.onrender.com/docs |
| Status do serviço | https://cardioia-backend-djsj.onrender.com/health |
| Simulação do ESP32 (Wokwi) | https://wokwi.com/projects/479256586222505985 |

## 3. Arquitetura

```
 ESP32 (Wokwi, MicroPython)                 Backend FastAPI (Render)
 ┌───────────────────────────┐   HTTPS    ┌──────────────────────────────────────────┐
 │ DHT22, pot. BPM, pot. SpO2│──────────► │ POST /api/sensores  ou  /api/sensores/lote │
 │ fila offline (20, FIFO)   │  1 req.    │   │                                        │
 │ LEDs + OLED  ◄────────────│◄── risco ──│   ├─► features (sensor + contexto + padrão)│
 └───────────────────────────┘  por ciclo │   ├─► modelo F6 (RandomForest) -> risco    │
                                          │   ├─► faixa: baixo / moderado / alto      │
                                          │   ├─► protocolos clínicos da F6           │
                                          │   └─► histórico em memória (200)          │
 Web / Mobile (Integrante 3)              │                                          │
   GET /api/leituras (polling 5 s) ─────► │ GET /api/leituras, /api/leituras/ultima  │
   POST /api/risco (simulador)    ─────►  │ POST /api/risco (não grava)              │
   POST /api/chat                 ─────►  │ POST /api/chat ─► IBM Watson Assistant v2 │
                                          └──────────────────────────────────────────┘
```

Faixas de risco: baixo < 0,30 ≤ moderado < 0,50 ≤ alto (o modelo foi avaliado com threshold 0,5).

## 4. Endpoints

Resumo extraído do [`CONTRATO_API.md`](CONTRATO_API.md), que tem os exemplos completos e os limites de cada campo.

| Método | Rota | Entrada | Saída | Erros |
|---|---|---|---|---|
| GET | `/health` | — | `status`, `modelo_carregado`, `watson_configurado` | — |
| POST | `/api/sensores` | `device_id`, `bpm` (30–220), `temperatura` (10–45); opcionais `timestamp_ms`, `umidade` (0–100), `spo2` (50–100), `contexto` | `Leitura`: `ResultadoRisco` + `id`, `recebido_em` e os sinais. **Grava** no histórico | 401, 403, 422, 503 |
| POST | `/api/sensores/lote` | `{"leituras": [...]}`, de 1 a 100 itens | Lista de `Leitura` na mesma ordem. Item inválido recusa o lote inteiro | 401, 403, 422, 503 |
| POST | `/api/risco` | Qualquer subconjunto das 10 features do modelo (não aceita `bpm`) | `ResultadoRisco`. **Não** grava | 422, 503 |
| GET | `/api/leituras/ultima` | — | A `Leitura` mais recente | 404 |
| GET | `/api/leituras?limite=50` | `limite` de 1 a 200 | Lista de `Leitura`, mais recentes primeiro | 422 |
| POST | `/api/chat` | `mensagem` (1–2048), `session_id` opcional | `resposta`, `session_id` | 422, 503 |

`ResultadoRisco` tem: `risco`, `faixa`, `led`, `oled`, `protocolos_acionados`, `recomendacoes`, `features`, `features_padrao` e `aviso`. Qualquer rota pode responder 500 em erro inesperado, sem stack trace.

**Autenticação:** todas as rotas são públicas por design (protótipo acadêmico). As rotas `/api/sensores*` exigem o header `X-Device-Key` **somente** se a variável `DEVICE_KEY` estiver configurada no servidor. Não existe login no backend.

## 5. Firmware (IoT/)

| Componente | Pino ESP32 | Detalhe |
|---|---|---|
| DHT22 (temperatura e umidade) | GPIO4 | padrão no Wokwi: 36,5 °C e 60 % |
| Potenciômetro BPM | GPIO32 | escala 0–1023 → BPM 40–180; começa em 256 (≈ 75 BPM) |
| Potenciômetro SpO2 | GPIO33 | escala 0–1023 → SpO2 70–100 %; começa em 820 (≈ 94 %) |
| LED verde + 220 Ω | GPIO2 | aceso quando o último envio ao backend deu certo |
| LED vermelho + 220 Ω | GPIO15 | aceso com alerta local ou faixa `alto` do backend |
| OLED SSD1306 128×64 | SDA 21, SCL 22 | 4 linhas de até 16 caracteres |

Comportamento:

- **Leitura a cada 5 s.** Alertas locais: BPM > 120, temperatura > 38 °C, umidade < 40 % ou > 80 %, SpO2 < 88 %.
- **Fila offline de 20 registros, FIFO.** Quando está cheia, descarta o mais antigo.
- **Alternância online/offline a cada 30 s** (`SIMULAR_OFFLINE_30S = True`), para reproduzir o cenário de edge computing da F3. O dispositivo começa offline.
- **Uma requisição HTTPS por ciclo.** Fila vazia: `POST /api/sensores`. Fila com itens: `POST /api/sensores/lote` com a leitura atual no fim; o último resultado é o dela. A fila só é limpa quando o backend confirma.
- **Repetição só na fase de envio.** `OSError` (rede ou TLS) e `ValueError` (`BadStatusLine` do urequests) ganham uma segunda tentativa, 1 s depois, com `gc.collect()` antes de cada uma. Erro ao ler o corpo depois de um 200 não repete.
- **Limites do payload.** Cada valor é limitado à faixa aceita pelo backend antes do envio; os alertas locais usam o valor bruto. Se o backend recusar com 4xx de dado inválido (ex.: 422), a leitura é descartada, ou no lote a fila é descartada, em vez de travar a fila. Falha de rede, 5xx, 401, 403, 408 e 429 mantêm a leitura na fila.
- **Configuração em `IoT/main.py`:** `BACKEND_URL = "https://cardioia-backend-djsj.onrender.com"` e `DEVICE_KEY = ""`.

## 6. Watson

- **JSON do skill:** [`Backend/docs/watson/cardioia-dialog-skill.json`](watson/cardioia-dialog-skill.json): 23 intents, 5 entities, 10 nós. Não contém credenciais.
- **Validação:** `python -I Backend/scripts/validar_watson_json.py`. O script confere a cadeia de nós, o fallback no fim e textos sem aspas literais ou emojis.
- **Como subir:** no IBM Cloud, abra o assistant no ambiente **Draft**, vá em **Dialog → Options → Upload/Download** e faça **Upload** do JSON. O upload substitui o skill atual.
- **Variáveis de ambiente do backend** (só os nomes; os valores ficam no `.env` local ou no painel do Render):

| Variável | Obrigatória |
|---|---|
| `WATSON_API_KEY` | sim |
| `WATSON_SERVICE_URL` | sim |
| `WATSON_ASSISTANT_ID` | sim |
| `WATSON_ENVIRONMENT_ID` | sim (ID do ambiente Draft; descubra com `Backend/scripts/descobrir_environment_id.py`) |
| `WATSON_VERSION` | não (padrão `2021-06-14`) |
| `WATSON_USER_ID` | não (padrão `cardioia-anonimo`) |

Sem qualquer uma das 4 obrigatórias, `/api/chat` responde 503 e o resto da API continua funcionando.

## 7. Como rodar localmente

Backend (Python 3.11):

```bash
cd Backend
py -3.11 -m venv .venv            # Linux/macOS: python3.11 -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux/macOS: cp .env.example .env  (preencha se quiser o chat)
uvicorn app.main:app --reload     # http://localhost:8000/docs
```

Testes:

```bash
cd Backend && pytest                       # backend
cd .. && python -m pytest IoT/tests        # firmware (com o venv do Backend ativado)
python -I Backend/scripts/validar_watson_json.py
```

IoT: abra o projeto https://wokwi.com/projects/479256586222505985 e clique em **Start**. Para montar uma cópia, siga o [`IoT/README.md`](../../IoT/README.md). Antes da demonstração, abra `/health` para acordar o Render.

## 8. Como reproduzir o risco ALTO no Wokwi

Com a simulação online, ajuste:

| Sensor | Valor alvo | Como |
|---|---|---|
| BPM | ≈ 145 | potenciômetro de BPM em ≈ 769 (de 0 a 1023) |
| SpO2 | ≈ 77 % | potenciômetro de SpO2 em ≈ 240 (de 0 a 1023) |
| Temperatura | ≈ 39 °C | clique no DHT22 e ajuste a temperatura |

Resultado esperado, conferido com o modelo real:

- terminal: `ALERTA: taquicardia, febre, spo2_baixa` e `-> Risco 0.86 (alto)`;
- OLED: `BPM 145 T39.0C`, `SpO2 77% U60%`, `Risco 86% ALTO`, `WiFi ON Fila 0`;
- **os dois LEDs acesos**: verde (envio OK) e vermelho (alerta local e faixa alta);
- protocolos acionados: `suporte_respiratorio`, `monitoramento_intensivo`, `protocolo_infeccioso` e `estado_emergencia`.

A faixa só aparece depois que o backend responde, ou seja, numa janela online.

## 9. Testes

Resultados em 30/10/2026, commit `8a3a6c2`:

| Verificação | Resultado |
|---|---|
| `pytest` no Backend | **90 passed** |
| `pytest IoT/tests` | **61 passed** |
| `validar_watson_json.py` | **VÁLIDO** (10 nós, 23 intents, 5 entities) |
| Varredura de segredos (árvore e histórico, 63 commits) | nenhuma chave, token, senha ou URL com credencial; `.env` não versionado |
| `GET /health` em produção | 200, `modelo_carregado: true`, `watson_configurado: true` |
| `POST /api/risco` em produção (caso da F6) | 200, risco 1.0, faixa alto, 4 protocolos |
| Correções da auditoria em produção | `NaN` no corpo responde 422 (antes 500) |

## 10. Limitações conhecidas

| Limitação | Impacto |
|---|---|
| Histórico em memória (últimas 200 leituras) | Some quando o serviço reinicia; os `id` recomeçam em 1 |
| Render free hiberna após ~15 min sem tráfego | A primeira requisição leva até ~1 min; abra `/health` antes de demonstrar |
| Repetição em `BadStatusLine` | Se o backend já tinha gravado antes de a conexão cair, a segunda tentativa grava a mesma leitura de novo |
| Sem idempotência | O backend não reconhece reenvio da mesma leitura; não há chave de deduplicação |
| Wokwi com a aba em segundo plano | A simulação fica muito lenta; mantenha a aba em primeiro plano |
| Rotas públicas e login só local nos apps | Qualquer pessoa com a URL lê o histórico; adequado só para protótipo |

## 11. Evidências

Os prints ficam em [`Backend/docs/evidencias/`](evidencias/). Lista esperada:

| Arquivo sugerido | Conteúdo |
|---|---|
| `01-terminal-online-risco-alto.png` | Terminal do Wokwi online com `-> Risco 0.86 (alto)` |
| `02-oled-leds.png` | Circuito com o OLED mostrando `Risco 86% ALTO` e os dois LEDs acesos |
| `03-swagger-docs.png` | Página `/docs` do backend em produção |
| `04-chat-sem-aspas.png` | Resposta de `/api/chat` sem aspas literais (depois do upload do skill no Draft) |

## 12. Checklist final

Verificado nesta entrega:

- [x] Árvore limpa e `main` igual à `origin/main`
- [x] Testes do Backend passando (90)
- [x] Testes do IoT passando (61)
- [x] Dialog skill do Watson válido (10 nós, cadeia íntegra)
- [x] Nenhum segredo na árvore nem no histórico; `.env` fora do Git
- [x] Backend em produção respondendo (`/health` e `/api/risco`)
- [x] Produção já com as correções da auditoria (`NaN` → 422)
- [x] `IoT/main.py` com a URL de produção e `DEVICE_KEY = ""`
- [x] `IoT/diagram.json` com os valores padrão (BPM 256, SpO2 820, DHT22 36,5 °C / 60 %)
- [x] Cenário de risco alto conferido com o modelo (0.86, `Risco 86% ALTO`)

Depende do usuário:

- [ ] Fazer o upload do `cardioia-dialog-skill.json` no Watson, ambiente Draft
- [ ] Colar o `IoT/main.py` e o `IoT/logica.py` atuais no projeto do Wokwi
- [ ] Adicionar os prints em `Backend/docs/evidencias/`
- [ ] Confirmar no painel do Render que o deploy Live é o último commit da `main`
