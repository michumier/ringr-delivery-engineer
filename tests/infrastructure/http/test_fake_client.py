"""Cliente HTTP simulado: guarda las requests y responde según una secuencia (CA-14, AMB-4)."""

import pytest

from ringr_agents.infrastructure.http.client import HttpRequest, TransportError
from ringr_agents.infrastructure.http.fake_client import FakeHttpClient


def make_request(url: str = "https://api.example/v1/x") -> HttpRequest:
    return HttpRequest(method="POST", url=url, headers={"A": "b"}, body="{}")


class TestFakeHttpClient:
    def test_stores_every_request_sent(self):
        """CA-14: el fake guarda las requests para poder inspeccionarlas, sin red."""
        client = FakeHttpClient()
        first, second = make_request("https://a"), make_request("https://b")

        client.send(first)
        client.send(second)

        assert client.requests == [first, second]

    def test_answers_200_when_no_sequence_is_given(self):
        """CA-2: sin secuencia configurada la respuesta simulada es 200."""
        client = FakeHttpClient()

        response = client.send(make_request())

        assert response.status_code == 200

    def test_returns_the_sequence_in_order_and_then_200(self):
        """AMB-4: devuelve los códigos en orden y, agotada la secuencia, 200."""
        client = FakeHttpClient([503, 400])

        codes = [client.send(make_request()).status_code for _ in range(3)]

        assert codes == [503, 400, 200]

    def test_raises_the_configured_transport_error(self):
        """AMB-4: un TransportError en la secuencia se lanza, y la request queda guardada."""
        error = TransportError("timeout", attempts=3)
        client = FakeHttpClient([error])

        with pytest.raises(TransportError) as raised:
            client.send(make_request())

        assert raised.value is error
        assert len(client.requests) == 1

    def test_continues_with_the_sequence_after_a_transport_error(self):
        """AMB-4: tras lanzar el error, el siguiente envío usa el siguiente elemento."""
        client = FakeHttpClient([TransportError(), 503])
        with pytest.raises(TransportError):
            client.send(make_request())

        response = client.send(make_request())

        assert response.status_code == 503

    def test_ignores_later_changes_to_the_list_given_by_the_caller(self):
        """AMB-4: el fake copia la secuencia; modificar la lista original no la altera."""
        results = [503]
        client = FakeHttpClient(results)
        results.clear()

        response = client.send(make_request())

        assert response.status_code == 503
