"""Contrato HTTP: `HttpRequest`, `HttpResponse`, `TransportError` y `HttpClient` (Protocol)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HttpRequest:
    """Petición ya construida, lista para enviar."""

    method: str
    url: str
    headers: Mapping[str, str]
    body: str


@dataclass(frozen=True)
class HttpResponse:
    """Respuesta del servidor; `attempts` viaja con ella para llegar al resultado del turno."""

    status_code: int
    attempts: int = 1


class TransportError(Exception):
    """Timeout o corte de conexión: no hubo respuesta HTTP."""

    def __init__(self, message: str = "error de transporte", attempts: int = 1) -> None:
        super().__init__(message)
        self.attempts = attempts


class HttpClient(Protocol):
    """Quien sabe enviar una `HttpRequest`; lo cumplen el cliente simulado y el de reintentos."""

    def send(self, request: HttpRequest) -> HttpResponse:
        """Envía la request. Lanza `TransportError` si no hay respuesta."""
        ...
