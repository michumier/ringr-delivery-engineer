# ARQUITECTURA

Organización de las clases, los patrones y las dependencias. Las **reglas de comportamiento** están en `REQUISITOS.md` y `DECISIONES.md` (se citan como «ver AMB-n» o «ver PC-n»); los **tests y el plan de construcción**, en `PLAN.md`.

Código en inglés y docstrings en español (AMB-8). Solo librería estándar (AMB-9).

---

## 0. Glosario

| Término | Qué significa aquí |
|---|---|
| **Template Method** (método plantilla) | La clase base fija el orden de los pasos (`handle_turn`) y las subclases rellenan los huecos. |
| **Strategy** (estrategia) | Objetos intercambiables que hacen lo mismo de formas distintas; quien los usa no sabe cuál le ha tocado. |
| **Decorator** (decorador) | Un objeto que envuelve a otro con la misma interfaz y le añade comportamiento sin modificarlo. |
| **Protocol / DIP** | `typing.Protocol` es una interfaz que se cumple «por tener los métodos». DIP (inversión de dependencias): el código importante depende de interfaces, no de clases concretas. |
| **Puerto / adaptador** | Vocabulario de la arquitectura hexagonal: el **puerto** es la interfaz que el núcleo necesita («enviar una acción»); el **adaptador** es la clase concreta que la cumple hablando con el exterior (aquí, simulado). |
| **DTO** | Objeto solo de datos (`dataclass(frozen=True)`), sin lógica. |
| **StrEnum** | Enumerado de Python 3.11 cuyos valores **son** cadenas: `FieldName.REQUEST == "request"`, así que sirve como clave del dict y como nombre de cabecera. |
| **Raíz de composición** | El único sitio donde se crean y se conectan las piezas. Aquí, `__main__.py`. |

---

## 1. El ciclo de un turno (esquema)

`handle_turn()` no recibe parámetros y devuelve un `TurnResult`. El orden es fijo (ver AMB-11). Entre corchetes, lo que aporta cada agente.

```
handle_turn()
 1. Responder      conversation_model.answer_user()
 2. Parsear        parser_model.parse_data()
 3. Normalizar     normalize(raw, [fields()])
 4. Decidir        ¿falló un modelo? ¿[should_execute](data)?    → si no toca, NOT_REQUIRED
 5. Duplicados     fingerprint([action_name], data) en el registro → si está, DUPLICATE
 6. Ejecutar       sender.send([action_url], data)                → SENT o FAILED
 7. Devolver       TurnResult
```

Qué pasa en cada fallo y cuándo se usa la respuesta de emergencia: ver AMB-11 y PC-8 en `DECISIONES.md`.

Dentro del paso 6, por capas:

```
HttpActionSender.send(url, data)       construye UNA HttpRequest (con su Idempotency-Key)
 └─ RetryingHttpClient.send(request)    Decorator: repite la misma request si toca (ver AMB-4)
     └─ FakeHttpClient.send(request)    guarda la request y responde lo configurado
```

---

## 2. Clases e interfaces

Agrupadas por subpaquete de `src/ringr_agents/`, según la estructura decidida en CARP-1 (sección 6).

### 2.1 `domain/`: lo propio del negocio

No importa nada de otros paquetes del proyecto; todos los demás lo pueden usar.

**Enumerados** (`domain/enums.py`, ENUM-1). Todos son `StrEnum`, para que su valor sea la cadena que exige el enunciado o que sale en el log.

| Enumerado | Valores | Para qué |
|---|---|---|
| `ActionStatus` | `NOT_REQUIRED`, `DUPLICATE`, `SENT`, `FAILED` | Qué pasó con la acción en el turno (AMB-5). |
| `TurnError` | `CONVERSATION_FAILED`, `PARSER_FAILED`, `SEND_FAILED` | Qué falló en el turno. Si falla un modelo, el estado es `NOT_REQUIRED` y el `TurnError` dice por qué. |
| `FieldName` | `COMMITMENT_DATE = "commitment_date"`, `COMMITTED_AMOUNT = "committed_amount"`, `REQUEST = "request"` | Nombres de los campos: claves del dict del parser, cabeceras y body. |
| `ActionName` | `REGISTER_COMMITMENT` (deuda), `REGISTER_REQUEST` (asistencia) | Nombre de la acción, para la huella de duplicados y el log. |

**`EMERGENCY_REPLY`** (`domain/constants.py`, ENUM-1): constante con la respuesta de emergencia (ver AMB-11).

**Resultados** (`domain/results.py`, CARP-1): los dos DTO que salen hacia fuera.
```python
@dataclass(frozen=True)
class SendResult:
    ok: bool
    attempts: int
    status_code: int | None                  # None si no hubo respuesta (error de transporte)
    idempotency_key: str                     # para enlazar el turno con la request en el log

@dataclass(frozen=True)
class TurnResult:
    reply: str
    data: Mapping[str, object | None]       # normalizados; claves = valores de FieldName
    action_status: ActionStatus
    warnings: tuple[str, ...] = ()           # datos descartados (AMB-2)
    errors: tuple[TurnError, ...] = ()
    send_result: SendResult | None = None    # detalle del envío (intentos incluidos), si lo hubo
```
`SendResult` ya **no guarda la `HttpRequest`**: guarda solo los datos que necesita quien lee el resultado, todos de tipos simples. Así el dominio no depende de `infrastructure/http/`, y quien quiera ver la request completa (los tests) la mira en `FakeHttpClient.requests`.

**`ActionSender` (Protocol)** (`domain/ports.py`): lo único que el agente sabe de «enviar» (DIP).
```python
class ActionSender(Protocol):
    def send(self, url: str, data: Mapping[str, object | None]) -> SendResult: ...
```
Vive en el dominio porque es la interfaz que **usa** el agente y su firma solo tiene tipos del dominio; así `agents/` no importa nada de `infrastructure/http/`.

**Control de duplicados** (`domain/dedup.py`, PC-5): pieza propia que usa `BaseAgent` y que se puede inyectar.
```python
Fingerprint = tuple[str, tuple[tuple[str, object], ...]]
def fingerprint(action_name: str, data: Mapping[str, object | None]) -> Fingerprint: ...

class SentActionRegistry:
    def was_sent(self, fp: Fingerprint) -> bool: ...
    def mark_sent(self, fp: Fingerprint) -> None: ...
```
Una instancia por agente, es decir, por conversación. La huella se calcula con los datos ya normalizados.

**Limpieza de campos** (`domain/fields/`, Strategy, PC-3).

**`FieldNormalizer` (Protocol)**: «algo que sabe limpiar un campo».
```python
class FieldNormalizer(Protocol):
    def normalize(self, raw: object) -> object | None: ...   # lanza InvalidFieldError
```

| Estrategia | Salida | Nota de diseño |
|---|---|---|
| `TextField()` | `str` o `None` | |
| `DateField(today: Callable[[], date] = date.today)` | `str` ISO | «hoy» se inyecta para poder probar el borde (PC-4) |
| `AmountField()` | `float` con 2 decimales | redondeo con `Decimal` (PC-11) |

Las reglas concretas de cada uno: ver AMB-2 y AMB-3.

**`normalize(raw, fields) -> Normalized`**: recorre el esquema de un agente y aplica a cada campo su estrategia. No conoce ningún tipo concreto.
```python
@dataclass(frozen=True)
class Normalized:
    data: dict[str, object | None]   # solo las claves que declara el agente
    warnings: tuple[str, ...]

def normalize(raw: Mapping[str, Any], fields: Mapping[str, FieldNormalizer]) -> Normalized: ...
```
**`InvalidFieldError(ValueError)`**: el valor no se puede normalizar; lleva el motivo.

### 2.2 `agents/`: los agentes (Template Method, PC-1)

La capa de aplicación: orquesta el dominio y llama a los puertos. Una carpeta por agente (CARP-1).

**`BaseAgent` (ABC)** (`agents/base_agent.py`): orquesta el turno en orden fijo. Hace todo el «cómo» (orden, fallos, respuesta de emergencia, duplicados, envío, resultado) y no sabe nada de cobros ni de atención. **Sin datos entre turnos**: lo único que recuerda es el registro de duplicados (ver AMB-12).
```python
class BaseAgent(ABC):
    action_name: ClassVar[str]           # un valor de ActionName
    action_url: ClassVar[str]            # la URL vive en el agente (PC-10)

    def __init__(self, conversation_model: ConversationModel, parser_model: ParserModel,
                 sender: ActionSender, registry: SentActionRegistry | None = None) -> None: ...

    def handle_turn(self) -> TurnResult: ...        # la plantilla: no se sobrescribe
    # Cada paso vive en un método privado pequeño: _answer, _parse y _send (SOLID-1).

    @abstractmethod
    def fields(self) -> Mapping[str, FieldNormalizer]: ...                   # PC-3
    @abstractmethod
    def should_execute(self, data: Mapping[str, object | None]) -> bool: ...  # PC-2
```

**`DebtAgent`** (`agents/debt/agent.py`) y **`AssistanceAgent`** (`agents/assistance/agent.py`): declaran solo el «qué» (unas 15-20 líneas cada uno).

| | `DebtAgent` | `AssistanceAgent` |
|---|---|---|
| `action_name` | `ActionName.REGISTER_COMMITMENT` | `ActionName.REGISTER_REQUEST` |
| `action_url` | `https://api.ringr.debt/v1/commitment` | `https://api.ringr.assistance/v1/request` |
| `fields()` | `{COMMITMENT_DATE: DateField(today), COMMITTED_AMOUNT: AmountField()}` | `{REQUEST: TextField()}` |
| `should_execute` | los dos campos con valor (RF-8) | `request` con valor (RF-10) |
| Extra | recibe `today` y se lo pasa a `DateField` (PC-4) | |

Las firmas usan `str` y no `FieldName` / `ActionName` (ENUM-2): como un `StrEnum` es una cadena, los agentes reales usan los enumerados y un agente de prueba definido en un test puede usar cadenas sin tocar `src/` (CA-13).

### 2.3 `infrastructure/`: lo externo (aquí, simulado)

#### `infrastructure/models/`: modelos simulados

**`ConversationModel`** y **`ParserModel`**: cada uno recibe un guion al crearse y en cada llamada devuelve el siguiente elemento; si el elemento es una excepción, la lanza (así se simulan los fallos sin mocks). Ver AMB-6.
```python
class ConversationModel:
    def __init__(self, script: Sequence[str | Exception]) -> None: ...
    def answer_user(self) -> str: ...

class ParserModel:
    def __init__(self, script: Sequence[dict[str, Any] | Exception]) -> None: ...
    def parse_data(self) -> dict[str, Any]: ...      # devuelve una copia
```
**`ScriptExhaustedError`**: se lanza al agotarse el guion; `handle_turn` no la captura (ver PC-8.3).

Sin interfaz común ni subclases: el enunciado dice que no hacen falta. Por eso son la única pieza de `infrastructure/` que `agents/` importa directamente (para las anotaciones de tipo de `BaseAgent` y para reconocer `ScriptExhaustedError`).

#### `infrastructure/http/`: envío y HTTP simulado

**`HttpActionSender`** (`http/sender.py`): cumple `ActionSender`. Construye la request una sola vez y se la da a su `HttpClient`. No reintenta y nunca lanza: un error de transporte o cualquier otro error del cliente acaba en `ok=False` (SEND-1).
```python
class HttpActionSender:
    def __init__(self, client: HttpClient, token: str,
                 new_idempotency_key: Callable[[], str] = lambda: str(uuid.uuid4())) -> None: ...
    def send(self, url: str, data: Mapping[str, object | None]) -> SendResult: ...
    def build_request(self, url: str, data: Mapping[str, object | None], key: str) -> HttpRequest: ...
```

La request que construye:

| Parte | Valor | Ver |
|---|---|---|
| Método y URL | `POST` a la `action_url` del agente | RF-8, RF-10 |
| `Authorization` | `Bearer <token>` (el token llega desde `Settings`) | RF-12, PC-10 |
| `Content-Type` | `application/json` | AMB-7 |
| `Idempotency-Key` | UUID por envío, el mismo en sus reintentos | AMB-4, PC-6 |
| Cabeceras del parser | una por campo no `None`, con el nombre de `FieldName` y el valor codificado | AMB-7, PC-12 |
| Body | JSON con los campos normalizados no nulos | AMB-10 |

Las cabeceras fijas se escriben después de las del parser, para que un campo no pueda pisarlas.

**`HttpRequest`** y **`HttpResponse`** (`http/client.py`; DTO; `HttpResponse.attempts: int = 1`, para que el número de intentos viaje con la respuesta sin cambiar la interfaz). **`TransportError`**: timeout o corte; también lleva `attempts`.

**`HttpClient` (Protocol)** (`http/client.py`): `send(request: HttpRequest) -> HttpResponse`. Vive junto a sus implementaciones porque solo lo usan piezas de `http/` (`HttpActionSender` y `RetryingHttpClient`) y su firma usa `HttpRequest`, un detalle de HTTP que el dominio no necesita.

**`FakeHttpClient`** (`http/fake_client.py`): la integración simulada del enunciado. Guarda cada request en `requests` y responde según una lista configurable (`[503, 200]`, un `TransportError`...); por defecto, 200. Vive en `src/` porque **es** la integración pedida.

**`RetryingHttpClient`** (`http/retry.py`; Decorator, PC-7.1): cumple `HttpClient` y envuelve a otro `HttpClient` para añadirle los reintentos, sin modificarlo.
```python
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.2
    sleep: Callable[[float], None] = time.sleep

class RetryingHttpClient:
    def __init__(self, inner: HttpClient, policy: RetryPolicy | None = None) -> None: ...  # None → RetryPolicy()
    def send(self, request: HttpRequest) -> HttpResponse: ...
```
Solo lo nombra la raíz de composición; ni el agente ni `HttpActionSender` saben que existe. Qué se reintenta: ver AMB-4 y PC-7.2.

#### `infrastructure/config.py`

**`Settings`** (PC-10): DTO con lo que cambia entre entornos (`api_token`, `max_attempts`, `base_delay`) y `Settings.from_env()`, que lo lee de variables de entorno con valores por defecto. Solo lo usa la raíz de composición.

### 2.4 Arranque

**`__main__.py`**: la raíz de composición y la demo (`python -m ringr_agents`). Monta `Settings` → `FakeHttpClient` → `RetryingHttpClient` → `HttpActionSender` → modelos con guion → agentes, y ejecuta unos turnos. Es el único archivo que conoce a la vez los agentes y los adaptadores concretos.

---

## 3. Patrones y principios: dónde exactamente

| Patrón / principio | Dónde | Por qué hace falta aquí |
|---|---|---|
| **Template Method** | `agents/base_agent.py`: `handle_turn` y sus huecos `fields()`, `should_execute()`, `action_name`, `action_url` | El orden del turno es igual para todos los agentes: se escribe una vez. |
| **Strategy** | `domain/fields/`: `FieldNormalizer` con `TextField`, `DateField`, `AmountField`; los usa `normalize` | Cada agente combina estrategias distintas y un tipo de dato nuevo es una clase nueva, sin tocar `normalize`. |
| **Decorator** | `infrastructure/http/retry.py`: `RetryingHttpClient` envolviendo un `HttpClient` | Añade los reintentos sin tocar `FakeHttpClient`, `HttpActionSender`, `handle_turn` ni los agentes. |
| **Protocol / DIP (puertos)** | `ActionSender` en `domain/ports.py` (lo usa `BaseAgent`); `HttpClient` en `infrastructure/http/client.py` (lo usan `HttpActionSender` y `RetryingHttpClient`); `FieldNormalizer` en `domain/fields/base.py` (lo usa `normalize`) | Quien usa la pieza no sabe cuál le ha tocado: en los tests se le da un fake y en producción se cambia sin tocar a quien la usa. |
| **DTO** | `TurnResult`, `SendResult` (`domain/results.py`), `Normalized`, `HttpRequest`, `HttpResponse`, `RetryPolicy`, `Settings` | Transportan datos sin estado modificable; se comparan fácil en los tests. |
| **Enumerados** | `domain/enums.py` | Cada valor fijo tiene un nombre y un único sitio; una errata (`ActionStatus.SNET`) da error en cuanto se ejecuta, en vez de pasar como una cadena mal escrita. |
| **Inyección de dependencias** | Constructores de `BaseAgent` (modelos, sender, registro), `DebtAgent` (`today`), `HttpActionSender` (cliente, token, generador de claves), `RetryPolicy` (`sleep`) | Todo lo no determinista (fecha, UUID, esperas, red) se fija en los tests (PC-9). |
| **SRP** (responsabilidad única) | Una carpeta por capa y por agente; dentro, un archivo por pieza | Si cambian los reintentos, solo se toca `http/retry.py`; si cambia la request, solo `http/sender.py`. |
| **OCP** (abierto/cerrado) | Agentes, estrategias, Decorator | Se amplía añadiendo clases, sin modificar las que hay (sección 5). |
| **LSP** (sustitución) | Cualquier agente donde se espera `BaseAgent`; `FakeHttpClient` o `RetryingHttpClient` donde se espera `HttpClient` | La demo y los tests llaman a `agent.handle_turn()` igual para todos. |
| **ISP** (interfaces pequeñas) | `ActionSender`, `HttpClient`, `FieldNormalizer`: un método cada uno | Escribir un fake o un Decorator cuesta pocas líneas. |

No se usan, a propósito: fábrica de agentes, Observer para el log (`logging` basta), contenedor de inyección, ni Strategy para cada paso del turno (descartado en PC-1).

---

## 4. Mapa de dependencias

Quién importa a quién («X ──▶ Y»: X importa Y):

```
   __main__.py      ──▶ agents/, infrastructure/, domain/      (raíz de composición: lo monta todo)
   agents/          ──▶ domain/
   agents/          ──▶ infrastructure/models/                  (solo las clases de los modelos)
   infrastructure/  ──▶ domain/
   domain/          ──▶ (nada del proyecto)
```

Quién cumple qué interfaz o hereda de qué clase («A ◁─ B»: B cumple A o hereda de A):

```
   BaseAgent        (agents/base_agent.py)              ◁─ DebtAgent, AssistanceAgent
   ActionSender     (domain/ports.py)                   ◁─ HttpActionSender                  (infrastructure/http/sender.py)
   HttpClient       (infrastructure/http/client.py)     ◁─ FakeHttpClient, RetryingHttpClient (este envuelve otro HttpClient)
   FieldNormalizer  (domain/fields/base.py)             ◁─ TextField, DateField, AmountField
```

**Regla de dependencias:** `domain/` no importa nada del proyecto; `agents/` importa `domain/` y las interfaces (más las clases de los modelos, que el enunciado da sin interfaz); `infrastructure/` implementa esas interfaces e importa `domain/`. Nadie conoce a los agentes salvo `__main__.py`.

### 4.1 Relación con la arquitectura hexagonal

El diseño sigue la idea hexagonal sin su vocabulario completo. Las interfaces `Protocol` hacen de **puertos**: `ActionSender` (el que usa el agente) y `HttpClient` (el que usa el envío). `HttpActionSender`, `FakeHttpClient` y `RetryingHttpClient` hacen de **adaptadores**. Los modelos simulados también son adaptadores, aunque sin `Protocol` propio, porque el enunciado no lo pide: su «puerto» son los métodos `answer_user` y `parse_data`, y cualquier clase que los tenga sirve. Pasar a un cliente HTTP real o a un LLM real es cambiar de adaptador en `__main__.py`, sin tocar `domain/` ni `agents/`.

Aquí no hay **controller** ni **endpoint** porque el sistema no recibe peticiones de nadie: solo las envía. En hexagonal sería un proyecto con adaptadores de salida (HTTP, modelos) y sin adaptadores de entrada; quien «entra» es quien llama a `handle_turn()`: la demo (`__main__.py`) o los tests.

---

## 5. Extensibilidad

| Añadir... | Archivos que se tocan | Qué no se toca |
|---|---|---|
| **(a) Un agente** | `agents/<nuevo>/agent.py` y su `__init__.py` (subclase con sus 4 huecos); una línea en `agents/__init__.py`; si se quiere, sus nombres en `domain/enums.py` (no es obligatorio, ENUM-2); sus tests en `tests/agents/test_<nuevo>_agent.py`. | `BaseAgent`, los otros agentes, el envío, los reintentos, los duplicados. |
| **(b) Una acción con un tipo de dato nuevo** (p. ej. teléfono) | Una estrategia nueva en `domain/fields/normalizers.py` y el agente que la declara. | `normalize`, `BaseAgent`. |
| **(c) Una integración nueva** | Si es otro cliente HTTP: una clase que cumpla `HttpClient` en `infrastructure/http/` (gana los reintentos al envolverla). Si no es HTTP (una cola): una clase que cumpla `ActionSender` en una carpeta nueva de `infrastructure/`. En los dos casos, el montaje en `__main__.py`. | `domain/`, los agentes, `handle_turn`, `HttpActionSender`. |

Límite conocido: cada agente tiene **una** acción. Un agente con dos obligaría a tocar `BaseAgent`; no se hace porque ningún requisito lo pide.

---

## 6. Estructura de carpetas (decidida, CARP-1)

Intermedia entre capas y funcionalidad: `domain/` (lo propio del negocio), `agents/` (una carpeta por agente) e `infrastructure/` (lo externo, aquí simulado). La regla de dependencias está en la sección 4.

```
entrega/
├── pyproject.toml                  # Python >= 3.11; pytest y ruff (desarrollo) y su configuración
├── README.md                       # qué hace, cómo se ejecuta y por qué está hecho así
├── .gitignore                      # .venv, cachés y notas/ (no se entrega)
├── .github/workflows/ci.yml        # ruff + pytest en cada PR (FLU-1)
├── CLAUDE.md                       # flujo de trabajo con IA (FLU-2)
├── .claude/agents/                 # los agentes de ese flujo (FLU-2)
├── docs/
│   ├── enunciado.pdf               # enunciado de la prueba
│   ├── REQUISITOS.md               # requisitos y ambigüedades resueltas
│   ├── DECISIONES.md               # decisiones de Miguel y su porqué
│   ├── ARQUITECTURA.md             # este documento
│   └── PLAN.md                     # estrategia de tests y plan de construcción
├── src/ringr_agents/
│   ├── __init__.py                 # solo el docstring del paquete
│   ├── __main__.py                 # raíz de composición y demo
│   ├── domain/                     # lo propio del negocio; no depende de nada
│   │   ├── enums.py                # ActionStatus, TurnError, FieldName, ActionName (StrEnum)
│   │   ├── constants.py            # EMERGENCY_REPLY
│   │   ├── results.py              # TurnResult, SendResult (DTO)
│   │   ├── ports.py                # ActionSender (Protocol)
│   │   ├── dedup.py                # fingerprint, SentActionRegistry
│   │   └── fields/
│   │       ├── base.py             # FieldNormalizer, InvalidFieldError
│   │       ├── normalizers.py      # TextField, DateField, AmountField
│   │       └── normalize.py        # Normalized, normalize
│   ├── agents/                     # capa de aplicación, una carpeta por agente
│   │   ├── base_agent.py           # BaseAgent (Template Method, handle_turn)
│   │   ├── debt/
│   │   │   └── agent.py            # DebtAgent
│   │   └── assistance/
│   │       └── agent.py            # AssistanceAgent
│   └── infrastructure/             # lo externo (aquí simulado)
│       ├── config.py               # Settings y from_env()
│       ├── models/
│       │   ├── conversation.py     # ConversationModel
│       │   ├── parser.py           # ParserModel
│       │   └── errors.py           # ScriptExhaustedError
│       └── http/
│           ├── client.py           # HttpRequest, HttpResponse, TransportError, HttpClient (Protocol)
│           ├── fake_client.py      # FakeHttpClient
│           ├── retry.py            # RetryPolicy, RetryingHttpClient
│           └── sender.py           # HttpActionSender
└── tests/                          # misma estructura que src/ringr_agents/
    ├── conftest.py                 # fixtures comunes y bloqueo de red (CA-14)
    ├── test_skeleton.py            # todos los módulos se importan; la red está bloqueada
    ├── test_main.py                # la demo: sus 8 escenarios, el log y la salida
    ├── domain/
    │   ├── test_enums.py
    │   ├── test_results.py
    │   ├── test_dedup.py
    │   └── fields/
    │       ├── test_normalizers.py
    │       └── test_normalize.py
    ├── agents/
    │   ├── conftest.py             # fixtures de los agentes (modelos con guion, sender, cliente)
    │   ├── constants.py            # token, Idempotency-Key fija y «hoy» de los tests
    │   ├── test_base_agent.py      # handle_turn con un tercer agente de prueba (CA-13)
    │   ├── test_debt_agent.py
    │   ├── test_assistance_agent.py
    │   ├── test_duplicates.py
    │   ├── test_retries.py         # reintentos de punta a punta
    │   └── test_turn_log.py        # una línea de log por paso, sin datos del cliente
    └── infrastructure/
        ├── test_config.py
        ├── models/test_models.py
        └── http/
            ├── test_fake_client.py
            ├── test_sender.py
            └── test_retry.py
```

Cada subpaquete lleva su `__init__.py`. Los que se usan desde fuera (`agents`, `domain.fields`, `infrastructure.http` e `infrastructure.models`) reexportan sus clases públicas (`from ringr_agents.domain.fields import DateField`); el paquete raíz, `domain` e `infrastructure` solo tienen el docstring. Los archivos de test tienen nombres distintos entre carpetas, para que pytest no los confunda.
