"""Clase `FakeHttpClient`: guarda las requests y devuelve códigos configurables."""

from collections.abc import Sequence

from ringr_agents.infrastructure.http.client import HttpRequest, HttpResponse, TransportError


class FakeHttpClient:
    """Integración simulada: no hace red; guarda cada request y responde según una secuencia."""

    def __init__(self, results: Sequence[int | TransportError] = ()) -> None:
        # Copia propia: si quien llama modifica su lista después, la secuencia no cambia.
        self._results = list(results)
        self._next = 0
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        """Guarda la request; devuelve el siguiente código o lanza el siguiente error.

        Cuando la secuencia se acaba, responde 200.
        """
        self.requests.append(request)
        if self._next >= len(self._results):
            return HttpResponse(status_code=200)
        item = self._results[self._next]
        self._next += 1
        if isinstance(item, TransportError):
            raise item
        return HttpResponse(status_code=item)
