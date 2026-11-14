# ARQUITECTURA

Propuesta de diseño para la prueba técnica. Parte de `REQUISITOS.md` y de las decisiones de `DECISIONES.md` (que mandan). Los puntos marcados como **PC-n** son decisiones de diseño **pendientes de Miguel**: cada uno trae opciones, pros y contras y una recomendación, pero nada está decidido hasta que él elija.

Criterio general: **simple antes que sofisticado**. Cada clase existe porque la pide un requisito o una decisión de Miguel; al lado de cada una se dice cuál.

---

## 0. Glosario mínimo

| Término | Qué significa aquí |
|---|---|
| **Método plantilla (Template Method)** | La clase base fija el orden de los pasos de un algoritmo (`handle_turn`) y las subclases solo rellenan los huecos (qué campos, qué URL, cuándo actuar). |
| **Estrategia (Strategy)** | Un objeto intercambiable que encapsula «una forma de hacer algo» (p. ej. cómo se normaliza una fecha); quien lo usa no sabe cuál le ha tocado. |
| **Protocol** | Interfaz de Python (`typing.Protocol`) que se cumple por «tener los métodos», sin heredar. Sirve para que el agente dependa de «algo que sabe enviar» y no de una clase concreta. |
| **DTO** | Objeto solo de datos (aquí, `dataclass` inmutable), sin lógica. Sirve para devolver resultados. |
| **Inyección de dependencias** | El objeto recibe sus colaboradores en el constructor en lugar de crearlos él; así en los tests se le pasan versiones falsas. |
| **Fake** | Doble de pruebas con comportamiento real pero simplificado (p. ej. un cliente HTTP que guarda las peticiones en una lista). **Mock**: doble que además comprueba cómo se le llamó. |
| **Huella (fingerprint)** | Valor que identifica «esta acción con estos datos»; dos envíos con la misma huella son duplicados. |
| **Idempotency-Key** | Cabecera con un identificador único del envío; si el servidor recibe dos veces la misma clave, sabe que es el mismo envío y no lo registra dos veces. |
| **Raíz de composición** | El único sitio del programa donde se crean y se conectan las piezas (agente + modelos + cliente HTTP + configuración). |

---

## 1. Visión general: el ciclo de un turno

`handle_turn()` no recibe parámetros (AMB-5) y devuelve un `TurnResult`. El orden es el del enunciado (AMB-11). Los nombres entre corchetes son los huecos que rellena cada agente.

```
handle_turn()
│
├─ 1. RESPONDER      reply = conversation_model.answer_user()
│                    └─ si lanza error → reply = EMERGENCY_REPLY, se anota el error (AMB-11)
│
├─ 2. PARSEAR        raw = parser_model.parse_data()
│                    └─ si lanza error o no es dict → reply = EMERGENCY_REPLY,
│                       se anota el error, NO se actúa → return TurnResult(NOT_REQUIRED)
│
├─ 3. VALIDAR Y      data, warnings = normalize(raw, [fields] del agente)
│    NORMALIZAR      · clave que falta → None · clave que sobra → se ignora
│                    · valor inválido → None + aviso (log + resultado)       (AMB-2, AMB-3)
│
├─ 4. DECIDIR        if not [should_execute](data) → return TurnResult(NOT_REQUIRED)
│                                                                           (RF-8, RF-10, RF-16)
├─ 5. DUPLICADOS     fp = fingerprint([action_name], data)
│                    if registry.was_sent(fp) → return TurnResult(DUPLICATE) (RF-17, AMB-1)
│
├─ 6. EJECUTAR       send = sender.send([action_url], data)
│                    · construye UNA request: URL + Bearer + Content-Type
│                      + Idempotency-Key + cabeceras del parser + body JSON  (RF-11..13, AMB-7, AMB-10)
│                    · hasta 3 intentos, solo reintenta 5xx, espera creciente (AMB-4)
│                    · si SENT  → registry.mark_sent(fp)
│                    · si FAILED → no se marca (podrá reintentarse otro turno)
│                    · (PC-8: qué respuesta recibe el cliente si FAILED)
│
└─ 7. DEVOLVER       TurnResult(reply, data, action_status, warnings, errors, send_result)
```

Puntos importantes del ciclo:

- **El agente nunca lanza excepción hacia fuera por culpa de los modelos, de los datos o del HTTP**: todo acaba en el `TurnResult` y en el log (AMB-2, AMB-4, AMB-11). La única excepción que sí sale es un error de programación (bug), que no se debe tapar.
- **El agente no guarda datos entre turnos** (AMB-12). Lo único que recuerda es qué acciones se enviaron (para los duplicados).
- **Al agotarse el guion** de un modelo simulado, el modelo lanza `ScriptExhaustedError` (AMB-6). Ver PC-8 sobre si esa excepción se trata como «fallo del modelo» o se deja salir (recomendación: dejarla salir, porque es un test mal preparado, no un fallo de producción).

---

## 2. Clases e interfaces

Paquete: `src/ringr_agents/`. Código en inglés, docstrings y comentarios en español (AMB-8). Solo librería estándar (AMB-9).

### 2.1 Modelos simulados — `models.py`

**`ConversationModel`** — Devuelve, en cada llamada, la siguiente respuesta de un guion fijado al crearlo (RF-2, RF-15, AMB-6).
```python
class ConversationModel:
    def __init__(self, script: Sequence[str]) -> None: ...
    def answer_user(self) -> str: ...          # lanza ScriptExhaustedError si se acaba
```

**`ParserModel`** — Igual, pero con un guion de `dict` (RF-3, RF-15, AMB-6).
```python
class ParserModel:
    def __init__(self, script: Sequence[dict[str, Any]]) -> None: ...
    def parse_data(self) -> dict[str, Any]:     # devuelve una COPIA del dict del guion
        ...
```

**`ScriptExhaustedError(Exception)`** — Error propio al agotarse el guion.

- Sin subclases ni interfaz común: el enunciado dice que no hacen falta (RF-15).
- Para simular un fallo del modelo en un turno concreto, el guion admite una excepción en lugar de un valor (`[{"request": None}, RuntimeError("caído")]`): si el elemento es una excepción, se lanza. Así se prueban AMB-11 sin mocks.
- **Quién la usa:** `BaseAgent` (y los tests, que crean los guiones).

### 2.2 Validación y normalización — `fields.py`

**`FieldNormalizer` (Protocol)** — «Algo que sabe limpiar un campo» (Estrategia).
```python
class FieldNormalizer(Protocol):
    def normalize(self, raw: object) -> object | None: ...   # lanza InvalidFieldError
```

**`InvalidFieldError(ValueError)`** — El valor no se puede normalizar; lleva el motivo legible.

Implementaciones (una por tipo de dato, reutilizables entre agentes; AMB-3 forma C):

| Clase | Entrada aceptada | Salida | Reglas (AMB-3) |
|---|---|---|---|
| `TextField()` | `str` | `str` o `None` | `strip()`; vacío → `None`; otro tipo → inválido |
| `DateField(today=...)` | `str` exactamente `yyyy-mm-dd` | `str` ISO | `strip()`; vacío → `None`; formato estricto; fecha real; **fecha < hoy → inválido; hoy vale** |
| `AmountField()` | `int`, `float`, `str` | `float` con 2 decimales | `str`: `strip()`, un solo separador `.` o `,` con 1-2 cifras detrás; lo demás («1.500,50», «1,500») inválido; `bool`, `NaN`, `inf` inválidos; redondeo a céntimos (PC-11); **> 0** |

Ojo para la entrevista: `date.fromisoformat` en Python 3.11 acepta también `"20261201"`, y `strptime("%Y-%m-%d")` acepta `"2026-1-5"`. Para «exactamente `yyyy-mm-dd`» hace falta una comprobación de formato (expresión regular `^\d{4}-\d{2}-\d{2}$`) antes de convertir.

**`normalize(raw, fields) -> Normalized`** — Función que aplica el esquema completo de un agente:
```python
@dataclass(frozen=True)
class Normalized:
    data: dict[str, object | None]   # SOLO las claves declaradas; las que faltan = None
    warnings: tuple[str, ...]         # un aviso por valor descartado

def normalize(raw: Mapping[str, Any], fields: Mapping[str, FieldNormalizer]) -> Normalized: ...
```
- Claves que sobran: se ignoran (y no llegan a cabeceras ni body: AMB-7).
- Valor inválido: `InvalidFieldError` → el campo queda en `None`, se añade aviso y se registra con `logging.warning` (AMB-2).
- **Quién la usa:** `BaseAgent` en el paso 3.

### 2.3 Resultado del turno — `results.py`

```python
class ActionStatus(Enum):
    NOT_REQUIRED = "not_required"   # no se cumplían las condiciones (o falló el parser)
    DUPLICATE    = "duplicate"      # ya se envió esa misma acción en esta conversación
    SENT         = "sent"           # 2xx
    FAILED       = "failed"         # 4xx, o 5xx tras agotar los reintentos

@dataclass(frozen=True)
class TurnResult:                   # DTO (AMB-5)
    reply: str                       # lo que se le dice al cliente
    data: Mapping[str, object | None]  # datos ya normalizados
    action_status: ActionStatus
    warnings: tuple[str, ...] = ()   # datos descartados (AMB-2)
    errors: tuple[str, ...] = ()     # fallos de modelos o del envío (AMB-11, AMB-4)
    send_result: SendResult | None = None   # detalle del envío, si lo hubo
```
- **Quién lo usa:** lo crea `BaseAgent`; lo leen los tests y quien llame al agente.

### 2.4 HTTP simulado — `http.py`

```python
@dataclass(frozen=True)
class HttpRequest:          # DTO: lo que exige RF-11
    method: str              # "POST"
    url: str
    headers: Mapping[str, str]
    body: str                # JSON ya serializado

@dataclass(frozen=True)
class HttpResponse:
    status_code: int

class HttpClient(Protocol):  # «algo que sabe enviar una request»
    def send(self, request: HttpRequest) -> HttpResponse: ...

class FakeHttpClient:        # la integración simulada (RF-11, RF-14, AMB-10)
    def __init__(self, statuses: Sequence[int] = ()) -> None: ...
    # statuses: códigos a devolver en orden (p. ej. [503, 200]); vacío o agotado → 200
    def send(self, request: HttpRequest) -> HttpResponse: ...
    @property
    def requests(self) -> list[HttpRequest]: ...   # todo lo que "se envió"
```
- `FakeHttpClient` vive en `src/` (no en `tests/`) porque **es** la integración simulada que pide el enunciado; no abre ninguna conexión.
- **Quién lo usa:** `HttpActionSender` (y la demo y los tests, que leen `requests`).

### 2.5 Envío de la acción — `sender.py`

**`ActionSender` (Protocol)** — Lo único que el agente sabe de «enviar»:
```python
class ActionSender(Protocol):
    def send(self, url: str, data: Mapping[str, object]) -> SendResult: ...
```

**`SendResult`** (DTO):
```python
@dataclass(frozen=True)
class SendResult:
    ok: bool
    attempts: int
    status_code: int | None
    request: HttpRequest           # la request construida (la misma en todos los intentos)
```

**`RetryPolicy`** (DTO de configuración, AMB-4):
```python
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3                              # intentos en total
    base_delay: float = 0.2                            # segundos; espera = base_delay * 2**(n-1)
    sleep: Callable[[float], None] = time.sleep        # en tests: lambda s: None (o una lista que apunta)
```

**`HttpActionSender`** — Construye la request y la envía con reintentos (implementa `ActionSender`).
```python
class HttpActionSender:
    def __init__(
        self,
        client: HttpClient,
        token: str,
        retry: RetryPolicy = RetryPolicy(),
        new_idempotency_key: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None: ...
    def send(self, url: str, data: Mapping[str, object]) -> SendResult: ...
    def build_request(self, url: str, data: Mapping[str, object], key: str) -> HttpRequest: ...
```

Request que construye (CA-2, CA-4, CA-6):

| Parte | Valor |
|---|---|
| Método | `POST` |
| URL | la del agente (`https://api.ringr.debt/v1/commitment` o `https://api.ringr.assistance/v1/request`) |
| `Authorization` | `Bearer ringr_test_token_9f3a2c1d` (RF-12; el token llega por configuración, PC-10) |
| `Content-Type` | `application/json` (AMB-7) |
| `Idempotency-Key` | un valor por envío, **el mismo en todos sus reintentos** (AMB-4, PC-6) |
| Cabeceras del parser | un header por campo declarado y no `None`, **mismo nombre** (`commitment_date`, `committed_amount`, `request`), valor normalizado pasado a `str` y codificado (PC-12) (RF-13, AMB-7) |
| Body | `json.dumps(data, ensure_ascii=False)` con los campos normalizados no nulos: `{"commitment_date": "2026-12-01", "committed_amount": 150.5}` (AMB-10); el texto original, tildes incluidas, va intacto |

- Las cabeceras fijas (`Authorization`, `Content-Type`, `Idempotency-Key`) se escriben **después** de las del parser, para que un campo nunca pueda pisarlas.
- Reintentos: 2xx → `ok`; 4xx → falla sin reintentar; 5xx → espera y reintenta hasta `max_attempts`. Cada intento y cada fallo dejan una línea de `logging` (AMB-10).
- **Quién lo usa:** `BaseAgent` (a través del Protocol `ActionSender`; no conoce `HttpActionSender`).

### 2.6 Control de duplicados — `dedup.py`

```python
Fingerprint = tuple[str, tuple[tuple[str, object], ...]]

def fingerprint(action_name: str, data: Mapping[str, object]) -> Fingerprint:
    """Huella = nombre de la acción + pares (campo, valor normalizado) ordenados por campo."""

class SentActionRegistry:
    def was_sent(self, fp: Fingerprint) -> bool: ...
    def mark_sent(self, fp: Fingerprint) -> None: ...
```
- La huella usa los datos **ya normalizados**: `" 150,5"` y `150.50` dan la misma huella.
- Ámbito: una instancia de registro por agente = por conversación (AMB-1).
- Solo se marca tras un envío `ok` (AMB-4).
- Comparar contra **todos** los envíos o contra **el último**: PC-5.
- **Quién lo usa:** `BaseAgent`, pasos 5 y 6.

### 2.7 Agentes — `agents/`

**`BaseAgent` (clase abstracta, `agents/base.py`)** — Orquesta el turno en orden fijo (método plantilla). No sabe nada de cobros ni de atención.
```python
EMERGENCY_REPLY = "Ha habido un error, inténtelo más tarde."   # AMB-11 (texto a validar por Miguel)

class BaseAgent(ABC):
    action_name: ClassVar[str]      # p. ej. "register_commitment" (para la huella y el log)
    action_url: ClassVar[str]

    def __init__(
        self,
        conversation_model: ConversationModel,
        parser_model: ParserModel,
        sender: ActionSender,
        registry: SentActionRegistry | None = None,   # por defecto, uno nuevo (conversación nueva)
    ) -> None: ...

    def handle_turn(self) -> TurnResult: ...          # la plantilla: NO se sobrescribe

    @abstractmethod
    def fields(self) -> Mapping[str, FieldNormalizer]: ...   # esquema del agente (PC-3)

    @abstractmethod
    def should_execute(self, data: Mapping[str, object | None]) -> bool: ...   # regla (PC-2)
```

**`DebtAgent(BaseAgent)` (`agents/debt.py`)** — Registra compromisos de pago.
```python
class DebtAgent(BaseAgent):
    action_name = "register_commitment"
    action_url = "https://api.ringr.debt/v1/commitment"

    def __init__(self, ..., today: Callable[[], date] = date.today) -> None: ...   # PC-4
    def fields(self):  {"commitment_date": DateField(today=self._today),
                        "committed_amount": AmountField()}
    def should_execute(self, data):  ambos campos no None          # RF-8
```

**`AssistanceAgent(BaseAgent)` (`agents/assistance.py`)** — Registra solicitudes para agentes humanos.
```python
class AssistanceAgent(BaseAgent):
    action_name = "register_request"
    action_url = "https://api.ringr.assistance/v1/request"
    def fields(self):  {"request": TextField()}
    def should_execute(self, data):  data["request"] is not None   # RF-10
```

Reparto del trabajo: **la base hace todo el «cómo»** (orden, manejo de errores, duplicados, envío, resultado); **cada agente declara solo el «qué»** (campos, regla, URL, nombre de la acción). Cada agente concreto ocupa unas 15-20 líneas.

### 2.8 Configuración y montaje — `config.py`

```python
@dataclass(frozen=True)
class Settings:
    api_token: str = "ringr_test_token_9f3a2c1d"   # token de pruebas del enunciado
    max_attempts: int = 3
    base_delay: float = 0.2

    @classmethod
    def from_env(cls) -> "Settings": ...   # RINGR_API_TOKEN, RINGR_MAX_ATTEMPTS... (PC-10)
```
La demo (`__main__.py`) es la raíz de composición: crea `Settings`, `FakeHttpClient`, `HttpActionSender`, los modelos con un guion de ejemplo y los dos agentes, ejecuta unos turnos y muestra los `TurnResult` y el log. Sirve para el apartado «cómo ejecutar» del README.

### 2.9 Mapa de dependencias

```
DebtAgent ─┐
           ├─▶ BaseAgent ──▶ ConversationModel, ParserModel      (models.py)
AssistanceAgent┘   │    ──▶ normalize + FieldNormalizer          (fields.py)
                   │    ──▶ SentActionRegistry + fingerprint     (dedup.py)
                   │    ──▶ ActionSender (Protocol)              (sender.py)
                   │                 ▲
                   │         HttpActionSender ──▶ HttpClient (Protocol) ◀── FakeHttpClient (http.py)
                   └──▶ TurnResult, ActionStatus                 (results.py)
```
Las flechas van siempre hacia piezas más pequeñas y genéricas; ninguna pieza de abajo conoce a los agentes.

---

## 3. Puntos clave con alternativas

### PC-1. Cómo se reparte el trabajo entre la base y los agentes

- **A. Herencia con método plantilla (Template Method).** `BaseAgent.handle_turn` fija los pasos; `DebtAgent` y `AssistanceAgent` heredan y rellenan `fields()`, `should_execute()`, `action_url`, `action_name`. Los colaboradores (modelos, sender, registro) se inyectan.
  - Pros: refleja literalmente «dos agentes con comportamientos diferenciados» y los nombres del enunciado son clases; el orden del turno está en un único sitio; fácil de explicar.
  - Contras: herencia = acoplamiento a la base; si un agente futuro necesitara otro orden de pasos, habría que tocar la base.
- **B. Composición pura: una sola clase `Agent` configurada con un `AgentSpec`** (campos, regla, URL). `DebtAgent` sería una función o constante que crea el `Agent` con su spec.
  - Pros: sin herencia; añadir un agente es añadir datos.
  - Contras: `DebtAgent`/`AssistanceAgent` dejan de ser clases de verdad (el enunciado los nombra como agentes); la regla de ejecución acaba siendo una lambda; menos «POO» visible, que es un criterio de evaluación.
- **C. Híbrido: A, pero cada paso del turno delegado en objetos estrategia** (un `Validator`, un `ActionPolicy`, un `Deduplicator` por agente).
  - Pros: máxima flexibilidad.
  - Contras: muchas clases para dos agentes de 2 campos; difícil de defender en 2 minutos.
- **Recomendación: A.** Es lo que mejor se explica («la base dice el orden, cada agente dice qué datos y cuándo actuar») y ya combina herencia (para el «qué» de cada agente) con composición (para modelos, envío y duplicados).

**Decisión de Miguel:** ✅ **A**, Template Method (ver `DECISIONES.md`).

### PC-2. Dónde vive la regla «cuándo se ejecuta la acción»

- **A. Método abstracto `should_execute(data)` en cada agente** (una línea cada uno).
  - Pros: la regla del enunciado se lee literalmente en el archivo del agente; un agente futuro puede tener cualquier regla.
  - Contras: dos líneas casi iguales (los dos agentes piden «todos mis campos con valor»).
- **B. Regla genérica en la base: «se ejecuta si todos los campos declarados tienen valor»**, sin método en los agentes.
  - Pros: cero código en los agentes.
  - Contras: la regla queda implícita; el primer agente con un campo opcional obliga a cambiar la base.
- **C. B por defecto + `should_execute` sobrescribible.**
  - Pros: lo mejor de los dos.
  - Contras: dos sitios donde mirar para saber cuándo actúa un agente.
- **Recomendación: A.** Es una de las dos garantías explícitas del enunciado (RF-16): mejor que se vea escrita en cada agente que deducida.

**Decisión de Miguel:** ✅ **A** (ver `DECISIONES.md`).

### PC-3. Cómo se representan los campos declarados (esquema por agente)

- **A. Objetos normalizadores por tipo (`TextField`, `DateField`, `AmountField`) que cumplen el Protocol `FieldNormalizer`;** cada agente devuelve `{"nombre": Normalizador}`.
  - Pros: reutilizables; cada uno se prueba solo; el que necesita configuración (la fecha necesita «hoy») la guarda dentro.
  - Contras: tres clases pequeñas más un Protocol.
- **B. Funciones sueltas (`normalize_date`, `normalize_amount`...) en un diccionario.**
  - Pros: lo más corto.
  - Contras: la fecha necesita «hoy», así que habría que usar `functools.partial` o un cierre; menos «POO».
- **C. Una `dataclass` por agente (`CommitmentData`) que se valida en `__post_init__`.**
  - Pros: tipos explícitos por agente.
  - Contras: lanza excepción al primer campo inválido, y AMB-2 pide descartar campo a campo y seguir; reglas repetidas entre agentes.
- **Recomendación: A.** Encaja con la «forma C» de AMB-3 («cada campo con su propia pieza y cada agente declara sus campos») y es el ejemplo más claro de Estrategia del proyecto.

**Decisión de Miguel:** _pendiente_

### PC-4. Cómo se inyecta «hoy» para poder probar las fechas pasadas

- **A. Parámetro `today: Callable[[], date] = date.today`** en `DateField` y en `DebtAgent`, que se lo pasa. En los tests: `DebtAgent(..., today=lambda: date(2026, 11, 13))`.
  - Pros: una línea; sin librerías; explícito.
  - Contras: el constructor de `DebtAgent` tiene un parámetro que `AssistanceAgent` no tiene.
- **B. Un objeto `Clock` con método `today()` inyectado en `BaseAgent`** para todos los agentes.
  - Pros: uniforme.
  - Contras: una clase para una sola llamada; `AssistanceAgent` recibiría algo que no usa.
- **C. No inyectar; en los tests, parchear `date.today` (monkeypatch) o elegir fechas lejanas (`2999-01-01`).**
  - Pros: cero diseño.
  - Contras: `date` no se puede parchear fácilmente (es tipo de C); las fechas lejanas no prueban el borde «hoy vale / ayer no».
- **Recomendación: A.** Es lo mínimo que permite probar el borde exacto que Miguel decidió (hoy sí, ayer no).

**Decisión de Miguel:** _pendiente_

### PC-5. Dónde vive el control de duplicados y qué es exactamente la «huella»

Dos preguntas.

**5.1 Dónde vive.**
- **A. Un `set` privado dentro de `BaseAgent`.** Pros: 3 líneas. Contras: no se prueba por separado; para pasar a un registro externo (AMB-1 C) habría que tocar la base.
- **B. Clase pequeña `SentActionRegistry` + función `fingerprint`, que la base usa (y que se puede inyectar).** Pros: se prueba sola; cambiarla por una persistente (Redis, BD) no toca los agentes. Contras: un archivo más.
- **Recomendación: B.** Es el corazón de RF-17 y merece su propia pieza y sus propios tests.

**5.2 Contra qué se compara** (la huella es siempre «acción + datos normalizados»).
- **A. Contra todos los envíos de la conversación.** Pros: literal con «no se envían duplicados durante la conversación»; sirve igual para los dos agentes. Contras: en cobros, A → B → A no reenvía la última A (el backend se queda con B aunque el cliente volvió a A).
- **B. Solo contra el último envío de esa acción.** Pros: encaja con «lo que vale es el último compromiso» (AMB-1). Contras: en atención, «cambiar dirección» → «baja» → «cambiar dirección» registraría dos veces la misma solicitud a los humanos; un evaluador lo puede leer como duplicado.
- **C. Que cada agente elija (A para atención, B para cobros).** Pros: la semántica correcta para cada uno. Contras: otro punto de configuración por agente y más que explicar.
- **Recomendación: A.** Cumple el enunciado al pie de la letra, es igual para los dos agentes y el caso A → B → A es raro; se documenta en el README como límite conocido.

**Decisión de Miguel:** ✅ **5.1 B y 5.2 A** (ver `DECISIONES.md`).

### PC-6. Dónde y cuándo se genera la `Idempotency-Key`

- **A. La genera `HttpActionSender` al empezar cada `send()` (UUID aleatorio), y la reutiliza en todos los reintentos de ese envío.** La función generadora se inyecta para que los tests tengan claves fijas.
  - Pros: cumple exactamente AMB-4 («la misma en todos sus reintentos»); el agente no sabe nada de ella; cero estado.
  - Contras: si un envío falla del todo y en el turno siguiente se repite, va con otra clave (el servidor no lo puede deduplicar si el primero sí llegó).
- **B. Derivada de la huella (hash de acción + datos).**
  - Pros: el reenvío en otro turno lleva la misma clave, el servidor deduplica también entre turnos.
  - Contras: dos conversaciones distintas con los mismos datos (dos clientes que prometen 150 € el 1-dic) tendrían la misma clave y el servidor descartaría la segunda: grave. Para evitarlo haría falta un id de conversación, que hoy no existe (AMB-10 descartó inventarlo).
- **C. Derivada de la huella + un id aleatorio por instancia de agente (por conversación).**
  - Pros: dedup entre turnos sin choque entre conversaciones.
  - Contras: más lógica; con PC-5 A, un mismo dato reenviado tras fallo reutiliza clave (bien), pero hay que explicar cuándo cambia.
- **Recomendación: A.** Es lo que Miguel describió en AMB-4 y lo más fácil de defender; el caso «falló todo y se repite en otro turno» se explica en el README.

**Decisión de Miguel:** _pendiente_

### PC-7. Dónde viven los reintentos y qué cuenta como «reintentable»

**7.1 Dónde.**
- **A. Bucle dentro de `HttpActionSender.send`**, con `RetryPolicy` inyectada. Pros: un único sitio; la request se construye una vez antes del bucle, así la clave es la misma por construcción. Contras: el sender hace dos cosas (construir y reintentar).
- **B. Un envoltorio `RetryingHttpClient` que cumple `HttpClient` y envuelve al cliente real (patrón Decorador: un objeto que envuelve a otro con la misma interfaz y le añade comportamiento).** Pros: separación limpia; el sender no sabe que hay reintentos. Contras: una clase más; el `SendResult` necesita saber cuántos intentos hubo, que queda escondido en el envoltorio.
- **Recomendación: A.** Es menos código y sigue siendo testeable gracias a `RetryPolicy.sleep`.

**7.2 Errores de transporte** (timeout, conexión rechazada: el `FakeHttpClient` no los produce, pero un cliente real sí).
- **A. Tratarlos como un 5xx (reintentables).** Pros: robusto ante cortes puntuales, que es el motivo de Miguel para reintentar. Contras: un `try/except` más.
- **B. No contemplarlos (fuera de alcance, solo códigos de estado).** Pros: más simple. Contras: con un cliente real, una excepción tiraría el turno, contra AMB-4/AMB-11.
- **Recomendación: A**, capturando una excepción propia `TransportError` que lanzaría cualquier cliente real (y que el fake puede simular).

**Decisión de Miguel:** _pendiente_

### PC-8. La respuesta se genera antes de enviar: ¿qué pasa si el envío falla?

El paso 1 obtiene la respuesta («Perfecto, queda apuntado el pago de 150 € para el 1 de diciembre») y el paso 6 puede acabar en `FAILED` tras los reintentos. El cliente habría oído «apuntado» sin que lo esté. Es el mismo problema que llevó a Miguel a usar la respuesta de emergencia cuando falla el parser (AMB-11).

- **A. Aceptarlo: se devuelve la respuesta normal y el `TurnResult` dice `FAILED`.** Quien llama al agente decide qué hacer.
  - Pros: cero lógica extra; nada se oculta.
  - Contras: el cliente cree que está registrado; incoherente con la decisión del parser.
- **B. Sustituir la respuesta por `EMERGENCY_REPLY` si el estado es `FAILED`** (`answer_user` se llama igual, para no descuadrar el guion; su texto queda en el log).
  - Pros: coherente con AMB-11; el cliente nunca oye una promesa falsa; una condición.
  - Contras: un fallo de un servicio interno se nota en la conversación; se pierde la respuesta «buena» del modelo (que, si no prometía nada, habría valido).
- **C. Reordenar el turno: parsear → validar → enviar → responder.**
  - Pros: la respuesta se genera ya sabiendo el resultado.
  - Contras: rompe el «orden fijo del enunciado» que Miguel eligió en AMB-11; y como `answer_user()` no recibe parámetros, el modelo no puede usar el resultado, así que en la práctica no cambia nada respecto a B.
- **Recomendación: B.** Mantiene el orden y aplica la misma regla que Miguel ya decidió para el parser: «la respuesta normal podría prometer algo que no se ha registrado».

Dos preguntas que van con esta:
- **8.2 Si falla `answer_user` pero el parser da datos válidos, ¿se envía la acción?** AMB-11 no lo dice. (a) Sí: los datos son buenos y el control de duplicados evita el doble registro si el cliente lo repite; (b) No: si el cliente oye «error», no debería quedar registrado. **Recomendación: (a)**, y seguir llamando siempre a `parse_data` para que los dos guiones no se descuadren.
- **8.3 `ScriptExhaustedError` (guion agotado), ¿se trata como fallo del modelo (respuesta de emergencia) o se deja salir?** (a) Dejarla salir: es un test o una demo mal preparados y «se tiene que notar» (AMB-6); (b) tratarla como cualquier fallo. **Recomendación: (a).**

**Decisión de Miguel:** ✅ **B; 8.2 (b), no se envía; 8.3 (a)** (ver `DECISIONES.md`).

### PC-9. Cómo se inyectan las dependencias

- **A. Todo por constructor y obligatorio** (modelos, sender, registro, reloj); se monta en una raíz de composición o una función `build_debt_agent(settings, client)`.
  - Pros: todo explícito.
  - Contras: crear un agente en un test pide 5-6 argumentos.
- **B. Por constructor: obligatorios los modelos y el `sender`; opcionales con valor por defecto el registro (uno nuevo) y `today` (`date.today`).** La demo hace de raíz de composición.
  - Pros: lo que cambia entre entornos es obligatorio; lo que casi nunca cambia tiene un valor sensato; los tests siguen pudiendo inyectarlo todo.
  - Contras: hay que justificar qué es obligatorio y qué no.
- **C. El agente crea sus colaboradores a partir de la configuración** (sin inyección).
  - Pros: crear un agente es `DebtAgent()`.
  - Contras: imposible probar sin parches; acopla el agente al HTTP; contradice «testeable».
- **Recomendación: B.**

**Decisión de Miguel:** _pendiente_

### PC-10. Dónde va la configuración (URLs, token, reintentos)

- **A. Todo como constantes en `config.py`.**
  - Pros: un único sitio.
  - Contras: el token queda fijo en el código; cambiar de entorno es editar código; añadir un agente obliga a tocar `config.py`.
- **B. URL y nombre de la acción como atributos de cada agente; token y reintentos en `Settings` (dataclass) con valores por defecto y `Settings.from_env()` para leer variables de entorno.**
  - Pros: un agente nuevo se define en su propio archivo; el token se puede cambiar sin tocar código; el valor por defecto es el token de pruebas que da el enunciado (no es un secreto real).
  - Contras: la URL fija en la clase dificulta apuntar a otro entorno (staging) sin subclase.
- **C. Todo (incluidas URLs) en `Settings` / variables de entorno.**
  - Pros: máxima flexibilidad por entorno.
  - Contras: el agente ya no se entiende leyendo su archivo; añadir un agente toca dos sitios.
- **Recomendación: B.** Lo dice el enunciado (cada agente tiene su endpoint) y deja el token fuera del código cuando haga falta.

**Decisión de Miguel:** _pendiente_

### PC-11. Cómo se redondea el importe a céntimos

Detalle de dinero: `round(2.675, 2)` en Python da `2.67`, porque el `float` 2.675 es en realidad 2.67499999...; y `round` además usa el «redondeo del banquero» (los .5 van al par).
- **A. `round(valor, 2)` sobre `float`.** Pros: una línea. Contras: los dos problemas de arriba.
- **B. Convertir a `Decimal` desde el texto (`Decimal(str(valor))`), redondear con `ROUND_HALF_UP` y devolver `float`** (el enunciado dice que el campo es `float`). Pros: redondeo «de colegio», correcto; la salida respeta el tipo del enunciado. Contras: dos conversiones que hay que explicar.
- **C. `Decimal` en todo el sistema y en el JSON como texto (`"150.50"`).** Pros: lo más correcto para dinero. Contras: contradice el tipo `float` del enunciado y cambia el body de AMB-10.
- **Recomendación: B.**

**Decisión de Miguel:** _pendiente_

### PC-12. Cuándo se codifican los valores de las cabeceras

AMB-7 decidió codificar los valores no ASCII (`Cambiar%20direcci%C3%B3n`). Falta concretar si se codifica solo cuando hay no ASCII o siempre.
- **A. Siempre `urllib.parse.quote(valor, safe="")`.** Pros: regla única; el receptor siempre decodifica; también protege de saltos de línea o caracteres de control en la cabecera. Contras: un texto ASCII con espacios también cambia (`Quiero%20cambiar`).
- **B. Solo si el valor tiene algún carácter no ASCII.** Pros: los valores simples quedan legibles. Contras: el receptor no sabe si tiene que decodificar; un `%` literal en un texto ASCII se malinterpretaría.
- **Recomendación: A.** Fechas e importes no cambian (no tienen caracteres especiales), y la regla es una sola.

**Decisión de Miguel:** _pendiente_

---

## 4. Principios y patrones (dónde y por qué)

| Dónde | Principio / patrón | Por qué hace falta aquí |
|---|---|---|
| `BaseAgent.handle_turn` | **Método plantilla** | El orden del turno es fijo (AMB-11) e igual para todos los agentes; escribirlo una vez evita que cada agente lo repita (y lo repita mal). |
| `FieldNormalizer` + `TextField`/`DateField`/`AmountField` | **Estrategia** y **Abierto/Cerrado (OCP**: se amplía añadiendo piezas nuevas, sin modificar las existentes) | Cada agente combina normalizadores distintos (AMB-3 forma C); un tipo de dato nuevo es una clase nueva, sin tocar `normalize`. |
| `ActionSender`, `HttpClient` (Protocol) | **Inversión de dependencias (DIP**: el código de alto nivel depende de interfaces, no de clases concretas) | El agente no debe saber si el envío es HTTP simulado, HTTP real o una cola (RNF-2, «nuevas integraciones»); y en los tests se le da un fake. |
| `ActionSender`, `HttpClient` con un solo método | **Segregación de interfaces (ISP**: interfaces pequeñas) | Para cumplirlas basta con un método `send`; un fake de tres líneas vale. |
| Un archivo / clase por tarea (`models`, `fields`, `dedup`, `sender`, `http`) | **Responsabilidad única (SRP)** | Cada pieza tiene una razón para cambiar: si cambia la política de reintentos, no se toca la validación ni los agentes. |
| `DebtAgent`/`AssistanceAgent` usables donde se espera `BaseAgent`; `FakeHttpClient` donde se espera `HttpClient` | **Sustitución de Liskov (LSP)** | La demo y los tests tratan a cualquier agente igual (`agent.handle_turn()`); un tercer agente funciona sin cambios (CA-13). |
| Constructores que reciben modelos, sender, registro, `today`, `sleep`, generador de claves | **Inyección de dependencias** | Todo lo no determinista (fecha, esperas, UUID, red) se puede fijar en los tests (RNF-3). |
| `TurnResult`, `SendResult`, `HttpRequest`, `HttpResponse`, `RetryPolicy`, `Settings` | **DTO / objetos de valor** inmutables (`frozen=True`) | Devuelven información sin exponer estado modificable (AMB-5); se comparan fácil en los tests. |
| `FakeHttpClient`, modelos con guion | **Fakes** (dobles de prueba) | El enunciado pide simular HTTP y LLM; con fakes no hace falta `unittest.mock` en casi ningún test. |

Patrones que **no** se usan, a propósito: fábrica o registro de agentes (con dos agentes, `DebtAgent(...)` es más claro), Observer/eventos para el log (`logging` ya lo resuelve), contenedor de inyección (la demo monta las piezas en 10 líneas), Decorador para reintentos (ver PC-7).

---

## 5. Extensibilidad

**(a) Un agente nuevo** (p. ej. `AppointmentAgent`):
1. Crear `src/ringr_agents/agents/appointment.py`: subclase de `BaseAgent` con `action_name`, `action_url`, `fields()` y `should_execute()`.
2. Exportarlo en `agents/__init__.py` (una línea).
3. Tests en `tests/test_appointment_agent.py`.
No se toca `BaseAgent`, ni los otros agentes, ni el envío, ni los duplicados (CA-13).

**(b) Una acción nueva:**
- Si es «registrar otra cosa en otro endpoint», es un agente nuevo: caso (a).
- Si necesita un tipo de dato nuevo (p. ej. un teléfono), se añade un normalizador en `fields.py` (o en su propio archivo) y el agente lo declara. `normalize` no cambia.
- Límite conocido: hoy cada agente tiene **una** acción. Si un agente necesitara dos, habría que tocar `BaseAgent` (pasaría de `action_url` a una lista de acciones). No se hace ahora porque ningún requisito lo pide.

**(c) Una integración nueva:**
- Otro transporte HTTP (un cliente real con `urllib`): nueva clase que cumpla `HttpClient` y se inyecta en `HttpActionSender`. Los agentes no cambian.
- Algo que no es HTTP (una cola de mensajes): nueva clase que cumpla `ActionSender` y se inyecta en el agente. Ni los agentes ni `HttpActionSender` cambian.
- En ambos casos solo cambia la raíz de composición (`__main__.py`).

---

## 6. Estructura de carpetas

```
entrega/
├── pyproject.toml                   # metadatos, Python >= 3.11, pytest y ruff como dependencias de desarrollo, configuración de ruff y pytest
├── README.md                        # lo redacta Miguel en la fase 5
├── .gitignore                       # .venv, __pycache__, .pytest_cache, .ruff_cache
├── .github/workflows/ci.yml         # CI: ruff check + ruff format --check + pytest en cada PR (FLU-1)
├── docs/
│   ├── enunciado.pdf                # enunciado original
│   ├── REQUISITOS.md                # requisitos y ambigüedades
│   ├── DECISIONES.md                # decisiones de Miguel con su porqué
│   └── ARQUITECTURA.md              # este documento
├── src/ringr_agents/
│   ├── __init__.py                  # exporta las clases públicas
│   ├── __main__.py                  # demo y raíz de composición: `python -m ringr_agents`
│   ├── config.py                    # Settings (token, reintentos) y from_env()
│   ├── models.py                    # ConversationModel, ParserModel, ScriptExhaustedError
│   ├── fields.py                    # FieldNormalizer, TextField, DateField, AmountField, InvalidFieldError, normalize
│   ├── results.py                   # ActionStatus, TurnResult
│   ├── http.py                      # HttpRequest, HttpResponse, HttpClient, FakeHttpClient, TransportError
│   ├── sender.py                    # ActionSender, SendResult, RetryPolicy, HttpActionSender
│   ├── dedup.py                     # fingerprint, SentActionRegistry
│   └── agents/
│       ├── __init__.py              # exporta BaseAgent, DebtAgent, AssistanceAgent
│       ├── base.py                  # BaseAgent (handle_turn) y EMERGENCY_REPLY
│       ├── debt.py                  # DebtAgent
│       └── assistance.py            # AssistanceAgent
└── tests/
    ├── conftest.py                  # fixtures comunes y bloqueo de sockets (CA-14)
    ├── test_models.py               # guiones, copia del dict, error al agotarse, excepción en guion
    ├── test_fields.py               # reglas de cada normalizador y de normalize
    ├── test_http.py                 # FakeHttpClient: guarda requests, códigos configurables
    ├── test_sender.py               # construcción de la request, codificación, reintentos, Idempotency-Key
    ├── test_dedup.py                # huella y registro
    ├── test_base_agent.py           # el ciclo con un agente de prueba: fallos de modelos, PC-8, CA-13
    ├── test_debt_agent.py           # CA-1, CA-2, CA-3, CA-6, CA-7, CA-8, CA-9, CA-10, CA-11
    └── test_assistance_agent.py     # CA-4, CA-5, CA-6, CA-7
```

---

## 7. Estrategia de tests

| Capa | Qué se prueba | Dobles |
|---|---|---|
| `models` | Devuelven el guion en orden; `parse_data` devuelve copia (modificar lo devuelto no altera el guion); al agotarse, `ScriptExhaustedError`; una excepción en el guion se lanza. | Ninguno. |
| `fields` | Cada regla de AMB-3 con casos borde, en tests parametrizados: `" 2026-12-01 "`, `"01/12/2026"`, `"2026-13-45"`, `"20261201"`, ayer / hoy / mañana; `150`, `"150"`, `"150,5"`, `"1.500,50"`, `"1,500"`, `0`, `-50`, `True`, `NaN`, `2.675` → `2.68`; `""` y `"   "` → `None`. `normalize`: claves que faltan, que sobran, aviso por inválido. | `today=lambda: date(2026, 11, 13)`. |
| `http` | `FakeHttpClient` guarda cada request; devuelve los códigos en orden y luego 200. | Ninguno. |
| `sender` | URL, método, `Authorization`, `Content-Type`, `Idempotency-Key`, cabeceras del parser (solo no nulas, codificadas), body JSON con tildes intactas; 503 → 200 = `ok` en 2 intentos con la misma clave; 503×3 = falla en 3; 400 = falla en 1; esperas crecientes; errores de transporte (si PC-7.2 A). | `FakeHttpClient`; `sleep` que apunta los segundos en una lista; generador de claves fijo. |
| `dedup` | Misma acción + mismos datos = misma huella; datos distintos o acción distinta = distinta; datos normalizados equivalentes = misma; marcar y consultar. | Ninguno. |
| `agents/base` | Con un `TestAgent` mínimo definido en el test (demuestra CA-13): fallo de `answer_user` → emergencia; fallo de `parse_data` → emergencia y sin envío; `FAILED` → lo que diga PC-8; ningún fallo sale como excepción; el log (con `caplog`). | Modelos con guion; `FakeHttpClient` + `HttpActionSender` real con `sleep` vacío. |
| Agentes concretos | Criterios de aceptación CA-1 a CA-12 de punta a punta, multi-turno (duplicado, corrección, fallo y reenvío en el turno siguiente). | Igual que la fila anterior. |
| Global | Ningún test abre red (CA-14): `conftest.py` sustituye `socket.socket` por algo que falla. | `monkeypatch`. |

Casi todo se prueba con **fakes** (objetos reales simplificados) en lugar de **mocks**: los tests comprueban resultados (`TurnResult`, `client.requests`) y no «a quién se llamó», así sobreviven a refactorizaciones. CA-1 («se ha llamado una vez a `answer_user` y a `parse_data`») se comprueba con guiones de un solo elemento: una segunda llamada lanzaría `ScriptExhaustedError`.

---

## 8. Plan de construcción

De dentro hacia fuera. Cada paso es una rama y una PR hacia `main` que se fusiona con el CI en verde (FLU-1). Al acabar cada paso, todo lo anterior sigue pasando.

| # | Paso | Queda funcionando y probado |
|---|---|---|
| 1 | **Esqueleto + CI:** `pyproject.toml`, `src/ringr_agents/__init__.py`, `.gitignore`, `.github/workflows/ci.yml` (ruff + pytest), `tests/conftest.py` con el bloqueo de red y un test trivial. | `ruff` y `pytest` pasan en local y en GitHub Actions. |
| 2 | **Modelos simulados** (`models.py`). | Guiones, copia, error al agotarse, excepción en guion. |
| 3 | **Normalizadores** (`fields.py`): `TextField`, `DateField`, `AmountField`, `normalize`. | Todas las reglas de AMB-2 y AMB-3, con el borde de «hoy». |
| 4 | **HTTP simulado** (`http.py`) y **resultados** (`results.py`). | `FakeHttpClient` guarda requests y devuelve códigos configurables. |
| 5 | **Construcción de la request** (`sender.py`: `build_request`, `Settings` en `config.py`). | URL, cabeceras (Bearer, Content-Type, Idempotency-Key, campos codificados) y body exactos. |
| 6 | **Envío con reintentos** (`HttpActionSender.send`, `RetryPolicy`). | 2xx / 4xx / 5xx / reintentos / misma clave / esperas. |
| 7 | **Duplicados** (`dedup.py`). | Huella y registro. |
| 8 | **`BaseAgent.handle_turn`** con un agente de prueba. | El ciclo completo, fallos de modelos, PC-8, sin excepciones hacia fuera, CA-13. |
| 9 | **`DebtAgent` y `AssistanceAgent`.** | CA-1 a CA-12 de punta a punta. |
| 10 | **Demo** (`__main__.py`). | `python -m ringr_agents` muestra varios turnos (feliz, duplicado, corrección, fallo con reintento) y su log. |

Después: verificación, revisión y README (fases 4 y 5 del flujo).

---

## 9. Piezas candidatas para que las escriba Miguel

1. **`BaseAgent.handle_turn`** (paso 8). Es el corazón del enunciado y la pregunta segura de la entrevista: orden de los pasos, qué pasa en cada fallo, por qué nunca lanza hacia fuera, cuándo se marca como enviado. Son unas 30-40 líneas que reflejan directamente sus decisiones de AMB-2, AMB-4, AMB-5, AMB-11 y PC-8.
2. **`fingerprint` y `SentActionRegistry`** (paso 7). Es la otra garantía explícita del enunciado (RF-17) y su decisión de AMB-1: por qué la huella usa los datos normalizados y por qué solo se marca tras un envío correcto. Pocas líneas, mucho que defender.
3. **El bucle de reintentos de `HttpActionSender.send`** (paso 6). Lo diseñó él en AMB-4 (3 intentos, solo 5xx, espera creciente, misma `Idempotency-Key`): escribirlo le permite explicar cada condición con seguridad.

Opcional, si sobra tiempo: **`AmountField.normalize`** (paso 3), porque las reglas del separador decimal y del redondeo (PC-11) son de las más finas del proyecto y son decisiones suyas.
