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
| `WATSON_VERSION` | `2021-06-14` | Versão da API v2 |

Os segredos ficam apenas no `.env`, que está no `.gitignore`, ou no painel do Render. Sem credenciais do Watson, `/api/chat` responde 503 e o resto da API continua funcionando.

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

## Deploy no Render (não realizado)

1. No Render, use **New → Blueprint** e aponte para este repositório. Se o `render.yaml` não for detectado por não estar na raiz, use **New → Web Service** com:
   - Root Directory: `Backend`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Env: `PYTHON_VERSION=3.11.11`, `AMBIENTE=producao`
2. Preencha no painel as variáveis marcadas como `sync: false`: `DEVICE_KEY`, `CORS_ORIGINS` e as do Watson.
3. Confira `https://<servico>.onrender.com/health`.

No plano free, o serviço hiberna depois de cerca de 15 min sem tráfego. A primeira requisição seguinte demora até ~50 s, e o histórico em memória é zerado.

## Segurança

- `X-Device-Key` é uma proteção **mínima** contra envio acidental de leituras. Como o projeto Wokwi é público, a chave usada no firmware é de demonstração e não é um segredo.
- `modelo/modelo_pico_risco.joblib` usa pickle. Carregue apenas o artefato gerado pela F6.
- Os erros 500 e 503 não expõem stack trace.
