"""`DebtAgent`: esquema, regla de ejecución y turnos completos (CA-1, CA-2, CA-3, CA-6, CA-9)."""

import json

import pytest

from ringr_agents.agents import DebtAgent
from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.enums import ActionName, ActionStatus, FieldName
from ringr_agents.infrastructure.models import ScriptExhaustedError

from .constants import KEY, TOKEN

VALID = {"commitment_date": "2026-12-01", "committed_amount": 150.0}


@pytest.fixture
def make_agent(make_deps, today):
    def _make(conversation, parser, http_results=()):
        conversation_model, parser_model, sender, client = make_deps(
            conversation, parser, http_results
        )
        return DebtAgent(conversation_model, parser_model, sender, today=today), client

    return _make


class TestSchema:
    def test_declares_the_two_fields(self, make_agent):
        """RF-8: el agente de deuda declara fecha e importe."""
        agent, _ = make_agent(["x"], [{}])

        assert set(agent.fields()) == {FieldName.COMMITMENT_DATE, FieldName.COMMITTED_AMOUNT}

    def test_action_name_and_url(self):
        """RF-11 y PC-10: la acción y la URL viven en el agente."""
        assert DebtAgent.action_name == ActionName.REGISTER_COMMITMENT
        assert DebtAgent.action_url == "https://api.ringr.debt/v1/commitment"

    @pytest.mark.parametrize(
        ("date_value", "amount", "expected"),
        [
            ("2026-12-01", 150.0, True),
            ("2026-12-01", None, False),
            (None, 150.0, False),
            (None, None, False),
        ],
    )
    def test_should_execute_only_with_date_and_amount(
        self, make_agent, date_value, amount, expected
    ):
        """CA-3 y RF-8: solo se ejecuta si están fecha e importe."""
        agent, _ = make_agent(["x"], [{}])
        data = {"commitment_date": date_value, "committed_amount": amount}

        assert agent.should_execute(data) is expected

    def test_should_execute_false_with_empty_data(self, make_agent):
        """CA-10: un diccionario vacío equivale a «sin datos»."""
        agent, _ = make_agent(["x"], [{}])

        assert agent.should_execute({}) is False


class TestHandleTurn:
    def test_no_data_sends_nothing_and_returns_the_reply(self, make_agent):
        """CA-1 y CA-12: sin datos no hay request y se devuelve la respuesta del modelo."""
        agent, client = make_agent(
            ["Perfecto, queda anotado."],
            [{"commitment_date": None, "committed_amount": None}],
        )

        result = agent.handle_turn()

        assert result.reply == "Perfecto, queda anotado."
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert client.requests == []

    def test_each_model_is_called_exactly_once_per_turn(self, make_agent):
        """CA-1: una llamada a answer_user y otra a parse_data (el 2.º turno se agotaría)."""
        agent, _ = make_agent(["a"], [{"commitment_date": None, "committed_amount": None}])
        agent.handle_turn()

        with pytest.raises(ScriptExhaustedError):
            agent.handle_turn()

    def test_happy_path_sends_one_post_with_token_and_body(self, make_agent):
        """CA-2: 1 POST a la URL de cobros con Bearer y body con fecha e importe."""
        agent, client = make_agent(["Anotado."], [VALID])

        result = agent.handle_turn()

        assert result.reply == "Anotado."
        assert result.action_status is ActionStatus.SENT
        assert result.errors == ()
        assert result.send_result is not None
        assert result.send_result.ok is True
        assert len(client.requests) == 1
        request = client.requests[0]
        assert request.method == "POST"
        assert request.url == "https://api.ringr.debt/v1/commitment"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["Idempotency-Key"] == KEY
        assert json.loads(request.body) == VALID

    def test_data_fields_go_as_headers_too(self, make_agent):
        """CA-6: además de Authorization, cabeceras con los nombres de los campos."""
        agent, client = make_agent(["Anotado."], [VALID])

        agent.handle_turn()

        headers = client.requests[0].headers
        assert headers["commitment_date"] == "2026-12-01"
        assert headers["committed_amount"] == "150.0"

    @pytest.mark.parametrize(
        "parsed",
        [
            {"commitment_date": "2026-12-01", "committed_amount": None},
            {"commitment_date": None, "committed_amount": 150.0},
            {},
        ],
    )
    def test_incomplete_data_sends_nothing(self, make_agent, parsed):
        """CA-3 y CA-10: con datos incompletos no hay request y el estado es NOT_REQUIRED."""
        agent, client = make_agent(["Vale."], [parsed])

        result = agent.handle_turn()

        assert result.reply == "Vale."
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.errors == ()
        assert result.send_result is None
        assert client.requests == []

    def test_extra_keys_are_ignored(self, make_agent):
        """CA-10 y AMB-2: una clave de más se ignora y no viaja en la request."""
        agent, client = make_agent(["Ok"], [{**VALID, "extra": 1}])

        result = agent.handle_turn()

        assert result.action_status is ActionStatus.SENT
        assert "extra" not in result.data
        assert json.loads(client.requests[0].body) == VALID

    def test_past_date_is_discarded_and_nothing_is_sent(self, make_agent):
        """CA-9, AMB-2 y PC-4: fecha pasada -> None, aviso y sin envío."""
        agent, client = make_agent(
            ["Ok"], [{"commitment_date": "2026-11-14", "committed_amount": 150.0}]
        )

        result = agent.handle_turn()

        assert result.data[FieldName.COMMITMENT_DATE] is None
        assert result.data[FieldName.COMMITTED_AMOUNT] == 150.0
        assert result.warnings
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert client.requests == []

    def test_today_is_a_valid_date(self, make_agent):
        """AMB-3 y PC-4: la fecha de hoy vale."""
        agent, client = make_agent(
            ["Ok"], [{"commitment_date": "2026-11-15", "committed_amount": 150.0}]
        )

        result = agent.handle_turn()

        assert result.action_status is ActionStatus.SENT
        assert result.warnings == ()
        assert len(client.requests) == 1

    @pytest.mark.parametrize(
        "parsed",
        [
            {"commitment_date": "01/12/2026", "committed_amount": 150.0},
            {"commitment_date": "2026-12-01", "committed_amount": -50.0},
            {"commitment_date": "2026-13-45", "committed_amount": 150.0},
        ],
    )
    def test_invalid_field_is_discarded_with_warning_and_not_sent(self, make_agent, parsed):
        """CA-9 y AMB-2: un campo inválido pasa a None con aviso y no se envía."""
        agent, client = make_agent(["Ok"], [parsed])

        result = agent.handle_turn()

        assert None in result.data.values()
        assert len(result.warnings) == 1
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert client.requests == []

    def test_numeric_text_amount_is_normalized_and_sent(self, make_agent):
        """CA-9 y AMB-3: el importe «150» en texto se normaliza a 150.0 y se envía."""
        agent, client = make_agent(
            ["Ok"], [{"commitment_date": "2026-12-01", "committed_amount": "150"}]
        )

        result = agent.handle_turn()

        assert result.data[FieldName.COMMITTED_AMOUNT] == 150.0
        assert result.action_status is ActionStatus.SENT
        assert json.loads(client.requests[0].body) == VALID

    def test_each_turn_only_looks_at_its_own_data(self, make_agent):
        """AMB-12: los valores no se acumulan entre turnos."""
        agent, client = make_agent(
            ["Uno", "Dos"],
            [
                {"commitment_date": None, "committed_amount": 150.0},
                {"commitment_date": "2026-12-01", "committed_amount": 150.0},
            ],
        )

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.action_status is ActionStatus.NOT_REQUIRED
        assert second.action_status is ActionStatus.SENT
        assert len(client.requests) == 1

    def test_date_alone_then_amount_alone_never_sends(self, make_agent):
        """AMB-12: fecha en un turno e importe en otro no se combinan."""
        agent, client = make_agent(
            ["Uno", "Dos"],
            [
                {"commitment_date": "2026-12-01", "committed_amount": None},
                {"commitment_date": None, "committed_amount": 150.0},
            ],
        )

        results = [agent.handle_turn(), agent.handle_turn()]

        assert [r.action_status for r in results] == [ActionStatus.NOT_REQUIRED] * 2
        assert client.requests == []

    def test_http_failure_gives_emergency_reply(self, make_agent):
        """CA-11, AMB-4 y AMB-11: con 503 la respuesta es la de emergencia y FAILED."""
        agent, client = make_agent(["Anotado."], [VALID], http_results=[503])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.FAILED
        assert result.send_result is not None
        assert result.send_result.ok is False
        assert len(client.requests) == 1
