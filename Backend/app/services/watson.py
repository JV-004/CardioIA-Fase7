"""Integração com o IBM Watson Assistant v2 (assistente conversacional da F5)."""
import logging
import threading
import uuid
from typing import Optional

from app.config import Settings

log = logging.getLogger(__name__)

RESPOSTA_VAZIA = "Desculpe, não consegui entender. Pode reformular a pergunta?"
TIMEOUT_S = 15  # sem isso, uma IBM lenta prenderia a requisição do usuário indefinidamente


class WatsonIndisponivel(RuntimeError):
    """Mensagem pensada para o usuário final (vai no corpo do HTTP 503)."""


def _eh_uuid(valor: str) -> bool:
    try:
        uuid.UUID(valor)
        return True
    except ValueError:
        return False


class ServicoWatson:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._cliente = None
        self._lock = threading.Lock()

    def _sem_chave(self, texto: str) -> str:
        """Defesa extra: mascara a API key caso ela apareça na mensagem de alguma exceção."""
        chave = self._settings.watson_api_key
        return texto.replace(chave, "***") if chave else texto

    @property
    def configurado(self) -> bool:
        return self._settings.watson_configurado

    def _obter_cliente(self):
        if not self.configurado:
            raise WatsonIndisponivel(
                "Assistente conversacional não configurado no servidor "
                "(defina WATSON_API_KEY, WATSON_SERVICE_URL, WATSON_ASSISTANT_ID "
                "e WATSON_ENVIRONMENT_ID)."
            )
        with self._lock:
            if self._cliente is None:
                from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
                from ibm_watson import AssistantV2

                cliente = AssistantV2(
                    version=self._settings.watson_version,
                    authenticator=IAMAuthenticator(self._settings.watson_api_key),
                )
                cliente.set_service_url(self._settings.watson_service_url)
                cliente.set_http_config({"timeout": TIMEOUT_S})
                self._cliente = cliente
            return self._cliente

    # A API v2 atual exige environment_id (ID do ambiente draft ou live) nas rotas de sessão e
    # mensagem, e user_id em toda mensagem.
    def _criar_sessao(self, cliente) -> str:
        r = cliente.create_session(
            assistant_id=self._settings.watson_assistant_id,
            environment_id=self._settings.watson_environment_id,
        ).get_result()
        return r["session_id"]

    def _enviar(self, cliente, session_id: str, mensagem: str) -> str:
        r = cliente.message(
            assistant_id=self._settings.watson_assistant_id,
            environment_id=self._settings.watson_environment_id,
            session_id=session_id,
            input={"message_type": "text", "text": mensagem},
            user_id=self._settings.watson_user_id,
        ).get_result()
        textos = [
            g.get("text", "")
            for g in r.get("output", {}).get("generic", [])
            if g.get("response_type") == "text" and g.get("text")
        ]
        return "\n".join(textos) or RESPOSTA_VAZIA

    def conversar(self, mensagem: str, session_id: Optional[str] = None) -> tuple[str, str]:
        """Envia a mensagem e devolve (resposta, session_id). Cria/recria a sessão se preciso."""
        from ibm_cloud_sdk_core import ApiException

        cliente = self._obter_cliente()
        if session_id and not _eh_uuid(session_id):
            session_id = None  # formato inválido: trata como ausente (a IBM responderia 400)
        try:
            if not session_id:
                session_id = self._criar_sessao(cliente)
            try:
                return self._enviar(cliente, session_id, mensagem), session_id
            except ApiException as exc:
                if exc.status_code != 404:  # 404 = sessão inválida/expirada (expira após inatividade)
                    raise
                session_id = self._criar_sessao(cliente)
                return self._enviar(cliente, session_id, mensagem), session_id
        except ApiException as exc:
            log.warning("Watson respondeu erro %s: %s", exc.status_code, exc.message)
            raise WatsonIndisponivel(
                f"Assistente conversacional indisponível (Watson retornou erro {exc.status_code})."
            ) from exc
        except Exception as exc:  # rede, DNS, timeout, autenticação IAM
            log.warning("Falha ao falar com o Watson: %s: %s",
                        type(exc).__name__, self._sem_chave(str(exc))[:200])
            raise WatsonIndisponivel(
                "Assistente conversacional indisponível no momento (falha de comunicação com o Watson)."
            ) from exc
