"""Reintentos de punta a punta: agente, envío y reintentos (CA-11, AMB-4, PC-5, PC-7)."""

import pytest

from ringr_agents.agents import DebtAgent
from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.enums import ActionStatus, TurnError
from ringr_agents.infrastructure.http import (
    FakeHttpClient,
    HttpActionSender,
    HttpResponse,
    RetryingHttpClient,
    RetryPolicy,
    TransportError,
)
from ringr_agents.infrastructure.models import ConversationModel, ParserModel

from .constants import KEY, TODAY, TOKEN

DEBT = {"commitment_date": "2026-12-01", "committed_amount": 150.0}


@pytest.fixture
def make_agent():
    """Crea (agente, cliente simulado) con reintentos sin esperas reales."""

    def _make(http_results, turns=1):
        fake = FakeHttpClient(http_results)
        policy = RetryPolicy(sleep=lambda seconds: None)
        sender = HttpActionSender(
            RetryingHttpClient(fake, policy), TOKEN, new_idempotency_key=lambda: KEY
        )
        agent = DebtAgent(
            ConversationModel(["Anotado."] * turns),
            ParserModel([DEBT] * turns),
            sender,
            today=lambda: TODAY,
        )
        return agent, fake

    return _make


def test_503_then_200_ends_sent_with_two_attempts_and_same_key(make_agent):
    """CA-11, AMB-4: 503 y luego 200 acaba SENT con attempts=2 y la misma Idempotency-Key."""
    agent, fake = make_agent([503, 200])

    result = agent.handle_turn()

    assert result.action_status is ActionStatus.SENT
    assert result.send_result.attempts == 2
    assert result.send_result.ok is True
    assert len(fake.requests) == 2
    assert [r.headers["Idempotency-Key"] for r in fake.requests] == [KEY, KEY]


def test_three_503_ends_failed_with_emergency_reply(make_agent):
    """CA-11, AMB-4: tres 503 acaban FAILED con la respuesta de emergencia y attempts=3."""
    agent, fake = make_agent([503, 503, 503])

    result = agent.handle_turn()

    assert result.action_status is ActionStatus.FAILED
    assert result.reply == EMERGENCY_REPLY
    assert result.send_result.attempts == 3
    assert result.send_result.status_code == 503
    assert len(fake.requests) == 3


def test_three_transport_errors_end_failed_without_status_code(make_agent):
    """CA-11, AMB-4: tres errores de transporte acaban FAILED, status_code None y attempts=3."""
    agent, fake = make_agent([TransportError("t") for _ in range(3)])

    result = agent.handle_turn()

    assert result.action_status is ActionStatus.FAILED
    assert result.reply == EMERGENCY_REPLY
    assert result.errors == (TurnError.SEND_FAILED,)
    assert result.send_result.status_code is None
    assert result.send_result.attempts == 3
    assert len(fake.requests) == 3


def test_next_turn_after_exhausted_retries_sends_again(make_agent):
    """PC-5, AMB-4: tras un FAILED por reintentos agotados, el turno siguiente se reenvía."""
    agent, fake = make_agent([503, 503, 503, 200], turns=2)

    first = agent.handle_turn()
    second = agent.handle_turn()

    assert first.action_status is ActionStatus.FAILED
    assert second.action_status is ActionStatus.SENT
    assert second.send_result.attempts == 1
    assert len(fake.requests) == 4


class BrokenThenOkClient:
    """Lanza un error inesperado en la primera llamada y responde 200 en las siguientes."""

    def __init__(self):
        self.calls = 0

    def send(self, request):
        self.calls += 1
        if self.calls == 1:
            raise ValueError("certificado no válido")
        return HttpResponse(status_code=200)


def test_an_unexpected_client_error_fails_the_turn_and_the_next_turn_resends():
    """SEND-1, AMB-11, PC-8: el cliente recibe la respuesta de emergencia; como no se marcó
    como enviado, el turno siguiente con los mismos datos se envía."""
    client = BrokenThenOkClient()
    sender = HttpActionSender(
        RetryingHttpClient(client, RetryPolicy(sleep=lambda seconds: None)),
        TOKEN,
        new_idempotency_key=lambda: KEY,
    )
    agent = DebtAgent(
        ConversationModel(["Anotado."] * 2), ParserModel([DEBT] * 2), sender, today=lambda: TODAY
    )

    first = agent.handle_turn()
    second = agent.handle_turn()

    assert first.action_status is ActionStatus.FAILED
    assert first.reply == EMERGENCY_REPLY
    assert TurnError.SEND_FAILED in first.errors
    assert second.action_status is ActionStatus.SENT
    assert client.calls == 2
