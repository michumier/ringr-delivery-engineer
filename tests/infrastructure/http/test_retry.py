"""Reintentos: `RetryPolicy` y `RetryingHttpClient` (AMB-4, PC-6, PC-7.1, PC-7.2, PC-10, CA-11)."""

import logging

import pytest

from ringr_agents.infrastructure.http import (
    FakeHttpClient,
    HttpRequest,
    RetryingHttpClient,
    RetryPolicy,
    TransportError,
)

TOKEN = "ringr_test_token_9f3a2c1d"
RETRY_LOGGER = "ringr_agents.infrastructure.http.retry"


def make_request():
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "clave-fija"}
    return HttpRequest(
        method="POST", url="https://api.ringr.debt/v1/commitment", headers=headers, body="{}"
    )


def make_client(results=(), **policy_options):
    """Crea (cliente con reintentos, cliente simulado, lista de esperas) sin esperar de verdad."""
    waits: list[float] = []
    fake = FakeHttpClient(results)
    policy = RetryPolicy(sleep=waits.append, **policy_options)
    return RetryingHttpClient(fake, policy), fake, waits


class TestSuccessAndRetriedStatuses:
    def test_first_attempt_ok_returns_one_attempt_without_waiting(self):
        """AMB-4: un 200 al primer intento da attempts=1 y no espera."""
        client, fake, waits = make_client([200])

        response = client.send(make_request())

        assert response.status_code == 200
        assert response.attempts == 1
        assert len(fake.requests) == 1
        assert waits == []

    def test_503_then_200_returns_ok_with_two_attempts(self):
        """AMB-4, CA-11: un 503 y luego un 200 devuelve 200 con attempts=2."""
        client, fake, _ = make_client([503, 200])

        response = client.send(make_request())

        assert response.status_code == 200
        assert response.attempts == 2
        assert len(fake.requests) == 2

    def test_retry_resends_the_same_request(self):
        """PC-7.1, PC-6: se reenvía la misma request, con la misma Idempotency-Key."""
        client, fake, _ = make_client([503, 200])
        request = make_request()

        client.send(request)

        assert fake.requests[0] is request
        assert fake.requests[1] is request
        assert fake.requests[0].headers["Idempotency-Key"] == "clave-fija"
        assert fake.requests[1].headers["Idempotency-Key"] == "clave-fija"

    def test_three_503_returns_the_last_503_with_three_attempts(self):
        """AMB-4, CA-11: tres 503 agotan los intentos y se devuelve el 503 con attempts=3."""
        client, fake, _ = make_client([503, 503, 503])

        response = client.send(make_request())

        assert response.status_code == 503
        assert response.attempts == 3
        assert len(fake.requests) == 3

    @pytest.mark.parametrize("status", [500, 502, 503, 599])
    def test_5xx_statuses_are_retried(self, status):
        """PC-7.2, AMB-4: cualquier 5xx se reintenta."""
        client, fake, _ = make_client([status, 200])

        response = client.send(make_request())

        assert response.status_code == 200
        assert response.attempts == 2
        assert len(fake.requests) == 2

    @pytest.mark.parametrize("status", [400, 404, 422])
    def test_4xx_statuses_are_returned_at_the_first_attempt(self, status):
        """PC-7.2, AMB-4: un 4xx no se reintenta: attempts=1 y sin esperas."""
        client, fake, waits = make_client([status, 200])

        response = client.send(make_request())

        assert response.status_code == status
        assert response.attempts == 1
        assert len(fake.requests) == 1
        assert waits == []


class TestTransportErrors:
    def test_transport_error_then_200_retries(self):
        """PC-7.2, AMB-4: un error de transporte se reintenta; luego 200 con attempts=2."""
        client, fake, _ = make_client([TransportError("timeout"), 200])

        response = client.send(make_request())

        assert response.status_code == 200
        assert response.attempts == 2
        assert len(fake.requests) == 2

    def test_three_transport_errors_raise_with_three_attempts(self):
        """PC-7.2, CA-11: tres errores de transporte relanzan TransportError con attempts=3."""
        errors = [TransportError("t1"), TransportError("t2"), TransportError("t3")]
        client, fake, _ = make_client(errors)

        with pytest.raises(TransportError) as raised:
            client.send(make_request())

        assert raised.value.attempts == 3
        assert len(fake.requests) == 3

    def test_mixed_503_transport_error_then_200(self):
        """PC-7.2: 503, luego error de transporte y luego 200 da attempts=3."""
        client, fake, _ = make_client([503, TransportError("corte"), 200])

        response = client.send(make_request())

        assert response.status_code == 200
        assert response.attempts == 3
        assert len(fake.requests) == 3

    def test_last_attempt_transport_error_after_503_raises(self):
        """PC-7.2: si el último intento es un error de transporte tras 503s, se relanza."""
        client, _, _ = make_client([503, 503, TransportError("corte")])

        with pytest.raises(TransportError) as raised:
            client.send(make_request())

        assert raised.value.attempts == 3


class TestWaits:
    def test_waits_double_between_attempts(self):
        """AMB-4: con 3 intentos fallidos se espera 0.2 y luego 0.4 segundos."""
        client, _, waits = make_client([503, 503, 503])

        client.send(make_request())

        assert waits == [0.2, 0.4]

    def test_base_delay_is_configurable(self):
        """AMB-4: la espera base se configura y se dobla igualmente."""
        client, _, waits = make_client([503, 503, 503], base_delay=1.0)

        client.send(make_request())

        assert waits == [1.0, 2.0]

    def test_no_wait_before_the_first_attempt(self):
        """AMB-4: no hay espera antes del primer intento (una sola espera con 2 intentos)."""
        client, _, waits = make_client([503, 200])

        client.send(make_request())

        assert waits == [0.2]

    def test_transport_errors_also_wait_between_attempts(self):
        """AMB-4: los errores de transporte siguen el mismo ritmo de espera."""
        client, _, waits = make_client([TransportError("a"), TransportError("b"), 200])

        client.send(make_request())

        assert waits == [0.2, 0.4]


class TestPolicy:
    def test_max_attempts_one_means_no_retries(self):
        """AMB-4: con max_attempts=1 un 503 se devuelve sin reintentar ni esperar."""
        client, fake, waits = make_client([503, 200], max_attempts=1)

        response = client.send(make_request())

        assert response.status_code == 503
        assert response.attempts == 1
        assert len(fake.requests) == 1
        assert waits == []

    def test_max_attempts_one_relays_a_transport_error(self):
        """AMB-4: con max_attempts=1 el error de transporte sale con attempts=1."""
        client, _, _ = make_client([TransportError("corte")], max_attempts=1)

        with pytest.raises(TransportError) as raised:
            client.send(make_request())

        assert raised.value.attempts == 1

    def test_max_attempts_five_tries_five_times(self):
        """AMB-4: max_attempts=5 hace 5 intentos y 4 esperas (0.2, 0.4, 0.8, 1.6)."""
        client, fake, waits = make_client([503] * 5, max_attempts=5)

        response = client.send(make_request())

        assert response.attempts == 5
        assert len(fake.requests) == 5
        assert waits == pytest.approx([0.2, 0.4, 0.8, 1.6])

    def test_default_policy_values(self):
        """AMB-4: por defecto 3 intentos y 0.2 s de espera base."""
        policy = RetryPolicy()

        assert policy.max_attempts == 3
        assert policy.base_delay == 0.2

    def test_client_without_policy_works(self):
        """AMB-4: sin policy funciona con la de por defecto (sus valores, en el test anterior).

        Solo con un 200, para no esperar de verdad: `time.sleep` es el valor por defecto.
        """
        fake = FakeHttpClient([200])
        client = RetryingHttpClient(fake)

        response = client.send(make_request())

        assert response.status_code == 200
        assert response.attempts == 1

    def test_max_attempts_below_one_is_rejected(self):
        """AMB-4: max_attempts < 1 lanza ValueError."""
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=0)

    def test_negative_base_delay_is_rejected(self):
        """AMB-4: un base_delay negativo lanza ValueError."""
        with pytest.raises(ValueError):
            RetryPolicy(base_delay=-0.1)


class TestRetryLog:
    def test_each_retry_logs_a_warning(self, caplog):
        """AMB-10, AMB-4: cada intento fallido que se reintenta deja un WARNING."""
        client, _, _ = make_client([503, TransportError("corte"), 200])

        with caplog.at_level(logging.WARNING, logger=RETRY_LOGGER):
            client.send(make_request())

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_first_attempt_ok_logs_no_warning(self, caplog):
        """AMB-10: si no hay reintentos, no hay WARNING."""
        client, _, _ = make_client([200])

        with caplog.at_level(logging.WARNING, logger=RETRY_LOGGER):
            client.send(make_request())

        assert caplog.records == []

    def test_log_does_not_contain_the_token(self, caplog):
        """PC-10: el token no aparece en el log de los reintentos."""
        client, _, _ = make_client([503, TransportError("corte"), 503])

        with caplog.at_level(logging.DEBUG, logger=RETRY_LOGGER):
            client.send(make_request())

        assert TOKEN not in caplog.text
