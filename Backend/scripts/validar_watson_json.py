"""Valida o Dialog skill do Watson (docs/watson/cardioia-dialog-skill.json).

Uso (a partir da pasta Backend/):
    python -I scripts/validar_watson_json.py [caminho.json]

Checa: JSON válido; cadeia de irmãos (previous_sibling) íntegra em cada nível; fallback
"anything_else" como último irmão da raiz; contagem de nós e intents esperadas; textos
sem aspas literais sobrando e sem emojis. Sai com código 1 se algo falhar.
"""
import json
import re
import sys
from pathlib import Path

CAMINHO_PADRAO = Path(__file__).resolve().parents[1] / "docs" / "watson" / "cardioia-dialog-skill.json"

NOS_ESPERADOS = 10
INTENTS_ESPERADAS = {
    "agendar_contato", "duvida_medicacao", "pedir_orientacao", "relatar_sintoma",
    "Bot_Control_Approve_Response", "Bot_Control_Change_Subject", "Bot_Control_Clarification",
    "Bot_Control_Confirm_Presence", "Bot_Control_Ignore_Undo", "Bot_Control_Reject_Response",
    "Bot_Control_Standby", "Bot_Control_Start_Over", "Bot_Control_Unsure",
    "General_About_You", "General_Agent_Capabilities", "General_Connect_to_Agent",
    "General_Ending", "General_Greetings", "General_Human_or_Bot", "General_Jokes",
    "General_Negative_Feedback", "General_Positive_Feedback", "General_Security_Assurance",
}
# Faixas Unicode de emojis e pictogramas mais comuns
EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF️]")


def textos(no):
    for g in no.get("output", {}).get("generic", []):
        for v in g.get("values", []):
            yield v.get("text", "")


def validar(skill: dict) -> list[str]:
    """Lista de problemas encontrados (vazia = válido)."""
    erros = []
    nos = skill.get("dialog_nodes", [])
    ids = [n["dialog_node"] for n in nos]
    por_id = {n["dialog_node"]: n for n in nos}

    if len(nos) != NOS_ESPERADOS:
        erros.append(f"esperados {NOS_ESPERADOS} nós, encontrados {len(nos)}")
    duplicados = sorted({i for i in ids if ids.count(i) > 1})
    if duplicados:
        erros.append(f"ids duplicados: {duplicados}")
    intents = {i["intent"] for i in skill.get("intents", [])}
    if intents != INTENTS_ESPERADAS:
        erros.append(f"intents alteradas: faltando {sorted(INTENTS_ESPERADAS - intents)}, "
                     f"sobrando {sorted(intents - INTENTS_ESPERADAS)}")

    # Agrupa por pai (None = raiz) e confere a cadeia de previous_sibling em cada nível
    niveis = {}
    for n in nos:
        niveis.setdefault(n.get("parent"), []).append(n)
    for pai, irmaos in niveis.items():
        nivel = "raiz" if pai is None else f"filhos de {pai}"
        nomes = {n["dialog_node"] for n in irmaos}
        primeiros = [n["dialog_node"] for n in irmaos if "previous_sibling" not in n]
        if len(primeiros) != 1:
            erros.append(f"{nivel}: esperado 1 nó sem previous_sibling, encontrados {primeiros}")
        for n in irmaos:
            ant = n.get("previous_sibling")
            if ant is not None and ant not in nomes:
                erros.append(f"{nivel}: {n['dialog_node']} aponta para irmão inexistente {ant!r}")
        seguinte = {}
        for n in irmaos:
            ant = n.get("previous_sibling")
            if ant in seguinte:
                erros.append(f"{nivel}: dois nós depois de {ant!r} ({seguinte[ant]} e {n['dialog_node']})")
            seguinte[ant] = n["dialog_node"]
        # Percorre a cadeia a partir do primeiro: tem que visitar todos, sem ciclo
        ordem, atual, vistos = [], seguinte.get(None), set()
        while atual is not None and atual not in vistos:
            vistos.add(atual)
            ordem.append(atual)
            atual = seguinte.get(atual)
        if atual is not None:
            erros.append(f"{nivel}: ciclo na cadeia em {atual!r}")
        if set(ordem) != nomes:
            erros.append(f"{nivel}: nós fora da cadeia: {sorted(nomes - set(ordem))}")
        if pai is None and ordem:
            ultimo = por_id[ordem[-1]]
            if ultimo.get("conditions") != "anything_else":
                erros.append(f"raiz: o último irmão deveria ser o fallback anything_else, é {ordem[-1]!r}")

    for n in nos:
        for t in textos(n):
            if not t.strip():
                erros.append(f"{n['dialog_node']}: texto vazio")
            elif t.strip() in ('""', "''") or (len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'"):
                erros.append(f"{n['dialog_node']}: texto com aspas literais: {t[:40]!r}")
            if EMOJI.search(t):
                erros.append(f"{n['dialog_node']}: texto com emoji")
    return erros


def ordem_raiz(skill: dict) -> list[str]:
    raiz = [n for n in skill["dialog_nodes"] if n.get("parent") is None]
    seguinte = {n.get("previous_sibling"): n for n in raiz}
    ordem, atual = [], seguinte.get(None)
    while atual is not None and len(ordem) <= len(raiz):
        ordem.append(atual.get("title") or atual["dialog_node"])
        atual = seguinte.get(atual["dialog_node"])
    return ordem


def main() -> int:
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else CAMINHO_PADRAO
    try:
        skill = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FALHOU: não foi possível ler o JSON ({type(exc).__name__}: {exc})")
        return 1
    print(f"json.load OK: {caminho.name}")
    print(f"nós: {len(skill.get('dialog_nodes', []))} | intents: {len(skill.get('intents', []))}"
          f" | entities: {len(skill.get('entities', []))}")
    print("ordem da raiz:", " -> ".join(ordem_raiz(skill)))
    erros = validar(skill)
    for e in erros:
        print("ERRO:", e)
    print("VÁLIDO" if not erros else f"FALHOU ({len(erros)} problema(s))")
    return 0 if not erros else 1


if __name__ == "__main__":
    sys.exit(main())
