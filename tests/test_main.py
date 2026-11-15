"""Prueba de humo de la demo (PLAN paso 7): `python -m ringr_agents` termina sin errores."""

import io
import logging

import pytest

from ringr_agents.__main__ import main, run_demo
from ringr_agents.domain.constants import EMERGENCY_REPLY
from ringr_agents.domain.enums import ActionStatus, TurnError
from ringr_agents.infrastructure.config import DEFAULT_API_TOKEN, Settings


@pytest.fixture
def demo():
    """Ejecuta la demo con `Settings()` explícito y registra las esperas y la salida."""
    sleeps: list[float] = []
    out = io.StringIO()
    results = run_demo(Settings(), sleeps.append, out)
    return results, sleeps, out.getvalue()


def test_la_demo_termina_y_devuelve_cinco_turnos_de_deuda_y_dos_de_asistencia(demo):
    """PLAN paso 7: la función principal termina sin errores y devuelve ambas conversaciones."""
    results, _, _ = demo

    assert len(results["debt"]) == 5
    assert len(results["assistance"]) == 2


def test_la_conversacion_de_deuda_envia_detecta_duplicado_y_descarta_fecha_pasada(demo):
    """PC-5, PC-7/AMB-4 y AMB-2: no enviar sin datos, no duplicar, descartar fecha pasada."""
    debt = demo[0]["debt"]

    statuses = [r.action_status for r in debt]

    assert statuses == [
        ActionStatus.NOT_REQUIRED,
        ActionStatus.SENT,
        ActionStatus.DUPLICATE,
        ActionStatus.SENT,
        ActionStatus.NOT_REQUIRED,
    ]
    assert debt[4].warnings  # aviso de fecha pasada


def test_la_conversacion_de_asistencia_reintenta_y_acaba_con_respuesta_de_emergencia(demo):
    """PC-8: éxito al segundo intento; fallo tras 3 intentos con respuesta de emergencia."""
    first, second = demo[0]["assistance"]

    assert first.action_status is ActionStatus.SENT
    assert first.send_result.attempts == 2
    assert second.action_status is ActionStatus.FAILED
    assert second.send_result.attempts == 3
    assert second.reply == EMERGENCY_REPLY
    assert TurnError.SEND_FAILED in second.errors


def test_las_esperas_pedidas_al_sleep_son_las_del_backoff(demo):
    """PC-8: backoff exponencial 0.2 s (1 reintento) y 0.2 s, 0.4 s (2 reintentos)."""
    _, sleeps, _ = demo

    assert sleeps == [0.2, 0.2, 0.4]


def test_la_salida_muestra_turnos_y_titulos_y_no_contiene_el_token(demo):
    """PLAN paso 7 y PC-10: el resumen es legible y no se imprime el token."""
    _, _, output = demo

    assert "Turno 1" in output
    assert "DebtAgent: compromiso de pago" in output
    assert "AssistanceAgent: solicitud de asistencia" in output
    assert DEFAULT_API_TOKEN not in output


def test_la_salida_ensena_la_ultima_peticion_con_el_token_tapado(demo):
    """Revisión de la PR 7 y PC-10: se ve la request (URL, cabeceras y body) sin el token."""
    _, _, output = demo

    assert "Última petición: POST https://api.ringr.debt/v1/commitment" in output
    assert "Authorization: Bearer ***" in output
    assert "committed_amount: 200.0" in output
    assert 'Body: {"commitment_date": "2026-12-01", "committed_amount": 200.0}' in output
    assert "Última petición: POST https://api.ringr.assistance/v1/request" in output


def test_el_log_de_la_demo_no_contiene_el_token(caplog):
    """PC-10: ningún registro INFO de la demo incluye el token."""
    caplog.set_level(logging.INFO)

    run_demo(Settings(), lambda _s: None, io.StringIO())

    assert caplog.records
    assert DEFAULT_API_TOKEN not in caplog.text


def test_main_ejecuta_la_demo_con_la_configuracion_del_entorno(monkeypatch, capsys):
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
    assert DEFAULT_API_TOKEN not in printed
