"""CardioIA Fase 7 — Backend integrador.

Sensor (MicroPython/ESP32) -> este backend -> modelo preditivo F6 + Watson F5 -> UI Web/Mobile.

Rodar local:  uvicorn app.main:app --reload   (a partir da pasta Backend/)
"""
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.schemas import (
    EntradaChat, EntradaRisco, Erro, LeituraSensor, LoteLeituras, RespostaChat,
    RespostaLeitura, ResultadoRisco, Saude,
)
from app.services import risco as servico_risco
from app.services.leituras import RepositorioLeituras
from app.services.watson import ServicoWatson, WatsonIndisponivel

log = logging.getLogger("cardioia")

REGEX_VERCEL = r"https://([a-z0-9-]+\.)*vercel\.app"
REGEX_LOCALHOST = r"http://(localhost|127\.0\.0\.1)(:\d+)?"


def _json_valido(valor) -> bool:
    try:
        json.dumps(valor, allow_nan=False)
        return True
    except (TypeError, ValueError):
        return False


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or get_settings()
    estado = {"modelo_carregado": False}
    repositorio = RepositorioLeituras(settings.max_leituras)
    watson = ServicoWatson(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        estado["modelo_carregado"] = servico_risco.carregar()
        if not estado["modelo_carregado"]:
            log.error("Modelo preditivo não carregou — rotas de risco responderão 503.")
        yield

    app = FastAPI(
        title="CardioIA Fase 7 — Backend",
        description="Integra sensores IoT, o modelo preditivo da F6 e o Watson Assistant da F5.",
        version="1.0.0",
        lifespan=lifespan,
    )

    regex_cors = REGEX_VERCEL + (f"|{REGEX_LOCALHOST}" if settings.em_desenvolvimento else "")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.lista_cors,
        allow_origin_regex=f"^({regex_cors})$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Device-Key"],
    )

    @app.exception_handler(RequestValidationError)
    async def _erro_validacao(_req: Request, exc: RequestValidationError):
        # NaN/Infinity (aceitos pelo parser JSON do Python) são recusados pela validação, mas o
        # valor recebido em "input" não é JSON válido e derrubaria a resposta 422 com um 500.
        erros = []
        for erro in jsonable_encoder(exc.errors()):
            if "input" in erro and not _json_valido(erro["input"]):
                erro = {k: v for k, v in erro.items() if k != "input"}
            erros.append(erro)
        return JSONResponse(status_code=422, content={"detail": erros})

    @app.exception_handler(servico_risco.ModeloIndisponivel)
    async def _modelo_indisponivel(_req: Request, exc: Exception):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(WatsonIndisponivel)
    async def _watson_indisponivel(_req: Request, exc: Exception):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def _erro_interno(_req: Request, exc: Exception):
        log.exception("Erro não tratado")
        return JSONResponse(status_code=500, content={"detail": "Erro interno no servidor."})

    def exigir_chave_dispositivo(x_device_key: Optional[str] = Header(None)) -> None:
        if not settings.device_key:
            return
        if not x_device_key:
            raise HTTPException(401, "Header X-Device-Key ausente.")
        if not secrets.compare_digest(x_device_key, settings.device_key):
            raise HTTPException(403, "X-Device-Key inválida.")

    def processar_leitura(leitura: LeituraSensor) -> RespostaLeitura:
        contexto = leitura.contexto.model_dump() if leitura.contexto else None
        features, padrao = servico_risco.montar_features(
            {"bpm": leitura.bpm, "temperatura": leitura.temperatura, "spo2": leitura.spo2},
            contexto,
        )
        resultado = servico_risco.avaliar(features, padrao, settings)
        return repositorio.adicionar({
            **resultado.model_dump(),
            **leitura.model_dump(exclude={"contexto"}),
            "recebido_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })

    erros_sensor = {401: {"model": Erro}, 403: {"model": Erro}, 503: {"model": Erro}}

    @app.get("/health", response_model=Saude, tags=["sistema"])
    def health():
        return Saude(
            status="ok",
            modelo_carregado=estado["modelo_carregado"],
            watson_configurado=watson.configurado,
        )

    @app.post("/api/sensores", response_model=RespostaLeitura, tags=["sensores"],
              dependencies=[Depends(exigir_chave_dispositivo)], responses=erros_sensor)
    def receber_leitura(leitura: LeituraSensor):
        """Recebe uma leitura do ESP32, avalia o risco e guarda no histórico."""
        return processar_leitura(leitura)

    @app.post("/api/sensores/lote", response_model=list[RespostaLeitura], tags=["sensores"],
              dependencies=[Depends(exigir_chave_dispositivo)], responses=erros_sensor)
    def receber_lote(lote: LoteLeituras):
        """Sincroniza a fila offline do ESP32. Resultados na mesma ordem do envio."""
        return [processar_leitura(leitura) for leitura in lote.leituras]

    @app.post("/api/risco", response_model=ResultadoRisco, tags=["risco"],
              responses={503: {"model": Erro}})
    def calcular_risco(entrada: EntradaRisco):
        """Avalia features parciais ou completas, sem armazenar."""
        dados = entrada.model_dump()
        features, padrao = servico_risco.montar_features(dados, usar_sinais_padrao=True)
        return servico_risco.avaliar(features, padrao, settings)

    @app.get("/api/leituras/ultima", response_model=RespostaLeitura, tags=["leituras"],
             responses={404: {"model": Erro}})
    def ultima_leitura():
        registro = repositorio.ultima()
        if registro is None:
            raise HTTPException(404, "Nenhuma leitura recebida desde que o serviço iniciou.")
        return registro

    @app.get("/api/leituras", response_model=list[RespostaLeitura], tags=["leituras"])
    def listar_leituras(limite: int = Query(50, ge=1, le=200)):
        """Histórico em memória, mais recentes primeiro."""
        return repositorio.listar(limite)

    @app.post("/api/chat", response_model=RespostaChat, tags=["chat"],
              responses={503: {"model": Erro}})
    def chat(entrada: EntradaChat):
        """Conversa com o Watson Assistant (F5). Sem session_id, uma nova sessão é criada."""
        resposta, session_id = watson.conversar(entrada.mensagem, entrada.session_id)
        return RespostaChat(resposta=resposta, session_id=session_id)

    return app


app = create_app()
