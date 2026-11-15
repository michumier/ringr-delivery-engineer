"""Envío HTTP: request construida, resultado y log (RF-11, RF-12, RF-13, AMB-4, AMB-7, PASO3)."""

import json
import logging

import pytest

from ringr_agents.infrastructure.http.client import TransportError
from ringr_agents.infrastructure.http.fake_client import FakeHttpClient
from ringr_agents.infrastructure.http.sender import HttpActionSender

URL = "https://api.ringr.assistance/v1/request"
TOKEN = "ringr_test_token_9f3a2c1d"
SENDER_LOGGER = "ringr_agents.infrastructure.http.sender"


def make_sender(results=(), key="clave-fija"):
    client = FakeHttpClient(results)
    return HttpActionSender(client, TOKEN, new_idempotency_key=lambda: key), client


class TestRequestBuilt:
    def test_posts_to_the_given_url_with_bearer_token(self):
        """RF-11, RF-12, CA-4: POST a la URL con `Authorization: Bearer <token>`."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Hola"})

        sent = client.requests[0]
        assert sent.method == "POST"
        assert sent.url == URL
        assert sent.headers["Authorization"] == "Bearer ringr_test_token_9f3a2c1d"

    def test_sends_content_type_and_the_idempotency_key(self):
        """AMB-4, AMB-7: `Content-Type: application/json` e `Idempotency-Key` generada."""
        sender, client = make_sender(key="abc-123")

        sender.send(URL, {"request": "Hola"})

        headers = client.requests[0].headers
        assert headers["Content-Type"] == "application/json"
        assert headers["Idempotency-Key"] == "abc-123"

    def test_sends_one_encoded_header_per_non_null_field(self):
        """RF-13, CA-6, AMB-7: una cabecera por campo, con el valor codificado."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Cambiar dirección"})

        assert client.requests[0].headers["request"] == "Cambiar%20direcci%C3%B3n"

    def test_headers_use_the_same_names_as_the_parser_fields(self):
        """RF-13, CA-6: nombres iguales a los del parser; números como texto."""
        sender, client = make_sender()

        sender.send(
            "https://api.ringr.debt/v1/commitment",
            {"commitment_date": "2026-12-01", "committed_amount": 150.0},
        )

        headers = client.requests[0].headers
        assert headers["commitment_date"] == "2026-12-01"
        assert headers["committed_amount"] == "150.0"

    def test_none_values_go_neither_in_headers_nor_in_body(self):
        """RF-13, AMB-7: los campos `None` se omiten en cabeceras y cuerpo."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Hola", "extra": None})

        sent = client.requests[0]
        assert "extra" not in sent.headers
        assert json.loads(sent.body) == {"request": "Hola"}

    def test_body_is_json_with_accents_intact(self):
        """AMB-7, AMB-10: el cuerpo es JSON y la tilde no se escapa."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Cambiar dirección"})

        body = client.requests[0].body
        assert "dirección" in body
        assert json.loads(body) == {"request": "Cambiar dirección"}

    def test_body_keeps_the_numeric_type(self):
        """AMB-10, CA-2: el importe va como número en el JSON, no como texto."""
        sender, client = make_sender()

        sender.send(
            "https://api.ringr.debt/v1/commitment",
            {"commitment_date": "2026-12-01", "committed_amount": 150.0},
        )

        body = json.loads(client.requests[0].body)
        assert body == {"commitment_date": "2026-12-01", "committed_amount": 150.0}

    @pytest.mark.parametrize("name", ["Authorization", "Content-Type", "Idempotency-Key"])
    def test_a_field_cannot_override_the_fixed_headers(self, name):
        """RF-12, AMB-7: un campo con el nombre de una cabecera fija no la pisa."""
        sender, client = make_sender(key="clave-real")

        sender.send(URL, {name: "malicioso"})

        headers = client.requests[0].headers
        assert headers["Authorization"] == "Bearer ringr_test_token_9f3a2c1d"
        assert headers["Content-Type"] == "application/json"
        assert headers["Idempotency-Key"] == "clave-real"

    def test_default_generator_gives_a_different_key_each_time(self):
        """AMB-4: sin generador inyectado, cada envío lleva una clave distinta."""
        client = FakeHttpClient()
        sender = HttpActionSender(client, TOKEN)

        sender.send(URL, {"request": "a"})
        sender.send(URL, {"request": "a"})

        keys = {r.headers["Idempotency-Key"] for r in client.requests}
        assert len(keys) == 2


class TestSendResult:
    def test_200_is_ok(self):
        """CA-2, CA-4: un 200 es un envío correcto con 1 intento."""
        sender, _ = make_sender([200])

        result = sender.send(URL, {"request": "Hola"})

        assert result.ok is True
        assert result.status_code == 200
        assert result.attempts == 1

    @pytest.mark.parametrize("code", [503, 400])
    def test_error_status_is_not_ok_after_one_attempt(self, code):
        """AMB-4: 503 o 400 llegan al sender como `ok=False` con 1 intento."""
        sender, _ = make_sender([code])

        result = sender.send(URL, {"request": "Hola"})

        assert result.ok is False
        assert result.status_code == code
        assert result.attempts == 1

    def test_transport_error_is_not_raised_and_has_no_status(self):
        """AMB-4: un TransportError no se propaga; `ok=False` y `status_code=None`."""
        sender, _ = make_sender([TransportError("timeout")])

        result = sender.send(URL, {"request": "Hola"})

        assert result.ok is False
        assert result.status_code is None
        assert result.attempts == 1

    def test_transport_error_attempts_are_reported(self):
        """AMB-4: los intentos del error de transporte pasan al resultado."""
        sender, _ = make_sender([TransportError("timeout", attempts=3)])

        result = sender.send(URL, {"request": "Hola"})

        assert result.attempts == 3

    @pytest.mark.parametrize("results", [[200], [503], [TransportError()]])
    def test_result_key_matches_the_key_of_the_stored_request(self, results):
        """AMB-4: `SendResult.idempotency_key` es la de la request enviada."""
        sender, client = make_sender(results, key="clave-xyz")

        result = sender.send(URL, {"request": "Hola"})

        assert result.idempotency_key == "clave-xyz"
        assert client.requests[0].headers["Idempotency-Key"] == result.idempotency_key

    def test_builds_the_request_once_per_send(self):
        """AMB-4: un envío produce exactamente una request en el cliente."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Hola"})

        assert len(client.requests) == 1


class TestSendLogging:
    def test_logs_the_start_and_the_end_of_a_successful_send(self, caplog):
        """PASO3: cada envío deja log con URL e Idempotency-Key, en INFO si va bien."""
        sender, _ = make_sender([200], key="k-1")

        with caplog.at_level(logging.INFO, logger=SENDER_LOGGER):
            sender.send(URL, {"request": "Hola"})

        records = [r for r in caplog.records if r.name == SENDER_LOGGER]
        assert len(records) == 2
        assert all(r.levelno == logging.INFO for r in records)
        assert all(URL in r.getMessage() and "k-1" in r.getMessage() for r in records)
        assert "200" in records[1].getMessage()

    def test_logs_a_warning_for_an_error_status(self, caplog):
        """PASO3: un 503 se registra como WARNING con su código."""
        sender, _ = make_sender([503], key="k-2")

        with caplog.at_level(logging.INFO, logger=SENDER_LOGGER):
            sender.send(URL, {"request": "Hola"})

        last = caplog.records[-1]
        assert last.levelno == logging.WARNING
        assert "503" in last.getMessage()
        assert "k-2" in last.getMessage()

    def test_logs_a_warning_when_there_is_no_response(self, caplog):
        """PASO3: un error de transporte se registra como WARNING."""
        sender, _ = make_sender([TransportError("timeout")], key="k-3")

        with caplog.at_level(logging.INFO, logger=SENDER_LOGGER):
            sender.send(URL, {"request": "Hola"})

        last = caplog.records[-1]
        assert last.levelno == logging.WARNING
        assert "timeout" in last.getMessage()
        assert "k-3" in last.getMessage()

    def test_log_does_not_contain_the_token(self, caplog):
        """PASO3, PC-10: el token no se escribe en el log."""
        sender, _ = make_sender([200])

        with caplog.at_level(logging.DEBUG):
            sender.send(URL, {"request": "Hola"})

        assert TOKEN not in caplog.text


class TestRequestSafety:
    @pytest.mark.parametrize("name", ["authorization", "CONTENT-TYPE", "idempotency-key"])
    def test_a_field_with_a_reserved_name_in_other_case_is_not_sent_as_header(self, name):
        """RF-12, AMB-7: en HTTP las cabeceras no distinguen mayúsculas; no se mandan dos."""
        sender, client = make_sender(key="clave-real")

        sender.send(URL, {name: "malicioso"})

        headers = client.requests[0].headers
        same_name = [h for h in headers if h.lower() == name.lower()]
        assert len(same_name) == 1  # solo la cabecera fija, no una segunda
        assert "malicioso" not in headers.values()
        assert json.loads(client.requests[0].body) == {name: "malicioso"}

    def test_a_line_break_in_a_value_cannot_inject_a_header(self):
        """PC-12: `quote` codifica el salto de línea; no se puede colar otra cabecera."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Hola\r\nX-Falsa: si"})

        value = client.requests[0].headers["request"]
        assert "\r" not in value and "\n" not in value
        assert value == "Hola%0D%0AX-Falsa%3A%20si"

    def test_repr_of_the_request_does_not_show_the_token(self):
        """PC-10: si se imprime la request (p. ej. en un test que falla) no sale el token."""
        sender, client = make_sender()

        sender.send(URL, {"request": "Hola"})

        assert TOKEN not in repr(client.requests[0])


class TestTokenNeverLogged:
    @pytest.mark.parametrize("result", [503, TransportError("timeout")])
    def test_token_is_not_logged_when_the_send_fails(self, caplog, result):
        """PASO3, PC-10: ni con un 503 ni sin respuesta sale el token en el log."""
        sender, _ = make_sender([result])

        with caplog.at_level(logging.DEBUG):
            sender.send(URL, {"request": "Hola"})

        assert TOKEN not in caplog.text

    def test_transport_error_log_includes_the_attempts(self, caplog):
        """PASO3: el log de un envío sin respuesta lleva también los intentos."""
        sender, _ = make_sender([TransportError("timeout", attempts=3)])

        with caplog.at_level(logging.INFO, logger=SENDER_LOGGER):
            sender.send(URL, {"request": "Hola"})

        assert "intentos 3" in caplog.records[-1].getMessage()
