"""Armazenamento das leituras em memória.

Sem banco de dados: guarda só as últimas N leituras (padrão 200) e tudo é perdido
quando o serviço reinicia (no Render free, isso acontece a cada hibernação).
"""
import threading
from collections import deque
from typing import Optional

from app.schemas import RespostaLeitura


class RepositorioLeituras:
    def __init__(self, max_leituras: int = 200):
        self._itens: deque[RespostaLeitura] = deque(maxlen=max_leituras)
        self._lock = threading.Lock()
        self._proximo_id = 1

    def adicionar(self, dados: dict) -> RespostaLeitura:
        """Atribui um id sequencial, guarda e devolve a leitura."""
        with self._lock:
            registro = RespostaLeitura(id=self._proximo_id, **dados)
            self._proximo_id += 1
            self._itens.append(registro)
            return registro

    def ultima(self) -> Optional[RespostaLeitura]:
        with self._lock:
            return self._itens[-1] if self._itens else None

    def listar(self, limite: int = 50) -> list[RespostaLeitura]:
        """Mais recentes primeiro."""
        with self._lock:
            return list(reversed(self._itens))[:limite]
