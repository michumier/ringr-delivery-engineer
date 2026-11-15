"""Raíz de composición y demo (`python -m ringr_agents`).

Es el único archivo que conoce a la vez los agentes y los adaptadores concretos: monta
`Settings` → `FakeHttpClient` → `RetryingHttpClient` → `HttpActionSender` → modelos con guion
→ agentes, y ejecuta dos conversaciones de ejemplo. Nada sale a la red: el servidor es simulado.
"""

import logging
import sys
import time
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, TextIO

from ringr_agents.agents import AssistanceAgent, BaseAgent, DebtAgent
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

# «Hoy» fijo: así la demo da los mismos resultados, se ejecute el día que se ejecute.
DEMO_TODAY = date(2026, 11, 15)

# Un turno del guion: lo que dice el modelo de conversación y lo que extrae el parser.
Turn = tuple[str, dict[str, Any]]

DEBT_TURNS: Sequence[Turn] = (
    # 1. El cliente aún no se compromete: no hay nada que enviar.
    ("¿Cuándo cree que podrá hacer el pago?", {}),
    # 2. Caso feliz: fecha e importe válidos («150,50» con coma) → se envía.
    (
        "Perfecto, apunto 150,50 € para el 1 de diciembre.",
        {"commitment_date": "2026-12-01", "committed_amount": "150,50"},
    ),
    # 3. Lo repite con otro formato (150.5): los datos limpios son los mismos → duplicado.
    (
        "Sí, queda registrado: 150,50 € el 1 de diciembre.",
        {"commitment_date": "2026-12-01", "committed_amount": 150.5},
    ),
    # 4. Corrige el importe: son datos nuevos → se envía otra vez.
    (
        "Entendido, lo cambio a 200 € para el 1 de diciembre.",
        {"commitment_date": "2026-12-01", "committed_amount": 200},
    ),
    # 5. Dice una fecha pasada: se descarta con un aviso y no se envía nada.
    (
        "Esa fecha ya ha pasado, ¿me indica otra?",
        {"commitment_date": "2026-10-01", "committed_amount": 200},
    ),
)

ASSISTANCE_TURNS: Sequence[Turn] = (
    # 1. El servidor responde 503 y al reintento 200 → se envía en 2 intentos.
    ("Tomo nota de su solicitud.", {"request": "  Cambiar la dirección de envío  "}),
    # 2. El servidor falla en los 3 intentos → respuesta de emergencia; no se marca como enviado.
    ("Tomo nota también de esto.", {"request": "Enviar una copia de la factura"}),
)

# Lo que responde el servidor simulado a cada intento, en orden (después, 200).
DEBT_SERVER: Sequence[int | TransportError] = ()
ASSISTANCE_SERVER: Sequence[int | TransportError] = (
    503,
    200,
    503,
    TransportError("tiempo de espera agotado"),
    503,
)


def build_client(
    responses: Sequence[int | TransportError], settings: Settings, sleep: Callable[[float], None]
) -> tuple[FakeHttpClient, HttpClient]:
    """Servidor simulado envuelto con los reintentos (Decorator). Devuelve los dos."""
    fake = FakeHttpClient(responses)
    policy = RetryPolicy(
        max_attempts=settings.max_attempts, base_delay=settings.base_delay, sleep=sleep
    )
    return fake, RetryingHttpClient(fake, policy)


def run_conversation(
    title: str, agent: BaseAgent, turns: Sequence[Turn], fake: FakeHttpClient, out: TextIO
) -> list[TurnResult]:
    """Ejecuta un turno del agente por cada turno del guion y escribe un resumen de cada uno."""
    print(f"\n=== {title} ===", file=out)
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
    print(f"\nPeticiones que recibió el servidor simulado: {len(fake.requests)}", file=out)
    if fake.requests:
        print_request(fake.requests[-1], out)
    return results


def print_request(request: HttpRequest, out: TextIO) -> None:
    """Enseña la última request (URL, cabeceras y body) con el token tapado.

    Es solo la presentación de la demo: el log de cada envío no cambia (AMB-10).
    """
    print(f"Última petición: {request.method} {request.url}", file=out)
    for name, value in request.headers.items():
        shown = "Bearer ***" if name == "Authorization" else value
        print(f"  {name}: {shown}", file=out)
    print(f"  Body: {request.body}", file=out)


def run_demo(
    settings: Settings | None = None,
    sleep: Callable[[float], None] = time.sleep,
    out: TextIO | None = None,
) -> dict[str, list[TurnResult]]:
    """Monta los dos agentes y ejecuta sus conversaciones. Devuelve los resultados."""
    settings = settings if settings is not None else Settings.from_env()
    # `sys.stdout` se lee al llamar, no al definir la función: así se puede capturar.
    out = out if out is not None else sys.stdout

    debt_fake, debt_client = build_client(DEBT_SERVER, settings, sleep)
    debt = DebtAgent(
        ConversationModel([reply for reply, _ in DEBT_TURNS]),
        ParserModel([data for _, data in DEBT_TURNS]),
        HttpActionSender(debt_client, settings.api_token),
        today=lambda: DEMO_TODAY,
    )

    assistance_fake, assistance_client = build_client(ASSISTANCE_SERVER, settings, sleep)
    assistance = AssistanceAgent(
        ConversationModel([reply for reply, _ in ASSISTANCE_TURNS]),
        ParserModel([data for _, data in ASSISTANCE_TURNS]),
        HttpActionSender(assistance_client, settings.api_token),
    )

    return {
        "debt": run_conversation("DebtAgent: compromiso de pago", debt, DEBT_TURNS, debt_fake, out),
        "assistance": run_conversation(
            "AssistanceAgent: solicitud de asistencia",
            assistance,
            ASSISTANCE_TURNS,
            assistance_fake,
            out,
        ),
    }


def main() -> None:
    """Punto de entrada: el log y el resumen de los turnos salen juntos y en orden por stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="  [log] %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    run_demo()


if __name__ == "__main__":
    main()
