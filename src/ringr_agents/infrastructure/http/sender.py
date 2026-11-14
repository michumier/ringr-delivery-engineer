"""Clase `HttpActionSender`: construye la request (URL, cabeceras, body) y la envía."""

import json
import logging
import uuid
from collections.abc import Callable, Mapping
from urllib.parse import quote

from ringr_agents.domain.results import SendResult
from ringr_agents.infrastructure.http.client import HttpClient, HttpRequest, TransportError

logger = logging.getLogger(__name__)


class HttpActionSender:
    """Cumple `ActionSender`. Construye la request una vez y se la da a su `HttpClient`.

    No reintenta (eso lo hace `RetryingHttpClient`) y nunca lanza por culpa del HTTP.
    """

    def __init__(
        self,
        client: HttpClient,
        token: str,
        new_idempotency_key: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._client = client
        self._token = token
        self._new_idempotency_key = new_idempotency_key

    def send(self, url: str, data: Mapping[str, object | None]) -> SendResult:
        """Envía los datos y resume el resultado; un error de transporte no se propaga."""
        key = self._new_idempotency_key()
        request = self.build_request(url, data, key)
        logger.info("Enviando POST a %s (Idempotency-Key=%s)", url, key)
        try:
            response = self._client.send(request)
        except TransportError as error:
            logger.warning("Envío a %s sin respuesta (Idempotency-Key=%s): %s", url, key, error)
            return SendResult(
                ok=False, attempts=error.attempts, status_code=None, idempotency_key=key
            )
        ok = 200 <= response.status_code < 300
        logger.log(
            logging.INFO if ok else logging.WARNING,
            "Envío a %s terminado (Idempotency-Key=%s): código %s, intentos %s",
            url,
            key,
            response.status_code,
            response.attempts,
        )
        return SendResult(
            ok=ok,
            attempts=response.attempts,
            status_code=response.status_code,
            idempotency_key=key,
        )

    def build_request(self, url: str, data: Mapping[str, object | None], key: str) -> HttpRequest:
        """Construye la request: una cabecera por campo no nulo y el mismo JSON como cuerpo."""
        present = {name: value for name, value in data.items() if value is not None}
        headers = {name: quote(str(value), safe="") for name, value in present.items()}
        # Las cabeceras fijas van después, para que un campo no pueda pisarlas.
        headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Idempotency-Key": key,
            }
        )
        # ensure_ascii=False: el texto original va intacto en el cuerpo (AMB-7).
        body = json.dumps(present, ensure_ascii=False)
        return HttpRequest(method="POST", url=url, headers=headers, body=body)
