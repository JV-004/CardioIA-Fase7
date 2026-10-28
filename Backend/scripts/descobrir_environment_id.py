"""Lista os ambientes (draft/live) do Watson Assistant para descobrir o WATSON_ENVIRONMENT_ID.

Uso (a partir da pasta Backend/, com o .env preenchido):
    python scripts/descobrir_environment_id.py

Lê WATSON_API_KEY, WATSON_SERVICE_URL e WATSON_ASSISTANT_ID via app.config.
Nunca imprime a API key.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ibm_cloud_sdk_core import ApiException  # noqa: E402
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator  # noqa: E402
from ibm_watson import AssistantV2  # noqa: E402

from app.config import get_settings  # noqa: E402

DIAGNOSTICO = {
    400: "requisição inválida (confira WATSON_VERSION e WATSON_ASSISTANT_ID)",
    401: "chave inválida ou sem permissão (confira WATSON_API_KEY e o plano da instância)",
    403: "chave inválida ou sem permissão (confira WATSON_API_KEY e o plano da instância)",
    404: "assistant não encontrado (confira WATSON_ASSISTANT_ID e WATSON_SERVICE_URL)",
}


def main() -> int:
    s = get_settings()
    faltando = [nome for nome, valor in [
        ("WATSON_API_KEY", s.watson_api_key),
        ("WATSON_SERVICE_URL", s.watson_service_url),
        ("WATSON_ASSISTANT_ID", s.watson_assistant_id),
    ] if not valor]
    if faltando:
        print("Variáveis vazias no .env:", ", ".join(faltando))
        return 2

    cliente = AssistantV2(version=s.watson_version, authenticator=IAMAuthenticator(s.watson_api_key))
    cliente.set_service_url(s.watson_service_url)
    try:
        ambientes = cliente.list_environments(s.watson_assistant_id).get_result()
    except ApiException as exc:
        print(f"Erro {exc.status_code}: {DIAGNOSTICO.get(exc.status_code, exc.message)}")
        return 1
    except Exception as exc:  # rede, DNS, URL malformada, falha no IAM
        print(f"Falha de comunicação: {type(exc).__name__}")
        return 1

    lista = ambientes.get("environments", [])
    if not lista:
        print("Nenhum ambiente retornado para este assistant.")
        return 1
    print(f"{'NOME':<20} {'AMBIENTE':<12} ENVIRONMENT_ID")
    for amb in lista:
        print(f"{amb.get('name', '-'):<20} {amb.get('environment', '-'):<12} {amb.get('environment_id', '-')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
