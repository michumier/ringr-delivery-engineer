"""`AssistanceAgent`: esquema, regla de ejecución y turnos completos (CA-4, CA-5, CA-6)."""

import json

import pytest

from ringr_agents.agents import AssistanceAgent
from ringr_agents.domain.enums import ActionName, ActionStatus, FieldName

from .conftest import TOKEN

REQUEST_TEXT = "Quiero cambiar mi dirección de facturación"


@pytest.fixture
def make_agent(make_deps):
    def _make(conversation, parser, http_results=()):
        conversation_model, parser_model, sender, client = make_deps(
            conversation, parser, http_results
        )
        return AssistanceAgent(conversation_model, parser_model, sender), client

    return _make


class TestSchema:
    def test_declares_only_request(self, make_agent):
        """RF-10: el agente de asistencia declara solo `request`."""
        agent, _ = make_agent(["x"], [{}])

        assert set(agent.fields()) == {FieldName.REQUEST}

    def test_action_name_and_url(self):
        """RF-11 y PC-10: la acción y la URL viven en el agente."""
        assert AssistanceAgent.action_name == ActionName.REGISTER_REQUEST
        assert AssistanceAgent.action_url == "https://api.ringr.assistance/v1/request"

    @pytest.mark.parametrize(("value", "expected"), [(REQUEST_TEXT, True), (None, False)])
    def test_should_execute_only_with_a_request(self, make_agent, value, expected):
        """CA-5 y RF-10: solo se ejecuta si hay petición."""
        agent, _ = make_agent(["x"], [{}])

        assert agent.should_execute({"request": value}) is expected

    def test_should_execute_false_with_empty_data(self, make_agent):
        """CA-10: un diccionario vacío equivale a «sin datos»."""
        agent, _ = make_agent(["x"], [{}])

        assert agent.should_execute({}) is False


class TestHandleTurn:
    def test_happy_path_sends_one_post_with_token_and_body(self, make_agent):
        """CA-4: 1 POST a la URL de asistencia con Bearer y body con la solicitud."""
        agent, client = make_agent(["Anotado."], [{"request": REQUEST_TEXT}])

        result = agent.handle_turn()

        assert result.reply == "Anotado."
        assert result.action_status is ActionStatus.SENT
        assert result.errors == ()
        assert len(client.requests) == 1
        request = client.requests[0]
        assert request.method == "POST"
        assert request.url == "https://api.ringr.assistance/v1/request"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert json.loads(request.body) == {"request": REQUEST_TEXT}

    def test_request_goes_as_header_too(self, make_agent):
        """CA-6: la cabecera `request` lleva la solicitud (codificada, AMB-7)."""
        agent, client = make_agent(["Anotado."], [{"request": "pedir ayuda"}])

        agent.handle_turn()

        assert client.requests[0].headers["request"] == "pedir%20ayuda"

    @pytest.mark.parametrize("parsed", [{"request": None}, {}, {"request": "   "}])
    def test_without_request_sends_nothing(self, make_agent, parsed):
        """CA-5 y CA-10: sin solicitud (o vacía) no hay request."""
        agent, client = make_agent(["Dígame."], [parsed])

        result = agent.handle_turn()

        assert result.reply == "Dígame."
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.send_result is None
        assert client.requests == []

    def test_each_turn_only_looks_at_its_own_data(self, make_agent):
        """AMB-12: el turno sin petición no usa la del turno anterior."""
        agent, client = make_agent(["Uno", "Dos"], [{"request": None}, {"request": REQUEST_TEXT}])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.NOT_REQUIRED
        assert second.action_status is ActionStatus.SENT
        assert len(client.requests) == 1
