"""Log de `handle_turn`: una línea por paso, sin valores del cliente (LOGS, PASO3, PC-10)."""

import logging
from collections.abc import Mapping

import pytest

from ringr_agents.agents import BaseAgent, DebtAgent
from ringr_agents.domain.fields import FieldNormalizer, TextField
from ringr_agents.infrastructure.http import TransportError

from .constants import KEY, TOKEN

LOGGER = "ringr_agents.agents.base_agent"
ACTION = "register_commitment"
VALID = {"commitment_date": "2026-12-01", "committed_amount": 150.0}
CLIENT_VALUES = ("2026-12-01", "150", "no-debe-salir-en-el-log")


class NeverAgent(BaseAgent):
    """Agente de prueba con datos completos pero que nunca cumple su regla."""

    action_name = "never_action"
    action_url = "https://api.ringr.test/v1/never"

    def fields(self) -> Mapping[str, FieldNormalizer]:
        return {"note": TextField()}

    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        return False


@pytest.fixture
def make_agent(make_deps, today):
    def _make(conversation, parser, http_results=()):
        conversation_model, parser_model, sender, client = make_deps(
            conversation, parser, http_results
        )
        return DebtAgent(conversation_model, parser_model, sender, today=today), client

    return _make


def _records(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


def _only(caplog, text):
    """Devuelve el único registro del logger cuyo mensaje contiene `text`."""
    found = [r for r in _records(caplog) if text in r.getMessage()]
    assert len(found) == 1, [r.getMessage() for r in _records(caplog)]
    return found[0]


def _assert_no_client_values(caplog, extra=()):
    for record in _records(caplog):
        message = record.getMessage()
        for value in (*CLIENT_VALUES, TOKEN, KEY, *extra):
            assert value not in message, message


class TestEachStepLeavesItsLine:
    def test_model_down_logs_a_warning_with_the_action_name(self, make_agent, caplog):
        """LOGS: modelo caído -> WARNING «ha fallado un modelo» con el nombre de la acción."""
        agent, _ = make_agent([RuntimeError("caído")], [VALID])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "ha fallado un modelo; no se ejecuta la acción")
        assert record.levelno == logging.WARNING
        assert ACTION in record.getMessage()

    def test_missing_fields_logs_info_naming_only_the_missing_field(self, make_agent, caplog):
        """LOGS: faltan datos -> INFO que nombra el campo que falta, no el que llegó."""
        agent, client = make_agent(["Dígame."], [{"commitment_date": "2026-12-01"}])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "faltan datos")
        assert record.levelno == logging.INFO
        assert ACTION in record.getMessage()
        assert "committed_amount" in record.getMessage()
        assert "commitment_date" not in record.getMessage()
        assert "no se ejecuta la acción" in record.getMessage()
        assert client.requests == []

    def test_all_fields_missing_names_all_of_them(self, make_agent, caplog):
        """LOGS: si no llega ningún dato, la línea nombra todos los campos que faltan."""
        agent, _ = make_agent(["Dígame."], [{}])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        message = _only(caplog, "faltan datos").getMessage()
        assert "commitment_date" in message
        assert "committed_amount" in message

    def test_conditions_not_met_logs_info_without_missing_fields(self, make_deps, caplog):
        """LOGS: should_execute falso sin campos None -> INFO «no se cumplen las condiciones»."""
        conversation, parser, sender, client = make_deps(["Ok."], [{"note": "secreto"}])
        agent = NeverAgent(conversation, parser, sender)

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "no se cumplen las condiciones")
        assert record.levelno == logging.INFO
        assert "never_action" in record.getMessage()
        assert not [r for r in _records(caplog) if "faltan datos" in r.getMessage()]
        assert client.requests == []
        _assert_no_client_values(caplog, extra=("secreto",))

    def test_duplicate_logs_info_and_does_not_send_again(self, make_agent, caplog):
        """LOGS y AMB-1: el segundo turno con los mismos datos deja INFO de duplicado."""
        agent, client = make_agent(["a", "b"], [VALID, VALID])
        agent.handle_turn()
        caplog.clear()

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "estos mismos datos ya se enviaron")
        assert record.levelno == logging.INFO
        assert ACTION in record.getMessage()
        assert not [r for r in _records(caplog) if "se ejecuta la acción" in r.getMessage()]
        assert len(client.requests) == 1

    def test_before_sending_logs_info_that_the_action_runs(self, make_agent, caplog):
        """LOGS: con datos completos y nuevos, INFO «se ejecuta la acción» antes de enviar."""
        agent, _ = make_agent(["Anotado."], [VALID])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        messages = [r.getMessage() for r in _records(caplog)]
        record = _only(caplog, "datos completos y nuevos; se ejecuta la acción")
        assert record.levelno == logging.INFO
        assert ACTION in record.getMessage()
        run_index = messages.index(record.getMessage())
        assert "acción registrada" in messages[run_index + 1]

    def test_sent_logs_info_with_code_and_attempts(self, make_agent, caplog):
        """LOGS: envío correcto -> INFO «acción registrada (código 200, intentos 1)»."""
        agent, _ = make_agent(["Anotado."], [VALID], [200])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "acción registrada")
        assert record.levelno == logging.INFO
        assert ACTION in record.getMessage()
        assert "código 200" in record.getMessage()
        assert "intentos 1" in record.getMessage()

    @pytest.mark.parametrize("failure", [400, TransportError("sin red")])
    def test_failed_logs_warning_with_code_and_attempts(self, make_agent, caplog, failure):
        """LOGS: envío fallido -> WARNING «no se ha podido registrar» con código e intentos."""
        agent, _ = make_agent(["Anotado."], [VALID], [failure])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "la acción no se ha podido registrar")
        assert record.levelno == logging.WARNING
        assert ACTION in record.getMessage()
        assert "código" in record.getMessage()
        assert "intentos 1" in record.getMessage()
        assert not [r for r in _records(caplog) if "acción registrada" in r.getMessage()]


class TestTurnStartLine:
    def test_each_turn_starts_with_one_line_that_comes_first(self, make_agent, caplog):
        """DEMO2: cada turno escribe una sola línea INFO «empieza el turno», la primera."""
        agent, _ = make_agent(["a", "b"], [VALID, VALID])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()
            first_turn = [r.getMessage() for r in _records(caplog)]
            caplog.clear()
            agent.handle_turn()
            second_turn = [r.getMessage() for r in _records(caplog)]

        for messages in (first_turn, second_turn):
            starts = [m for m in messages if "empieza el turno" in m]
            assert len(starts) == 1
            assert messages[0] == starts[0]
            assert ACTION in starts[0]

    def test_start_line_is_info_and_has_no_client_values(self, make_agent, caplog):
        """DEMO2 y PC-10: la línea de inicio es INFO y no incluye valores del cliente."""
        agent, _ = make_agent(["no-debe-salir-en-el-log"], [VALID])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        record = _only(caplog, "empieza el turno")
        assert record.levelno == logging.INFO
        _assert_no_client_values(caplog)


class TestNoClientValuesInTheLog:
    """LOGS, PASO3 y PC-10: los mensajes nombran campos, nunca valores del cliente."""

    def test_sent_turn_messages_do_not_contain_client_values(self, make_agent, caplog):
        """LOGS y PC-10: ni fecha, ni importe, ni token, ni clave de idempotencia."""
        agent, _ = make_agent(["no-debe-salir-en-el-log"], [VALID])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        assert _records(caplog)
        _assert_no_client_values(caplog)

    def test_failed_turn_messages_do_not_contain_client_values(self, make_agent, caplog):
        """LOGS y PC-10: el envío fallido tampoco filtra datos del cliente."""
        agent, client = make_agent(["no-debe-salir-en-el-log"], [VALID], [500])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        assert _records(caplog)
        _assert_no_client_values(caplog, extra=(client.requests[0].body,))

    def test_missing_fields_turn_does_not_contain_the_value_that_did_arrive(
        self, make_agent, caplog
    ):
        """LOGS: con un campo presente y otro ausente, solo se nombra el ausente."""
        agent, _ = make_agent(["no-debe-salir-en-el-log"], [{"commitment_date": "2026-12-01"}])

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        assert _records(caplog)
        _assert_no_client_values(caplog)

    def test_duplicate_turn_messages_do_not_contain_client_values(self, make_agent, caplog):
        """LOGS: el turno duplicado tampoco muestra valores."""
        agent, _ = make_agent(["a", "no-debe-salir-en-el-log"], [VALID, VALID])
        agent.handle_turn()
        caplog.clear()

        with caplog.at_level(logging.DEBUG, logger=LOGGER):
            agent.handle_turn()

        assert _records(caplog)
        _assert_no_client_values(caplog)
