"""Reintentos con el patrón Decorator: `RetryPolicy` y `RetryingHttpClient` (AMB-4, PC-7)."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from ringr_agents.infrastructure.http.client import (
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    """Cuántas veces se intenta y cuánto se espera (AMB-4). `sleep` se inyecta en los tests."""

    max_attempts: int = 3
    base_delay: float = 0.2
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts debe ser al menos 1, no {self.max_attempts}")
        if self.base_delay < 0:
            raise ValueError(f"base_delay no puede ser negativo, no {self.base_delay}")

    def delay_before(self, attempt: int) -> float:
        """Espera antes del intento `attempt` (2, 3...): se dobla cada vez (0.2, 0.4...)."""
        return self.base_delay * 2 ** (attempt - 2)


def _is_retryable(status_code: int) -> bool:
    # Solo los 5xx: un 4xx es un error de la petición y fallaría igual (AMB-4).
    return 500 <= status_code < 600


class RetryingHttpClient:
    """Cumple `HttpClient` y envuelve a otro para añadirle reintentos, sin modificarlo (PC-7.1).

    Repite **la misma** `HttpRequest`, así que la `Idempotency-Key` no cambia entre intentos.
    Se reintentan los 5xx y los errores de transporte (PC-7.2). El número de intentos viaja en
    la respuesta o en el error, para que llegue al resultado del turno.
    """

    def __init__(self, inner: HttpClient, policy: RetryPolicy | None = None) -> None:
        self._inner = inner
        self._policy = policy if policy is not None else RetryPolicy()

    def send(self, request: HttpRequest) -> HttpResponse:
        """Envía la request hasta `max_attempts` veces.

        Devuelve la primera respuesta que no se reintenta (2xx o 4xx), o la última si se agotan
        los intentos. Si el último intento fue un error de transporte, lo relanza.
        """
        attempts = self._policy.max_attempts
        for attempt in range(1, attempts + 1):
            if attempt > 1:
                self._policy.sleep(self._policy.delay_before(attempt))
            try:
                response = self._inner.send(request)
            except TransportError as error:
                if attempt == attempts:
                    raise TransportError(str(error), attempts=attempt) from error
                logger.warning("Intento %s/%s sin respuesta: %s", attempt, attempts, error)
                continue
            if not _is_retryable(response.status_code) or attempt == attempts:
                return replace(response, attempts=attempt)
            logger.warning("Intento %s/%s: código %s", attempt, attempts, response.status_code)
        raise AssertionError("inalcanzable: el último intento siempre devuelve o lanza")
