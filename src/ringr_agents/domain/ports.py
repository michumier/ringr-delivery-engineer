"""Interfaces del dominio: `ActionSender` (Protocol)."""

from collections.abc import Mapping
from typing import Protocol

from ringr_agents.domain.results import SendResult


class ActionSender(Protocol):
    """Lo único que el agente sabe de «enviar» (DIP)."""

    def send(self, url: str, data: Mapping[str, object | None]) -> SendResult:
        """Envía los datos a la URL y devuelve el resultado; no lanza por fallos de HTTP."""
        ...
