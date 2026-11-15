"""HTTP simulado: cliente, envío de la acción y reintentos."""

from ringr_agents.infrastructure.http.client import (
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)
from ringr_agents.infrastructure.http.fake_client import FakeHttpClient
from ringr_agents.infrastructure.http.retry import RetryingHttpClient, RetryPolicy
from ringr_agents.infrastructure.http.sender import HttpActionSender

__all__ = [
    "FakeHttpClient",
    "HttpActionSender",
    "HttpClient",
    "HttpRequest",
    "HttpResponse",
    "RetryPolicy",
    "RetryingHttpClient",
    "TransportError",
]
