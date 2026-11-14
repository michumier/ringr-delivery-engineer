"""Clase `ParserModel` (`parse_data`), simulada con un guion."""

import copy
from collections.abc import Sequence
from typing import Any

from ringr_agents.infrastructure.models.errors import ScriptExhaustedError


class ParserModel:
    """Modelo parser simulado: un elemento del guion por turno (AMB-6)."""

    def __init__(self, script: Sequence[dict[str, Any] | Exception]) -> None:
        self._script = list(script)
        self._next = 0

    def parse_data(self) -> dict[str, Any]:
        """Devuelve una copia del siguiente dict; si el elemento es una excepción, la lanza.

        Lanza `ScriptExhaustedError` cuando ya no quedan elementos.
        """
        if self._next >= len(self._script):
            raise ScriptExhaustedError("el guion de ParserModel se ha agotado")
        item = self._script[self._next]
        self._next += 1  # se consume también si es una excepción: es un turno más
        if isinstance(item, Exception):
            raise item
        # Copia para que quien la reciba no pueda alterar el guion.
        return copy.deepcopy(item)
