# Agentes conversacionales con integración HTTP simulada

Prueba técnica para el puesto de Delivery Engineer en Ringr. El enunciado está en [`docs/enunciado.pdf`](docs/enunciado.pdf).

Dos agentes conversacionales orientados a objetos, `DebtAgent` y `AssistanceAgent`. En cada turno, un agente responde al cliente, extrae información estructurada de la conversación, la valida y normaliza, y decide si ejecuta una acción externa mediante una petición HTTP simulada. La acción solo se ejecuta cuando se cumplen sus condiciones, y nunca se envía dos veces durante la misma conversación.

| Agente | Ejecuta la acción si… | Petición |
|---|---|---|
| `DebtAgent` | hay `commitment_date` (fecha futura o de hoy) **y** `committed_amount` (> 0) | `POST https://api.ringr.debt/v1/commitment` |
| `AssistanceAgent` | hay `request` | `POST https://api.ringr.assistance/v1/request` |

## Cómo se ejecuta

Requiere Python 3.11 o superior. No tiene dependencias de ejecución: solo la librería estándar.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"         # pytest y ruff
```

| Qué | Comando |
|---|---|
| Demo (8 escenarios) | `python -m ringr_agents` |
| Tests | `pytest` |
| Estilo | `ruff check .` y `ruff format --check .` |

El CI (GitHub Actions) ejecuta `ruff` y `pytest` en cada pull request.

**Configuración.** Se lee de variables de entorno; si no están definidas, se usan los valores por defecto.

| Variable | Por defecto | Qué es |
|---|---|---|
| `RINGR_API_TOKEN` | el token de pruebas del enunciado | Token que va en `Authorization: Bearer …` |
| `RINGR_MAX_ATTEMPTS` | `3` | Intentos totales de cada envío |
| `RINGR_RETRY_BASE_DELAY` | `0.2` | Espera antes del primer reintento, en segundos; se dobla en cada reintento |

**La demo** ejecuta 8 conversaciones, cada una con su propio agente y su propio servidor simulado:
- un caso exitoso, sin incidencias;
- los datos que llegan poco a poco;
- un duplicado seguido de una corrección;
- datos inválidos;
- un reintento que salva el envío;
- los reintentos agotados;
- un 400 que no se reintenta;
- un parser que devuelve basura.

Para cada turno muestra el log paso a paso y un resumen, y al final de cada conversación, la última petición construida (con el token oculto).

## Cómo funciona un turno

`handle_turn()` sigue siempre el mismo orden. Lo que va entre corchetes lo aporta cada agente:

```
1. Responder     conversation_model.answer_user()
2. Parsear       parser_model.parse_data()
3. Normalizar    normalize(datos, [fields()])          → lo inválido se descarta con un aviso
4. Decidir       ¿falló un modelo? ¿[should_execute]?   → si no toca: NOT_REQUIRED
5. Duplicados    ¿ya se envió esta acción con estos datos? → si es así: DUPLICATE
6. Enviar        POST a [action_url], con reintentos    → SENT o FAILED
7. Devolver      TurnResult
```

`TurnResult` es un objeto inmutable con la respuesta al cliente, los datos normalizados, el estado de la acción (`NOT_REQUIRED`, `DUPLICATE`, `SENT` o `FAILED`), los avisos, los errores y el detalle del envío (código e intentos).

La petición lleva:
- `Authorization: Bearer <token>`;
- `Content-Type: application/json`;
- una `Idempotency-Key` por envío, la misma en todos sus reintentos;
- una cabecera por cada dato extraído (con los valores normalizados y codificados);
- un cuerpo JSON con esos mismos datos.

## Diseño

| Patrón o principio | Dónde | Para qué |
|---|---|---|
| **Template Method** | `BaseAgent.handle_turn` (`@final`) | El orden del turno es común y no se puede alterar; cada agente solo declara sus campos, su regla `should_execute`, su URL y el nombre de su acción. |
| **Strategy** | `domain/fields/` (`TextField`, `DateField`, `AmountField`) | Cada tipo de dato tiene su propia validación y normalización; un agente declara sus campos sin escribir lógica de validación. |
| **Decorator** | `RetryingHttpClient` | Añade la política de reintentos envolviendo al cliente HTTP, sin modificarlo. Se incorporó sin tocar los agentes ni `handle_turn`. |
| **Inversión de dependencias** | `ActionSender` (`domain/ports.py`) y `HttpClient` | Los agentes dependen de interfaces, no de la implementación HTTP. |
| **Inyección de dependencias** | Constructores; `__main__.py` como raíz de composición | Modelos, sender, registro de duplicados, reloj, generador de claves y espera se inyectan. Así todo es testeable sin red ni esperas reales. |
| **Responsabilidad única** | Un archivo por pieza; `handle_turn` dividido en métodos pequeños | Cada cambio se localiza en un único sitio. |

El código se organiza en tres capas, con la regla de dependencias `agents → domain ← infrastructure`:

```
src/ringr_agents/
├── __main__.py        # raíz de composición y demo
├── domain/            # reglas y tipos propios; no depende de nada
│   ├── enums.py, constants.py, results.py, ports.py, dedup.py
│   └── fields/        # validación y normalización (Strategy)
├── agents/            # BaseAgent (Template Method) y una carpeta por agente
│   ├── debt/
│   └── assistance/
└── infrastructure/    # lo externo, aquí simulado
    ├── config.py      # Settings desde variables de entorno
    ├── models/        # ConversationModel y ParserModel con guion
    └── http/          # request, cliente falso, reintentos (Decorator) y sender
```

El árbol completo, con los tests, está en [`ARQUITECTURA.md`](docs/ARQUITECTURA.md#6-estructura-de-carpetas-decidida-carp-1).

### Decisiones principales

El enunciado deja abiertos varios puntos. Estas son las decisiones más relevantes; cada una, con su motivo y las alternativas descartadas, está en [`docs/DECISIONES.md`](docs/DECISIONES.md).

- **Duplicado = la misma acción con exactamente los mismos datos normalizados en la conversación** (AMB-1). `"150,50"` y `150.5` son el mismo compromiso; cambiar el importe es una corrección y se envía.
- **Datos inválidos: se descartan con un aviso y el turno continúa** (AMB-2, AMB-3). Se rechazan, por ejemplo, un importe ≤ 0, una fecha pasada o un formato ambiguo como `"1.500,50"`.
- **El cliente nunca se queda sin respuesta** (AMB-11, PC-8, SEND-1). Si falla un modelo o el envío, recibe una respuesta de emergencia fija y no se le confirma nada que no se haya registrado.
- **Reintentos** (AMB-4, PC-7.1): 3 intentos, solo ante 5xx o errores de transporte, con espera creciente y la misma `Idempotency-Key`, para que el servidor pueda descartar repeticiones. Un envío fallido no se marca como enviado: si el cliente lo repite, se reenvía.
- **Configuración fuera del código** (PC-10): el token y los reintentos se leen del entorno; las URL son propias de cada agente.
- **El log describe el turno paso a paso** (LOGS) sin registrar datos del cliente: solo los nombres de los campos, los códigos y los intentos.

## Comportamiento ante fallos

| Situación | Estado | Respuesta al cliente | ¿Se envía? |
|---|---|---|---|
| Faltan datos (sin aviso) o no son válidos (con aviso) | `NOT_REQUIRED` | la del modelo | No |
| Falla `answer_user` o `parse_data` | `NOT_REQUIRED` + `TurnError` | de emergencia | No |
| Mismos datos que un envío anterior | `DUPLICATE` | la del modelo | No |
| 5xx o error de transporte | se reintenta | — | Sí, hasta 3 veces |
| Se agotan los intentos, 4xx o error inesperado del cliente HTTP | `FAILED` + `SEND_FAILED` | de emergencia | Sí, y se podrá reenviar en otro turno |

## Cómo añadir un agente

Basta con una subclase. No hay que tocar `BaseAgent`, ni el envío, ni los reintentos, ni los duplicados:

```python
from collections.abc import Mapping
from types import MappingProxyType
from typing import ClassVar

from ringr_agents.agents import BaseAgent
from ringr_agents.domain.fields import FieldNormalizer, TextField


class ReminderAgent(BaseAgent):
    action_name = "register_reminder"
    action_url = "https://api.ringr.test/v1/reminder"

    _fields: ClassVar[Mapping[str, FieldNormalizer]] = MappingProxyType({"note": TextField()})

    def fields(self) -> Mapping[str, FieldNormalizer]:
        return self._fields

    def should_execute(self, data: Mapping[str, object | None]) -> bool:
        return data.get("note") is not None
```

Los tests de `BaseAgent` usan precisamente un agente así, definido en el propio test (`tests/agents/test_base_agent.py`). Un tipo de dato nuevo es una estrategia más en `domain/fields/normalizers.py`. Una integración nueva es una clase que cumpla `HttpClient` (y hereda los reintentos al envolverla) o `ActionSender`.

## Tests

Tests con `pytest`, organizados con la misma estructura que `src/`. Cada test cita en su docstring el requisito o la decisión que comprueba (`RF-n`, `CA-n`, `AMB-n`…).

- **Fakes en lugar de mocks.** Los modelos simulados y el `FakeHttpClient` son implementaciones reales y sencillas. Los tests comprueban resultados (la petición construida, el estado del turno) y no a quién se ha llamado.
- **La red está bloqueada** en todos los tests (`tests/conftest.py`): ninguno puede hacer una llamada real.
- **Sin esperas reales:** el reloj y la espera de los reintentos se inyectan.

## Límites conocidos

- **A → B → A.** Si el cliente se compromete a A, cambia a B y vuelve a A, la vuelta a A cuenta como duplicado y no se reenvía, porque el registro guarda todo lo enviado en la conversación (PC-5.2). Cubrirlo exigiría saber cuál es el compromiso vigente en el destino.
- **El registro de duplicados está en memoria**, uno por agente (es decir, por conversación). En producción sería persistente, con la misma interfaz.
- **Una acción por agente.** Un agente con dos acciones obligaría a cambiar `BaseAgent`; ningún requisito lo pide.
- **`handle_turn()` no recibe el mensaje del cliente** (AMB-5), y `BaseAgent` importa directamente los modelos simulados, sin interfaz (PORT-1). Es lo que plantea el enunciado. Con modelos reales, `handle_turn` recibiría el mensaje y los modelos tendrían una interfaz; el resto del diseño no cambia.
- **Cualquier 2xx cuenta como éxito.** Un `202 Accepted` (recibido, pero pendiente de procesar) se trata igual que un `200`; con un destino real habría que confirmar qué código significa «registrado».

## Flujo de trabajo con IA

El desarrollo se ha hecho con Claude Code, con Claude Opus 5.5 como modelo de la sesión principal, y con un flujo por fases y agentes especializados ([`CLAUDE.md`](CLAUDE.md) y [`.claude/agents/`](.claude/agents/)). Las decisiones técnicas las he tomado yo: la IA las presentaba como preguntas con alternativas, y cada decisión quedó registrada con su porqué en `DECISIONES.md`.

| Agente | Modelo | Qué ha hecho |
|---|---|---|
| `analista-requisitos` | Claude Sonnet | Convirtió el enunciado en requisitos, criterios de aceptación y ambigüedades con opciones. |
| `arquitecto` | Claude Opus | Propuso la arquitectura y el plan de construcción, con alternativas en cada punto clave. |
| `constructor` | Claude Sonnet | Implementó cada paso del plan aprobado, sin tomar decisiones de diseño. |
| `tester` | Claude Sonnet | Escribió los tests a partir de los criterios de aceptación y las decisiones. |
| `verificador` | Claude Haiku | Hizo las comprobaciones mecánicas: estilo, tests, trazabilidad, secretos y restos. |
| `revisor` | Claude Opus | Revisó cada PR y el proyecto entero como lo haría el evaluador, con veredicto APTO / NECESITA CAMBIOS. |

1. **Requisitos:** un agente analista extrajo del enunciado los requisitos, los criterios de aceptación y las ambigüedades, con opciones para cada una ([`REQUISITOS.md`](docs/REQUISITOS.md)).
2. **Arquitectura:** un agente arquitecto propuso el diseño con alternativas en los puntos clave ([`ARQUITECTURA.md`](docs/ARQUITECTURA.md), [`PLAN.md`](docs/PLAN.md)).
3. **Construcción por pasos:** cada paso en su rama y su pull request hacia `main`, con CI. Un agente revisor comentaba cada PR, yo respondía qué aceptaba y por qué, y se fusionaba con el CI en verde. El historial de PR del repositorio recoge ese proceso.
4. **Verificación:** comprobaciones automáticas y revisión del proyecto entero antes de la entrega.

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/REQUISITOS.md`](docs/REQUISITOS.md) | Requisitos, criterios de aceptación y ambigüedades con sus opciones |
| [`docs/DECISIONES.md`](docs/DECISIONES.md) | Registro de decisiones, con su motivo y las alternativas descartadas |
| [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) | Clases, patrones, dependencias, extensibilidad y estructura de carpetas |
| [`docs/PLAN.md`](docs/PLAN.md) | Estrategia de tests y plan de construcción |
