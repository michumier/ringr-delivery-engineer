"""Clase `ConversationModel` (`answer_user`), simulada con un guion."""

from collections.abc import Sequence

from ringr_agents.infrastructure.models.errors import ScriptExhaustedError


class ConversationModel:
    """Modelo de conversación simulado: un elemento del guion por turno (AMB-6)."""

    def __init__(self, script: Sequence[str | Exception]) -> None:
        # Copia propia: si quien llama modifica su lista después, el guion no cambia.
        self._script = list(script)
        self._next = 0

    def answer_user(self) -> str:
        """Devuelve la siguiente respuesta; si el elemento es una excepción, la lanza.

        Lanza `ScriptExhaustedError` cuando ya no quedan elementos.
        """
        if self._next >= len(self._script):
            raise ScriptExhaustedError("el guion de ConversationModel se ha agotado")
        item = self._script[self._next]
        self._next += 1  # se consume también si es una excepción: es un turno más
        if isinstance(item, Exception):
            raise item
        return item
