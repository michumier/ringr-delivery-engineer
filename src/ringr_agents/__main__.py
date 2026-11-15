"""Raíz de composición y demo (`python -m ringr_agents`).

Es el único archivo que conoce a la vez los agentes y los adaptadores concretos: monta
`Settings` → `FakeHttpClient` → `RetryingHttpClient` → `HttpActionSender` → modelos con guion
→ agentes, y ejecuta 8 conversaciones de ejemplo (DEMO2). Nada sale a la red: el servidor es
simulado.
"""

import io
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, TextIO

from ringr_agents.agents import AssistanceAgent, BaseAgent, DebtAgent
from ringr_agents.domain.ports import ActionSender
from ringr_agents.domain.results import TurnResult
from ringr_agents.infrastructure.config import Settings
from ringr_agents.infrastructure.http import (
    FakeHttpClient,
    HttpActionSender,
    HttpClient,
    HttpRequest,
    RetryingHttpClient,
    RetryPolicy,
    TransportError,
)
from ringr_agents.infrastructure.models import ConversationModel, ParserModel

# Nombre fijo: al ejecutar con `python -m`, `__name__` vale "__main__" y no diría de dónde sale.
logger = logging.getLogger("ringr_agents.demo")

# «Hoy» fijo: así la demo da los mismos resultados, se ejecute el día que se ejecute.
DEMO_TODAY = date(2026, 11, 15)

# Un turno del guion: lo que dice el modelo de conversación y lo que devuelve el parser
# (normalmente un dict; en el escenario 8, algo que no lo es).
Turn = tuple[str, Any]
ServerReply = int | TransportError
# Cualquier cosa que cree un agente con sus dos modelos y su sender: la propia clase o una
# función. Así un agente nuevo entra en la demo sin tocar `build_agent`.
AgentFactory = Callable[[ConversationModel, ParserModel, ActionSender], BaseAgent]


def debt_agent(
    conversation: ConversationModel, parser: ParserModel, sender: ActionSender
) -> BaseAgent:
    """`DebtAgent` con el «hoy» fijo de la demo."""
    return DebtAgent(conversation, parser, sender, today=lambda: DEMO_TODAY)


@dataclass(frozen=True)
class Scenario:
    """Una conversación de la demo: qué agente, qué turnos y qué responde el servidor."""

    key: str
    title: str
    make_agent: AgentFactory  # crea el agente de esta conversación
    turns: Sequence[Turn]
    # Lo que responde el servidor a cada intento, en orden; cuando se acaba, 200.
    server: Sequence[ServerReply] = ()


SCENARIOS: Sequence[Scenario] = (
    Scenario(
        key="todo_bien",
        title="deuda, todo bien",
        make_agent=debt_agent,
        turns=(
            (
                "Perfecto, apunto 150,50 € para el 1 de diciembre.",
                {"commitment_date": "2026-12-01", "committed_amount": "150,50"},
            ),
        ),
    ),
    Scenario(
        key="poco_a_poco",
        title="deuda, el cliente da los datos poco a poco",
        make_agent=debt_agent,
        turns=(
            (
                "De acuerdo, el 1 de diciembre. ¿Qué importe podrá pagar?",
                {"commitment_date": "2026-12-01"},
            ),
            (
                "Perfecto, 75 € el 1 de diciembre.",
                {"commitment_date": "2026-12-01", "committed_amount": "75"},
            ),
        ),
    ),
    Scenario(
        key="repite_y_corrige",
        title="deuda, el cliente repite y corrige",
        make_agent=debt_agent,
        turns=(
            (
                "Perfecto, apunto 150,50 € para el 1 de diciembre.",
                {"commitment_date": "2026-12-01", "committed_amount": "150,50"},
            ),
            # Otro formato (150.5), mismos datos limpios → duplicado.
            (
                "Sí, queda registrado: 150,50 € el 1 de diciembre.",
                {"commitment_date": "2026-12-01", "committed_amount": 150.5},
            ),
            # Una corrección son datos nuevos → se envía otra vez.
            (
                "Entendido, lo cambio a 200 € para el 1 de diciembre.",
                {"commitment_date": "2026-12-01", "committed_amount": 200},
            ),
        ),
    ),
    Scenario(
        key="datos_raros",
        title="deuda, datos raros que se descartan",
        make_agent=debt_agent,
        turns=(
            (
                "El importe tiene que ser positivo.",
                {"commitment_date": "2026-12-01", "committed_amount": "-50"},
            ),
            (
                "¿Son mil quinientos euros?",
                {"commitment_date": "2026-12-01", "committed_amount": "1.500,50"},
            ),
            ("Esa fecha no existe.", {"commitment_date": "2026-02-30", "committed_amount": 100}),
            ("Esa fecha ya ha pasado.", {"commitment_date": "2026-10-01", "committed_amount": 100}),
            ("¿Qué día exactamente?", {"commitment_date": "mañana", "committed_amount": 100}),
        ),
    ),
    Scenario(
        key="reintento_salva",
        title="asistencia, el reintento salva el envío",
        make_agent=AssistanceAgent,
        turns=(("Tomo nota de su solicitud.", {"request": "  Cambiar la dirección de envío  "}),),
        server=(503, 200),
    ),
    Scenario(
        key="reintentos_agotados",
        title="asistencia, falla por la política de reintentos",
        make_agent=AssistanceAgent,
        turns=(
            ("Tomo nota de su solicitud.", {"request": "Enviar una copia de la factura"}),
            # Lo fallido no cuenta como enviado: al repetirlo se envía de nuevo.
            ("Lo intento de nuevo.", {"request": "Enviar una copia de la factura"}),
        ),
        server=(503, TransportError("tiempo de espera agotado"), 503),
    ),
    Scenario(
        key="error_4xx",
        title="asistencia, un 400 no se reintenta",
        make_agent=AssistanceAgent,
        turns=(("Tomo nota de su solicitud.", {"request": "Darme de baja"}),),
        server=(400,),
    ),
    Scenario(
        key="parser_roto",
        title="asistencia, el parser devuelve algo que no es un dict",
        make_agent=AssistanceAgent,
        turns=(
            ("Tomo nota de su solicitud.", ["esto", "no", "es", "un", "dict"]),
            ("Tomo nota de su solicitud.", {"request": "Hablar con un agente"}),
        ),
    ),
)


def build_client(
    responses: Sequence[ServerReply], settings: Settings, sleep: Callable[[float], None]
) -> tuple[FakeHttpClient, HttpClient]:
    """Servidor simulado envuelto con los reintentos (Decorator). Devuelve los dos."""
    fake = FakeHttpClient(responses)
    policy = RetryPolicy(
        max_attempts=settings.max_attempts, base_delay=settings.base_delay, sleep=sleep
    )
    return fake, RetryingHttpClient(fake, policy)


def build_agent(scenario: Scenario, client: HttpClient, settings: Settings) -> BaseAgent:
    """Crea el agente del escenario con sus modelos de guion."""
    conversation = ConversationModel([reply for reply, _ in scenario.turns])
    parser = ParserModel([parsed for _, parsed in scenario.turns])
    sender = HttpActionSender(client, settings.api_token)

    return scenario.make_agent(conversation, parser, sender)


def run_conversation(agent: BaseAgent, turns: Sequence[Turn], out: TextIO) -> list[TurnResult]:
    """Ejecuta un turno del agente por cada turno del guion y escribe un resumen de cada uno."""
    results = []
    for number in range(1, len(turns) + 1):
        # La cabecera va antes del turno para que su log salga debajo, no encima.
        print(f"\nTurno {number}", file=out)
        result = agent.handle_turn()
        results.append(result)
        data = {str(name): value for name, value in result.data.items()}
        print(f"  Respuesta : {result.reply}", file=out)
        print(f"  Datos     : {data}", file=out)
        print(f"  Acción    : {result.action_status}", file=out)
        if result.send_result is not None:
            print(
                f"  Envío     : código {result.send_result.status_code}, "
                f"intentos {result.send_result.attempts}",
                file=out,
            )
        for warning in result.warnings:
            print(f"  Aviso     : {warning}", file=out)
        for error in result.errors:
            print(f"  Error     : {error}", file=out)
    return results


def print_request(request: HttpRequest, out: TextIO) -> None:
    """Enseña la última request (URL, cabeceras y body) con el token tapado.

    Es solo la presentación de la demo: el log de cada envío no cambia (AMB-10).
    """
    print(f"\nÚltima petición: {request.method} {request.url}", file=out)
    for name, value in request.headers.items():
        shown = "Bearer ***" if name == "Authorization" else value
        print(f"  {name}: {shown}", file=out)
    print(f"  Body: {request.body}", file=out)


def run_demo(
    settings: Settings | None = None,
    sleep: Callable[[float], None] = time.sleep,
    out: TextIO | None = None,
) -> dict[str, list[TurnResult]]:
    """Ejecuta cada escenario como una conversación aparte. Devuelve sus resultados por clave."""
    settings = settings if settings is not None else Settings.from_env()
    # `sys.stdout` se lee al llamar, no al definir la función: así se puede capturar.
    out = out if out is not None else sys.stdout

    results: dict[str, list[TurnResult]] = {}
    total = len(SCENARIOS)
    for number, scenario in enumerate(SCENARIOS, start=1):
        # Un agente y un servidor nuevos por escenario: las conversaciones no se mezclan.
        fake, client = build_client(scenario.server, settings, sleep)
        agent = build_agent(scenario, client, settings)
        print(file=out)
        logger.info("===== Conversación %s/%s: %s =====", number, total, scenario.title)
        results[scenario.key] = run_conversation(agent, scenario.turns, out)
        if fake.requests:
            print_request(fake.requests[-1], out)
        logger.info(
            "===== Fin de la conversación %s: peticiones al servidor: %s =====",
            number,
            len(fake.requests),
        )
    return results


def main() -> None:
    """Punto de entrada: el log y el resumen de los turnos salen juntos y en orden por stdout."""
    # En Windows, al redirigir la salida a un archivo se usa cp1252 y «€» o «ñ» salen mal.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    run_demo()


if __name__ == "__main__":
    main()
