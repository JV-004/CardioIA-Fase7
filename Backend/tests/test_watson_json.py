"""Valida o Dialog skill versionado em docs/watson/ com scripts/validar_watson_json.py."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

DIR_BACKEND = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "validar_watson_json", DIR_BACKEND / "scripts" / "validar_watson_json.py")
validador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validador)

SKILL = json.loads(validador.CAMINHO_PADRAO.read_text(encoding="utf-8"))


def test_skill_versionado_e_valido():
    assert validador.validar(SKILL) == []
    assert validador.ordem_raiz(SKILL)[-3:] == ["#General_Greetings", "#General_Ending", "Em outros casos"]


def test_script_retorna_zero(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["validar_watson_json.py"])
    assert validador.main() == 0
    assert "VÁLIDO" in capsys.readouterr().out


def _no(skill, no_id):
    return next(n for n in skill["dialog_nodes"] if n["dialog_node"] == no_id)


def _quebrado(alterar):
    skill = copy.deepcopy(SKILL)
    alterar(skill)
    return validador.validar(skill)


@pytest.mark.parametrize("descricao,alterar,trecho", [
    ("previous_sibling inexistente",
     lambda s: _no(s, "node_despedida_cardioia").update(previous_sibling="nao_existe"), "inexistente"),
    ("dois nós raiz sem previous_sibling",
     lambda s: _no(s, "node_saudacao_cardioia").pop("previous_sibling"), "1 nó sem previous_sibling"),
    ("ciclo",
     lambda s: _no(s, "Bem-vindo").update(previous_sibling="Em outros casos"), "previous_sibling"),
    ("id duplicado",
     lambda s: _no(s, "node_despedida_cardioia").update(dialog_node="node_saudacao_cardioia"), "duplicados"),
    ("fallback fora do fim",
     lambda s: (_no(s, "Em outros casos").update(previous_sibling="node_saudacao_cardioia"),
                _no(s, "node_despedida_cardioia").update(previous_sibling="Em outros casos")),
     "último irmão"),
    ("aspas literais",
     lambda s: _no(s, "node_saudacao_cardioia")["output"]["generic"][0]["values"][0].update(text='"Olá"'),
     "aspas"),
    ("texto só com aspas",
     lambda s: _no(s, "node_saudacao_cardioia")["output"]["generic"][0]["values"][0].update(text='""'),
     "aspas"),
    ("emoji",
     lambda s: _no(s, "node_despedida_cardioia")["output"]["generic"][0]["values"][0].update(text="Até logo! ❤️"),
     "emoji"),
    ("intent removida", lambda s: s["intents"].pop(), "intents alteradas"),
    ("nó a menos", lambda s: s["dialog_nodes"].pop(0), "esperados 10 nós"),
])
def test_validador_detecta_problemas(descricao, alterar, trecho):
    erros = _quebrado(alterar)
    assert any(trecho in e for e in erros), (descricao, erros)
