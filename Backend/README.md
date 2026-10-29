# CardioIA Fase 7: Backend integrador

Serviço Python (FastAPI) que liga as peças do CardioIA:

```
ESP32 (MicroPython) ──POST /api/sensores──►  Backend  ──► Modelo preditivo F6 (scikit-learn)
                                               │   └──► Protocolos clínicos F6
Web / Mobile ◄──GET /api/leituras── histórico  │
Web / Mobile ──POST /api/chat──────────────────┴──► IBM Watson Assistant v2 (F5)
```

O contrato completo das rotas, com exemplos e códigos de erro, está em **[docs/CONTRATO_API.md](docs/CONTRATO_API.md)**. A documentação interativa fica em `/docs`.

## Estrutura

```
Backend/
  app/
    main.py            rotas, CORS, X-Device-Key e tratamento de erros
    config.py          variáveis de ambiente, limiares e valores padrão
    schemas.py         modelos pydantic (validação e limites)
    services/
      risco.py         features → modelo → faixa → protocolos (+ ponto de extensão p/ agentes F6)
      protocolos.py    tabela de protocolos (dados) + função pura
      leituras.py      histórico em memória (deque de 200 com Lock)
      watson.py        Watson Assistant v2 (sessões, expiração e erros)
  modelo/              artefatos da F6 copiados sem alteração (predict.py, features.json, .joblib)
  tests/               pytest
  requirements.txt  .env.example  render.yaml  pytest.ini
```

## Rodar localmente

É necessário o **Python 3.11**, porque o `.joblib` exige `scikit-learn==1.6.1`.

```bash
cd Backend
py -3.11 -m venv .venv            # Linux/macOS: python3.11 -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Linux/macOS: cp .env.example .env  (depois preencha)
uvicorn app.main:app --reload     # http://localhost:8000/docs
pytest
```

Teste rápido:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/sensores -H "Content-Type: application/json" \
  -d '{"device_id":"teste","bpm":72,"temperatura":36.5,"spo2":97}'
```

## Variáveis de ambiente

| Variável | Padrão | Uso |
|---|---|---|
| `AMBIENTE` | `desenvolvimento` | Com `producao`, o CORS deixa de aceitar `localhost` |
| `CORS_ORIGINS` | vazio | Origens extras, separadas por vírgula (`*.vercel.app` já é aceito) |
| `DEVICE_KEY` | vazio | Se preenchida, `POST /api/sensores*` exige o header `X-Device-Key` |
| `WATSON_API_KEY` | vazio | API key do IBM Cloud |
| `WATSON_SERVICE_URL` | vazio | Ex.: `https://api.us-south.assistant.watson.cloud.ibm.com/instances/...` |
| `WATSON_ASSISTANT_ID` | vazio | ID do **assistant** (não do skill) |
| `WATSON_ENVIRONMENT_ID` | vazio | ID do ambiente **Draft** ou **Live** do assistant, exigido pela API v2 nas rotas de sessão e mensagem. É diferente do `WATSON_ASSISTANT_ID`. Para descobrir, rode `scripts/descobrir_environment_id.py` (ver abaixo) |
| `WATSON_VERSION` | `2021-06-14` | Versão da API v2 |
| `WATSON_USER_ID` | `cardioia-anonimo` | Enviado em toda mensagem (a API exige `user_id`). Um valor fixo conta como um único usuário ativo no plano da IBM |

Os segredos ficam apenas no `.env`, que está no `.gitignore`, ou no painel do Render. Se faltar qualquer uma das 4 variáveis do Watson (incluindo `WATSON_ENVIRONMENT_ID`), `/api/chat` responde 503 e o resto da API continua funcionando.

### Descobrir o `WATSON_ENVIRONMENT_ID`

Com `WATSON_API_KEY`, `WATSON_SERVICE_URL` e `WATSON_ASSISTANT_ID` preenchidos no `.env`:

```bash
cd Backend
python scripts/descobrir_environment_id.py
```

O script lista nome, tipo (`draft`/`live`) e ID de cada ambiente, e nunca imprime a chave. Copie o ID do ambiente onde o skill está publicado; o Dialog skill da F5 foi validado no **Draft**. Em caso de erro, ele mostra só o código e o diagnóstico: 401/403 = chave ou permissão; 404 = Assistant ID ou Service URL.

### Sessões do chat

O `session_id` devolvido por `/api/chat` deve ser reenviado nas mensagens seguintes. Se ele não estiver no formato UUID, o backend o ignora e cria uma sessão nova. Se a sessão tiver expirado (404 da IBM), ela é recriada automaticamente. Nos dois casos, o novo `session_id` vem na resposta.

## Regras de negócio

1. **Do sensor para as features:** `bpm → fc_media`, `temperatura → temperatura`, `spo2 → spo2_media`. As outras features vêm do campo `contexto`. O que faltar é preenchido com `CONTEXTO_PADRAO` (faixa normal, abaixo de todos os limiares) e listado em `features_padrao`, para deixar claro o que foi realmente medido.
2. **Faixas:** baixo < 0,30 ≤ moderado < 0,50 ≤ alto. O corte de 0,5 é o threshold com que o modelo foi avaliado na F6. Os limiares são configuráveis em `config.py`.
3. **Protocolos:** a tabela da F6 foi implementada literalmente em `services/protocolos.py`, com comparações estritas (`<` e `>`).
4. **Aviso:** toda resposta clínica inclui `aviso`.
5. **Armazenamento:** em memória, últimas 200 leituras. **Tudo se perde quando o serviço reinicia.** Não há banco de dados, por decisão de escopo do MVP.

### Observação sobre o limiar de SpO2

O protocolo de suporte respiratório usa **`spo2_media < 88`**, exatamente como definido na F6. O exemplo do enunciado da F6 (`spo2_media = 89`) aparece junto de recomendações que sugerem hipoxemia, o que é inconsistente com esse limiar. O limiar **não** foi alterado: para o caso do enunciado, o backend **não** aciona `suporte_respiratorio`. Se a equipe decidir mudar, edite apenas a tabela em `services/protocolos.py` e o teste correspondente.

### Observação sobre o valor 0,91 do enunciado

Para o "novo caso" da F6, o modelo retorna **1,00**, e não o 0,91 ilustrativo do enunciado. O motivo está explicado no README do modelo da F6: o caso aciona todos os limiares que geram o rótulo.

## Extensão: orquestrador multiagente da F6

`services/risco.py::enriquecer_com_agentes()` é o ponto preparado para ligar os agentes da F6. Hoje a função devolve o resultado sem alterações. O código dos agentes não está neste repositório e nenhuma dependência de LLM foi adicionada. As instruções estão na docstring da função.

## Deploy

Publicado no Render: **https://cardioia-backend-djsj.onrender.com** (`/health`, `/docs`).

### Serviço no Render

| Configuração | Valor |
|---|---|
| Tipo | Web Service (Python), plano free |
| Root Directory | `Backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/health` |
| Auto-Deploy | **On Commit**: cada push na `main` dispara um novo deploy |

O `render.yaml` desta pasta tem os mesmos valores. Como ele não está na raiz do repositório, o Blueprint do Render pode não detectá-lo; nesse caso, crie o serviço como **New → Web Service** com a tabela acima.

### Variáveis de ambiente (painel do Render → Environment)

| Variável | O que colocar |
|---|---|
| `PYTHON_VERSION` | `3.11.11` (o `.joblib` exige `scikit-learn==1.6.1`) |
| `AMBIENTE` | `producao` |
| `CORS_ORIGINS` | domínios extras do front, separados por vírgula (`*.vercel.app` já é aceito) |
| `DEVICE_KEY` | opcional; se preenchida, o ESP32 precisa enviar o mesmo valor em `X-Device-Key` |
| `WATSON_API_KEY` | API key da instância do Watson Assistant |
| `WATSON_SERVICE_URL` | URL da instância (`https://api.<região>.assistant.watson.cloud.ibm.com/instances/<id>`) |
| `WATSON_ASSISTANT_ID` | ID do assistant |
| `WATSON_ENVIRONMENT_ID` | ID do ambiente **Draft** (descubra com `scripts/descobrir_environment_id.py`) |
| `WATSON_VERSION` | `2021-06-14` |
| `WATSON_USER_ID` | opcional; padrão `cardioia-anonimo` |

Os valores ficam só no painel do Render, nunca no repositório. Espaços, quebras de linha e aspas coladas por engano são removidos na leitura. Se faltar qualquer uma das 4 variáveis obrigatórias do Watson, `/api/chat` responde 503 e o resto da API continua funcionando.

### Plano free

O serviço **hiberna após ~15 min** sem tráfego. A primeira requisição seguinte demora até ~50 s, e o histórico em memória é zerado. **Abra `/health` antes da demonstração.**

## Segurança

- `X-Device-Key` é uma proteção **mínima** contra envio acidental de leituras. Como o projeto Wokwi é público, a chave usada no firmware é de demonstração e não é um segredo.
- `modelo/modelo_pico_risco.joblib` usa pickle. Carregue apenas o artefato gerado pela F6.
- Os erros 500 e 503 não expõem stack trace.
