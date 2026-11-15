"""Fixtures comunes de los tests de agentes: modelos con guion, envío real y cliente simulado."""

import pytest

from ringr_agents.infrastructure.http import FakeHttpClient, HttpActionSender
from ringr_agents.infrastructure.models import ConversationModel, ParserModel

from .constants import KEY, TODAY, TOKEN


@pytest.fixture
def today():
    """«Hoy» fijo para los agentes que validan fechas (PC-4)."""
    return lambda: TODAY


@pytest.fixture
def make_deps():
    """Crea (conversación, parser, sender real, cliente simulado) a partir de guiones."""

    def _make(conversation, parser, http_results=()):
        client = FakeHttpClient(http_results)
        sender = HttpActionSender(client, TOKEN, new_idempotency_key=lambda: KEY)
        return ConversationModel(conversation), ParserModel(parser), sender, client

    return _make
