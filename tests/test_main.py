"""Demo (PLAN paso 7 y DEMO2): `python -m ringr_agents` ejecuta 8 conversaciones sin errores."""

import io
import logging

import pytest

from ringr_agents.__main__ import SCENARIOS, main, run_demo
from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.enums import ActionStatus, TurnError
from ringr_agents.infrastructure.config import DEFAULT_API_TOKEN, Settings

DEMO_LOGGER = "ringr_agents.demo"
KEYS = [
    "todo_bien",
    "poco_a_poco",
    "repite_y_corrige",
    "datos_raros",
    "reintento_salva",
    "reintentos_agotados",
    "error_4xx",
    "parser_roto",
]


def _run():
    sleeps: list[float] = []
    out = io.StringIO()
    results = run_demo(Settings(), sleeps.append, out)
    return results, sleeps, out.getvalue()


@pytest.fixture
def demo():
    """Ejecuta la demo con `Settings()` explícito y devuelve resultados, esperas y salida."""
    return _run()


def _statuses(results, key):
    return [r.action_status for r in results[key]]


def _demo_messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == DEMO_LOGGER]


def test_demo_returns_one_result_per_scenario_in_order(demo):
    """PLAN paso 7 y DEMO2: 8 escenarios, uno por conversación, con los turnos del guion."""
    results, _, _ = demo

    assert list(results) == KEYS
    assert [s.key for s in SCENARIOS] == KEYS
    for scenario in SCENARIOS:
        assert len(results[scenario.key]) == len(scenario.turns)


def test_todo_bien_sends_in_its_only_turn(demo):
    """DEMO2, RF-8 y CA-2: con fecha e importe válidos se envía."""
    assert _statuses(demo[0], "todo_bien") == [ActionStatus.SENT]


def test_poco_a_poco_does_not_send_until_all_data_arrives(demo):
    """DEMO2, RF-16 y AMB-12: sin importe no se envía; al llegar el importe, sí."""
    assert _statuses(demo[0], "poco_a_poco") == [ActionStatus.NOT_REQUIRED, ActionStatus.SENT]


def test_repite_y_corrige_sends_detects_duplicate_and_sends_the_correction(demo):
    """DEMO2, PC-7 y AMB-1: mismos datos limpios en otro formato = duplicado; corrección = envío."""
    statuses = _statuses(demo[0], "repite_y_corrige")

    assert statuses == [ActionStatus.SENT, ActionStatus.DUPLICATE, ActionStatus.SENT]


def test_datos_raros_are_discarded_with_one_warning_each(demo):
    """DEMO2, AMB-2 y AMB-3: importe negativo o ambiguo, fecha inexistente, pasada o texto."""
    turns = demo[0]["datos_raros"]

    assert [r.action_status for r in turns] == [ActionStatus.NOT_REQUIRED] * 5
    assert all(len(r.warnings) == 1 for r in turns)
    assert all(r.send_result is None for r in turns)


def test_reintento_salva_sends_at_the_second_attempt(demo):
    """DEMO2, AMB-4 y PC-7.1: un 503 y luego un 200 -> SENT con 2 intentos."""
    (turn,) = demo[0]["reintento_salva"]

    assert turn.action_status is ActionStatus.SENT
    assert turn.send_result.attempts == 2


def test_reintentos_agotados_fails_with_emergency_reply_then_sends(demo):
    """DEMO2, AMB-4, PC-7.2 y PC-8: 3 intentos fallidos -> emergencia; lo fallido se reenvía."""
    failed, sent = demo[0]["reintentos_agotados"]

    assert failed.action_status is ActionStatus.FAILED
    assert failed.send_result.attempts == 3
    assert failed.reply == EMERGENCY_REPLY
    assert TurnError.SEND_FAILED in failed.errors
    assert sent.action_status is ActionStatus.SENT


def test_error_4xx_fails_without_retrying(demo):
    """DEMO2 y AMB-4: un 400 no se reintenta -> FAILED con 1 intento."""
    (turn,) = demo[0]["error_4xx"]

    assert turn.action_status is ActionStatus.FAILED
    assert turn.send_result.attempts == 1


def test_parser_roto_does_not_send_and_the_next_turn_does(demo):
    """DEMO2 y PC-8.2: un parser que no devuelve dict -> PARSER_FAILED; luego se envía."""
    broken, sent = demo[0]["parser_roto"]

    assert broken.action_status is ActionStatus.NOT_REQUIRED
    assert TurnError.PARSER_FAILED in broken.errors
    assert sent.action_status is ActionStatus.SENT


def test_sleep_waits_follow_the_backoff(demo):
    """AMB-4: backoff exponencial 0.2 s (1 reintento) y 0.2 s, 0.4 s (2 reintentos)."""
    _, sleeps, _ = demo

    assert sleeps == [0.2, 0.2, 0.4]


def test_log_has_start_and_end_of_the_8_conversations_in_order(caplog):
    """DEMO2: cada conversación abre y cierra con su línea, con el nº de peticiones."""
    caplog.set_level(logging.INFO)
    _run()
    messages = _demo_messages(caplog)

    assert len(messages) == 16
    for number, scenario in enumerate(SCENARIOS, start=1):
        start, end = messages[2 * (number - 1)], messages[2 * (number - 1) + 1]
        assert start == f"===== Conversación {number}/8: {scenario.title} ====="
        assert end.startswith(f"===== Fin de la conversación {number}: peticiones al servidor: ")
        assert end.endswith(" =====")


def test_end_of_each_conversation_counts_the_real_requests(caplog):
    """DEMO2: todo_bien = 1 petición; reintentos_agotados = 3 + 1; parser_roto = 1."""
    caplog.set_level(logging.INFO)
    _run()
    ends = [m for m in _demo_messages(caplog) if "Fin de la conversación" in m]

    assert ends[0].endswith("peticiones al servidor: 1 =====")
    assert ends[5].endswith("peticiones al servidor: 4 =====")
    assert ends[7].endswith("peticiones al servidor: 1 =====")


def test_output_shows_turns_and_last_request_with_masked_token(demo):
    """PLAN paso 7, PC-10 y PASO7: se ve la request y el token sale como «Bearer ***»."""
    _, _, output = demo

    assert "Turno 1" in output
    assert "Última petición: POST https://api.ringr.debt/v1/commitment" in output
    assert "Última petición: POST https://api.ringr.assistance/v1/request" in output
    assert "Authorization: Bearer ***" in output


def test_neither_output_nor_log_contain_the_token(caplog):
    """PC-10: el token no aparece nunca, ni en lo impreso ni en los registros."""
    caplog.set_level(logging.INFO)
    _, _, output = _run()

    assert caplog.records
    assert DEFAULT_API_TOKEN not in output
    assert DEFAULT_API_TOKEN not in caplog.text


def test_main_runs_the_demo_with_the_environment_settings(monkeypatch, capsys):
    """PLAN paso 7: `main()` termina sin errores y no filtra el token.

    Se quitan las otras variables para no depender del entorno del equipo. No comprueba por
    dónde sale el log: dentro de pytest `logging.basicConfig` no hace nada.
    """
    monkeypatch.setenv("RINGR_RETRY_BASE_DELAY", "0")
    monkeypatch.delenv("RINGR_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("RINGR_API_TOKEN", raising=False)

    main()

    printed = capsys.readouterr().out
    assert "Turno 5" in printed
    assert "Bearer ***" in printed
    assert DEFAULT_API_TOKEN not in printed
