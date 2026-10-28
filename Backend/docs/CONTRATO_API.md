# Contrato da API — CardioIA Fase 7

Backend integrador (FastAPI). Consumidores: firmware do ESP32 (`IoT/`), app Web (React + Vite) e app Mobile (Expo).

- **URL base (produção):** `https://SEU-BACKEND.onrender.com`. O Integrante 2 informa a URL real depois do deploy.
- **URL base (local):** `http://localhost:8000`
- **Formato:** JSON (UTF-8) em todas as rotas.
- **Documentação interativa:** `GET /docs` (Swagger) e `GET /openapi.json`.
- **CORS:** aceita qualquer `https://*.vercel.app`, as origens de `CORS_ORIGINS` e, fora de produção, `http://localhost:*`.

> Toda resposta clínica traz o campo `aviso`: *"Protótipo acadêmico com dados sintéticos; não substitui avaliação médica."* A interface deve exibi-lo.

## Resumo

| Método | Rota | Uso | Autenticação |
|---|---|---|---|
| GET | `/health` | Status do serviço | — |
| POST | `/api/sensores` | Leitura do ESP32 (avalia e **armazena**) | `X-Device-Key` se configurada |
| POST | `/api/sensores/lote` | Fila offline do ESP32 (avalia e **armazena**) | `X-Device-Key` se configurada |
| POST | `/api/risco` | Simulação de risco (**não** armazena) | — |
| GET | `/api/leituras/ultima` | Última leitura recebida | — |
| GET | `/api/leituras?limite=50` | Histórico, mais recentes primeiro | — |
| POST | `/api/chat` | Assistente conversacional (Watson, F5) | — |

## Objeto `ResultadoRisco`

É devolvido por `/api/risco` e faz parte de toda leitura.

| Campo | Tipo | Descrição |
|---|---|---|
| `risco` | float 0–1 | Probabilidade de pico de risco (modelo F6), 4 casas |
| `faixa` | `"baixo"` \| `"moderado"` \| `"alto"` | baixo < 0,30 ≤ moderado < 0,50 ≤ alto |
| `led` | `"verde"` \| `"amarelo"` \| `"vermelho"` | Cor sugerida para a faixa |
| `oled` | string[] | Até 4 linhas ASCII de até 21 caracteres (resumo curto) |
| `protocolos_acionados` | string[] | Códigos (tabela abaixo) |
| `recomendacoes` | string[] | Texto das ações, na mesma ordem dos códigos |
| `features` | objeto | As 10 features efetivamente enviadas ao modelo |
| `features_padrao` | string[] | Features que **não** vieram na requisição e foram preenchidas por valor padrão. Mostre isso na UI. |
| `aviso` | string | Aviso legal fixo |

### Objeto `Leitura` (= `ResultadoRisco` + dados da leitura)

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | int | Sequencial; recomeça em 1 quando o serviço reinicia |
| `recebido_em` | string ISO 8601 (UTC) | Momento em que o backend recebeu a leitura |
| `device_id` | string | Identificador do dispositivo |
| `timestamp_ms` | int \| null | `millis()` do ESP32 (tempo desde o boot, não é data) |
| `bpm`, `temperatura` | float | Sinais medidos |
| `umidade`, `spo2` | float \| null | Sinais opcionais |

### Protocolos

| Código | Condição | Recomendação |
|---|---|---|
| `suporte_respiratorio` | spo2_media < 88 | Suporte respiratório imediato |
| `unidades_temporarias` | carga_sistema > 85 | Abrir unidades temporárias |
| `monitoramento_intensivo` | fc_media > 120 | Monitoramento intensivo |
| `resposta_rapida` | eventos_24h > 5 | Acionar equipe de resposta rápida |
| `redistribuir_insumos` | disponibilidade_recursos < 30 | Redistribuir insumos |
| `triagem_emergencial` | tempo_espera > 90 | Priorizar triagem emergencial |
| `protocolo_infeccioso` | temperatura > 38 | Protocolo infeccioso |
| `plano_contingencia` | densidade_eventos > 6 | Plano de contingência |
| `protocolo_choque` | pa_sistolica < 90 | Protocolo de choque |
| `estado_emergencia` | faixa == "alto" | Ativar estado de emergência (sempre o último da lista) |

## Rotas

### `GET /health`

```json
{"status":"ok","modelo_carregado":true,"watson_configurado":false}
```

Se `modelo_carregado` for `false`, as rotas de risco e de sensores respondem 503. Se `watson_configurado` for `false`, `/api/chat` responde 503. Dá para esconder o chat na UI com base nesse campo.

### `POST /api/sensores`

Body:

| Campo | Tipo | Obrigatório | Limites |
|---|---|---|---|
| `device_id` | string | sim | 1–64 caracteres |
| `timestamp_ms` | int | não | ≥ 0 |
| `bpm` | número | sim | 30–220 → `fc_media` |
| `temperatura` | número | sim | 10–45 → `temperatura` |
| `umidade` | número | não | 0–100 (não entra no modelo) |
| `spo2` | número | não | 50–100 → `spo2_media` |
| `contexto` | objeto | não | Qualquer subconjunto das 8 features abaixo |

Features aceitas em `contexto`: `idade_media`, `carga_sistema`, `tempo_espera`, `spo2_media`, `pa_sistolica`, `densidade_eventos`, `eventos_24h`, `disponibilidade_recursos`. As chaves são normalizadas, então `"Carga Sistema"` vira `carga_sistema`. Chave desconhecida gera 422.

Ordem de prioridade: sinal do sensor > `contexto` > valor padrão. Valores padrão (faixa normal): idade_media 55, carga_sistema 50, tempo_espera 30, spo2_media 97, pa_sistolica 120, densidade_eventos 3, eventos_24h 2, disponibilidade_recursos 70.

Request:

```json
{"device_id":"esp32-wokwi-01","timestamp_ms":5000,"bpm":72,"temperatura":36.5,"umidade":60,"spo2":97}
```

Response 200 (saída real):

```json
{
  "risco": 0.0, "faixa": "baixo", "led": "verde",
  "oled": ["Risco 0% BAIXO", "FC72 T36.5 O2 97", "Protocolos: 0", "Sem protocolos"],
  "protocolos_acionados": [], "recomendacoes": [],
  "features": {"fc_media": 72.0, "temperatura": 36.5, "spo2_media": 97.0, "idade_media": 55.0,
               "carga_sistema": 50.0, "tempo_espera": 30.0, "pa_sistolica": 120.0,
               "densidade_eventos": 3.0, "eventos_24h": 2.0, "disponibilidade_recursos": 70.0},
  "features_padrao": ["idade_media", "carga_sistema", "tempo_espera", "pa_sistolica",
                      "densidade_eventos", "eventos_24h", "disponibilidade_recursos"],
  "aviso": "Protótipo acadêmico com dados sintéticos; não substitui avaliação médica.",
  "id": 1, "recebido_em": "2026-10-26T23:21:49+00:00", "device_id": "esp32-wokwi-01",
  "timestamp_ms": 5000, "bpm": 72.0, "temperatura": 36.5, "umidade": 60.0, "spo2": 97.0
}
```

### `POST /api/sensores/lote`

Usado pelo ESP32 para enviar a fila offline. Body: `{"leituras": [Leitura de sensor, ...]}`, com 1 a 100 itens. Responde com uma lista de `Leitura` **na mesma ordem** do envio. Se um item for inválido, o lote inteiro é recusado com 422 e nada é armazenado.

```json
{"leituras":[
  {"device_id":"esp32-wokwi-01","timestamp_ms":10000,"bpm":95,"temperatura":37.0,"spo2":95},
  {"device_id":"esp32-wokwi-01","timestamp_ms":15000,"bpm":135,"temperatura":38.6,"spo2":86}
]}
```

### `POST /api/risco`

Simulador ("e se?") para a UI. Recebe qualquer subconjunto das 10 features e **não armazena** nada. Valem a mesma normalização e os mesmos valores padrão. Se faltarem `fc_media` e `temperatura`, entram 75 e 36,5, e elas também aparecem em `features_padrao`.

Request (caso do enunciado da F6; repare na chave com espaço):

```json
{"idade_media":62,"carga_sistema":92,"tempo_espera":75,"fc_media":118,"spo2_media":89,
 "pa_sistolica":100,"temperatura":37.5,"densidade_eventos":7,"eventos_24h":5,
 "disponibilidade recursos":25}
```

Response 200 (saída real):

```json
{
  "risco": 1.0, "faixa": "alto", "led": "vermelho",
  "oled": ["Risco 100% ALTO", "FC118 T37.5 O2 89", "Protocolos: 4", "ESTADO DE EMERGENCIA"],
  "protocolos_acionados": ["unidades_temporarias", "redistribuir_insumos", "plano_contingencia", "estado_emergencia"],
  "recomendacoes": ["Abrir unidades temporárias", "Redistribuir insumos", "Plano de contingência", "Ativar estado de emergência"],
  "features": {"idade_media": 62.0, "carga_sistema": 92.0, "tempo_espera": 75.0, "spo2_media": 89.0,
               "pa_sistolica": 100.0, "densidade_eventos": 7.0, "eventos_24h": 5.0,
               "disponibilidade_recursos": 25.0, "fc_media": 118.0, "temperatura": 37.5},
  "features_padrao": [],
  "aviso": "Protótipo acadêmico com dados sintéticos; não substitui avaliação médica."
}
```

### `GET /api/leituras/ultima`

Devolve a `Leitura` mais recente. Responde 404 com `{"detail":"Nenhuma leitura recebida desde que o serviço iniciou."}` enquanto não houver leitura.

### `GET /api/leituras?limite=50`

Lista de `Leitura`, das mais recentes para as mais antigas. `limite` vai de 1 a 200 (padrão 50). Para tempo real, faça **polling a cada 5 s** (mesmo intervalo do ESP32) e use `id` para detectar leituras novas.

> O histórico fica **em memória** (últimas 200 leituras) e é apagado quando o serviço reinicia. No plano free do Render isso acontece depois de cerca de 15 min sem tráfego, e a primeira requisição seguinte pode levar até ~50 s.

### `POST /api/chat`

Request: `{"mensagem": "Estou com dor no peito", "session_id": "opcional"}` (mensagem com 1 a 2048 caracteres).

Response 200: `{"resposta": "texto do Watson", "session_id": "..."}`. Guarde o `session_id` e envie-o de volta nas mensagens seguintes. Se a sessão expirar, o backend cria outra sozinho e devolve o novo `session_id`.

Response 503 (Watson sem credenciais, com erro de rede ou erro da API):

```json
{"detail":"Assistente conversacional não configurado no servidor (defina WATSON_API_KEY, WATSON_SERVICE_URL, WATSON_ASSISTANT_ID e WATSON_ENVIRONMENT_ID)."}
```

## Códigos de erro

Todos os erros têm o formato `{"detail": ...}`.

| Código | Quando | `detail` |
|---|---|---|
| 401 | `DEVICE_KEY` configurada e header `X-Device-Key` ausente (rotas `/api/sensores*`) | `"Header X-Device-Key ausente."` |
| 403 | `X-Device-Key` incorreta | `"X-Device-Key inválida."` |
| 404 | `/api/leituras/ultima` sem leituras | texto |
| 422 | Validação: campo obrigatório ausente, valor fora dos limites, chave desconhecida ou duplicada | **lista** de erros do pydantic (ex.: `[{"loc":["body","bpm"],"msg":"Input should be less than or equal to 220", ...}]`) |
| 500 | Erro inesperado (sem stack trace) | `"Erro interno no servidor."` |
| 503 | Modelo não carregado, ou Watson indisponível | texto em português |

Exemplo de 422 (bpm = 250):

```json
{"detail":[{"type":"less_than_equal","loc":["body","bpm"],"msg":"Input should be less than or equal to 220","input":250,"ctx":{"le":220.0}}]}
```
