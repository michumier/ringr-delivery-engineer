"""Ciclo de `BaseAgent.handle_turn` con un agente de prueba (CA-12, CA-13, AMB-5, AMB-11, PC-8)."""

import logging
from collections.abc import Mapping

import pytest

from ringr_agents.agents import BaseAgent
from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.enums import ActionStatus, TurnError
from ringr_agents.domain.fields import FieldNormalizer, TextField
from ringr_agents.infrastructure.http import TransportError
from ringr_agents.infrastructure.models import ScriptExhaustedError

from .constants import KEY, TOKEN


class ReminderAgent(BaseAgent):
    """Tercer agente ficticio, definido solo en el test (CA-13)."""

    action_name = "register_reminder"
    action_url = "https://api.ringr.test/v1/reminder"

    def fields(self) -> Mapping[str, FieldNormalizer]:
        return {"note": TextField()}

    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        return data.get("note") is not None


@pytest.fixture
def make_agent(make_deps):
    def _make(conversation, parser, http_results=()):
        conversation_model, parser_model, sender, client = make_deps(
            conversation, parser, http_results
        )
        return ReminderAgent(conversation_model, parser_model, sender), client

    return _make


class TestExtensibility:
    def test_a_new_agent_works_with_handle_turn_without_touching_src(self, make_agent):
        """CA-13: un agente nuevo solo declara campos, regla, acción y URL."""
        agent, client = make_agent(["Hecho."], [{"note": "llamar mañana"}])

        result = agent.handle_turn()

        assert result.reply == "Hecho."
        assert result.action_status is ActionStatus.SENT
        assert len(client.requests) == 1
        request = client.requests[0]
        assert request.url == "https://api.ringr.test/v1/reminder"
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        assert request.headers["Idempotency-Key"] == KEY
        assert request.body == '{"note": "llamar mañana"}'


class TestHappyPath:
    def test_sent_when_all_ok_and_it_applies(self, make_agent):
        """CA-12 y AMB-5: respuesta normal, SENT, sin errores y con send_result ok."""
        agent, client = make_agent(["Hecho."], [{"note": "a"}])

        result = agent.handle_turn()

        assert result.reply == "Hecho."
        assert result.action_status is ActionStatus.SENT
        assert result.errors == ()
        assert result.warnings == ()
        assert result.data == {"note": "a"}
        assert result.send_result is not None
        assert result.send_result.ok is True
        assert result.send_result.idempotency_key == KEY
        assert len(client.requests) == 1

    def test_not_required_when_should_execute_is_false(self, make_agent):
        """AMB-5 y RF-16: faltan datos -> respuesta normal, NOT_REQUIRED y 0 requests."""
        agent, client = make_agent(["Dígame."], [{"note": None}])

        result = agent.handle_turn()

        assert result.reply == "Dígame."
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.errors == ()
        assert result.send_result is None
        assert client.requests == []

    def test_data_keeps_only_declared_fields(self, make_agent):
        """CA-10 y AMB-2: las claves que sobran no aparecen en los datos."""
        agent, _ = make_agent(["ok"], [{"note": "a", "otra": 1}])

        result = agent.handle_turn()

        assert dict(result.data) == {"note": "a"}

    def test_returns_a_new_result_each_turn(self, make_agent):
        """AMB-12: cada turno devuelve su propio resultado."""
        agent, client = make_agent(["a", "b"], [{"note": None}, {"note": "x"}])

        first = agent.handle_turn()
        second = agent.handle_turn()

        assert first.reply == "a"
        assert second.reply == "b"
        assert len(client.requests) == 1


class TestConversationFailure:
    def test_gives_emergency_reply_and_sends_nothing(self, make_agent):
        """AMB-11 y PC-8.2: si falla answer_user no se envía, aunque el parser dé datos."""
        agent, client = make_agent([RuntimeError("caído")], [{"note": "a"}])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.errors == (TurnError.CONVERSATION_FAILED,)
        assert result.send_result is None
        assert client.requests == []

    def test_parser_is_still_called_in_that_turn(self, make_agent):
        """AMB-11: el parser se llama igualmente (el siguiente turno usa su siguiente guion)."""
        agent, client = make_agent(
            [RuntimeError("caído"), "Hecho."], [{"note": "primero"}, {"note": "segundo"}]
        )

        agent.handle_turn()
        second = agent.handle_turn()

        assert second.data == {"note": "segundo"}
        assert second.action_status is ActionStatus.SENT
        assert len(client.requests) == 1


class TestParserFailure:
    def test_gives_emergency_reply_with_empty_data(self, make_agent):
        """AMB-11 y PC-8: si falla parse_data -> emergencia, datos a None y sin envío."""
        agent, client = make_agent(["Hecho."], [RuntimeError("caído")])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.errors == (TurnError.PARSER_FAILED,)
        assert dict(result.data) == {"note": None}
        assert client.requests == []

    @pytest.mark.parametrize("bad", [None, [], "texto"])
    def test_a_result_that_is_not_a_dict_counts_as_parser_failure(self, make_agent, bad):
        """AMB-11 y PC-8: si parse_data no devuelve un dict -> emergencia y PARSER_FAILED."""
        agent, client = make_agent(["Hecho."], [bad])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.errors == (TurnError.PARSER_FAILED,)
        assert dict(result.data) == {"note": None}
        assert client.requests == []

    def test_both_models_failing_report_both_errors_in_order(self, make_agent):
        """AMB-11: si fallan los dos, CONVERSATION_FAILED antes que PARSER_FAILED."""
        agent, client = make_agent([RuntimeError("a")], [RuntimeError("b")])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.NOT_REQUIRED
        assert result.errors == (TurnError.CONVERSATION_FAILED, TurnError.PARSER_FAILED)
        assert client.requests == []


class TestSendFailure:
    def test_error_status_gives_emergency_reply_and_failed(self, make_agent):
        """AMB-4, AMB-11 y PC-8: con 503 -> emergencia, FAILED y SEND_FAILED."""
        agent, client = make_agent(["Hecho."], [{"note": "a"}], http_results=[503])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.FAILED
        assert result.errors == (TurnError.SEND_FAILED,)
        assert result.send_result is not None
        assert result.send_result.ok is False
        assert result.send_result.status_code == 503
        assert len(client.requests) == 1

    def test_transport_error_gives_emergency_reply_and_failed(self, make_agent):
        """AMB-4 y AMB-11: un TransportError también acaba en FAILED, sin lanzar."""
        agent, _ = make_agent(["Hecho."], [{"note": "a"}], http_results=[TransportError()])

        result = agent.handle_turn()

        assert result.reply == EMERGENCY_REPLY
        assert result.action_status is ActionStatus.FAILED
        assert result.errors == (TurnError.SEND_FAILED,)
        assert result.send_result is not None
        assert result.send_result.ok is False
        assert result.send_result.status_code is None


class TestScriptExhausted:
    def test_conversation_script_exhausted_is_not_captured(self, make_agent):
        """PC-8.3: guion de conversación agotado -> la excepción sale del método."""
        agent, _ = make_agent([], [{"note": "a"}])

        with pytest.raises(ScriptExhaustedError):
            agent.handle_turn()

    def test_parser_script_exhausted_is_not_captured(self, make_agent):
        """PC-8.3: guion del parser agotado -> la excepción sale del método."""
        agent, _ = make_agent(["Hecho."], [])

        with pytest.raises(ScriptExhaustedError):
            agent.handle_turn()


class TestFailureLogging:
    @pytest.mark.parametrize(
        ("conversation", "parser", "method"),
        [
            ([RuntimeError("caído")], [{"note": "a"}], "answer_user"),
            (["Hecho."], [RuntimeError("caído")], "parse_data"),
        ],
    )
    def test_a_model_failure_is_logged_as_a_one_line_warning(
        self, make_agent, caplog, conversation, parser, method
    ):
        """AMB-10, AMB-11 y PR8: el fallo de un modelo deja un WARNING de una
        línea con la acción, el método y el tipo de error, sin la traza completa."""
        agent, _ = make_agent(conversation, parser)

        with caplog.at_level(logging.WARNING, logger="ringr_agents.agents.base_agent"):
            agent.handle_turn()

        failures = [r for r in caplog.records if f"falló {method}" in r.getMessage()]
        assert len(failures) == 1
        assert failures[0].levelno == logging.WARNING
        assert "register_reminder" in failures[0].getMessage()
        assert "RuntimeError: caído" in failures[0].getMessage()
        assert failures[0].exc_info is None
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
