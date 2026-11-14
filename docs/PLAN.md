# PLAN

Estrategia de tests, plan de construcción y piezas que escribe Miguel. El diseño está en `ARQUITECTURA.md`; las reglas, en `REQUISITOS.md` y `DECISIONES.md`.

Las rutas siguen la estructura de carpetas decidida en CARP-1 (`ARQUITECTURA.md`, sección 6), relativas a `src/ringr_agents/`. Los tests imitan esa estructura dentro de `tests/`.

---

## 1. Estrategia de tests

| Capa (paso del plan) | Qué se prueba | Dobles |
|---|---|---|
| `infrastructure/models/` (2) | Devuelven el guion en orden; `parse_data` devuelve una copia; al agotarse, `ScriptExhaustedError`; una excepción en el guion se lanza. | Ninguno. |
| `domain/fields/` (2) | Cada regla de AMB-2 y AMB-3 con casos borde, en tests parametrizados: `" 2026-12-01 "`, `"01/12/2026"`, `"2026-13-45"`, `"20261201"`, ayer / hoy / mañana; `150`, `"150"`, `"150,5"`, `"1.500,50"`, `"1,500"`, `0`, `-50`, `True`, `NaN`, `2.675` → `2.68`; `""` y `"   "` → `None`. `normalize`: claves que faltan, que sobran, aviso por valor inválido. | `today=lambda: date(2026, 11, 13)`. |
| `infrastructure/http/` fake (3) | `FakeHttpClient` guarda cada request; devuelve los códigos en orden y luego 200; lanza el `TransportError` configurado; `attempts` = 1. | Ninguno. |
| `infrastructure/http/sender` (3) | URL, método, `Authorization`, `Content-Type`, `Idempotency-Key`, cabeceras del parser (solo campos no nulos, codificadas con `quote`), body JSON con tildes intactas, cabeceras fijas que no se pueden pisar; 200 → `ok`; 503 o 400 → `ok=False` en 1 intento (aquí no hay reintentos); `TransportError` → `ok=False`, `status_code=None`; `SendResult.idempotency_key` coincide con la de la request guardada en el fake. | `FakeHttpClient`; generador de claves fijo. |
| `infrastructure/config` (3) | `Settings.from_env()` con y sin variables. | `monkeypatch.setenv`. |
| `agents/base_agent` (4) | Con un `TestAgent` mínimo definido en el test, con cadenas en lugar de enumerados (demuestra CA-13): fallo de `answer_user` → emergencia, `NOT_REQUIRED`, `errors == (TurnError.CONVERSATION_FAILED,)` y sin envío aunque los datos sean válidos (PC-8.2 b), y `parse_data` se ha llamado igual; fallo de `parse_data` o resultado que no es `dict` → emergencia, `NOT_REQUIRED`, `TurnError.PARSER_FAILED`; envío `FAILED` → emergencia y `TurnError.SEND_FAILED` (PC-8 B); `ScriptExhaustedError` sale (PC-8.3 a); ningún otro fallo sale como excepción; el log (con `caplog`). | Modelos con guion; `FakeHttpClient` + `HttpActionSender` real. |
| `agents/debt`, `agents/assistance` (4) | CA-1 a CA-6 y CA-9 a CA-12 de punta a punta. CA-1 («se ha llamado una vez a cada modelo») con guiones de un solo elemento: una segunda llamada lanzaría `ScriptExhaustedError`. | Igual que la fila anterior. |
| `domain/dedup` (5) | Misma acción + mismos datos = misma huella; datos o acción distintos = huella distinta; datos normalizados equivalentes = misma huella; marcar y consultar. | Ninguno. |
| Agentes con duplicados (5) | CA-7 (repetido → `DUPLICATE`, una sola request), CA-8 (corrección → segunda request), A → B → A (no reenvía: límite conocido), fallo y reenvío en el turno siguiente (un `FAILED` no se marca). | Igual, más un `SentActionRegistry` inyectado cuando haga falta inspeccionarlo. |
| `infrastructure/http/retry` (6) | 503 → 200: respuesta 200 con `attempts=2`, y `inner` recibió la misma request dos veces (misma `Idempotency-Key`); 503×3 → 503 con `attempts=3`; 400 → 400 con `attempts=1`; `TransportError` → 200 reintenta; `TransportError`×3 → relanza con `attempts=3`; esperas `[0.2, 0.4]`; `max_attempts` configurable. Integración: un agente con `RetryingHttpClient` acaba `SENT` con `send_result.attempts == 2`, sin cambios en agentes ni `handle_turn`. | `FakeHttpClient`; `sleep` que apunta los segundos en una lista. |
| Demo (7) | `python -m ringr_agents` (su función principal) termina sin errores. | `sleep` vacío o `base_delay=0`. |
| Global | Ningún test abre red (CA-14): `conftest.py` sustituye `socket.socket` por algo que falla. | `monkeypatch`. |

Casi todo se prueba con **fakes** (objetos reales simplificados) en lugar de **mocks**: los tests comprueban resultados (`TurnResult`, `client.requests`) y no «a quién se llamó», así sobreviven a los cambios internos.

---

## 2. Plan de construcción

Orden decidido por Miguel (ver `PLAN` en `DECISIONES.md`): **primero un camino completo y luego se enriquece**. Cada paso es una rama y una PR hacia `main` que se fusiona con el CI en verde (FLU-1). Al acabar cada paso, todo lo anterior sigue pasando.

| # | Paso | Queda funcionando y probado |
|---|---|---|
| 1 | **Esqueleto + CI:** `pyproject.toml`, las carpetas `domain/`, `agents/` (con `debt/` y `assistance/`) e `infrastructure/` (con `models/` y `http/`) vacías con su `__init__.py`, `.gitignore`, `.github/workflows/ci.yml` (ruff + pytest), `tests/conftest.py` con el bloqueo de red y un test trivial. | `ruff` y `pytest` pasan en local y en GitHub Actions. |
| 2 | **Vocabulario** (`domain/enums.py`, `domain/constants.py`), **modelos simulados** (`infrastructure/models/`) y **normalizadores** (`domain/fields/`). | Guiones con error al agotarse; todas las reglas de AMB-2 y AMB-3, con el borde de «hoy». |
| 3 | **Resultado del envío y su interfaz** (`SendResult` en `domain/results.py`, `ActionSender` en `domain/ports.py`), **HTTP simulado** (`infrastructure/http/client.py`, `infrastructure/http/fake_client.py`), **construcción de la request** (`infrastructure/http/sender.py`) y **configuración** (`infrastructure/config.py`, con el token). | `FakeHttpClient` guarda requests y devuelve códigos configurables; URL, cabeceras y body exactos. Sin reintentos (siempre 1 intento). |
| 4 | **`TurnResult`** (`domain/results.py`), **`BaseAgent.handle_turn`** (`agents/base_agent.py`), **`DebtAgent`** (`agents/debt/agent.py`) y **`AssistanceAgent`** (`agents/assistance/agent.py`). *(Pieza de Miguel: `handle_turn`.)* | Los dos agentes de punta a punta (CA-1 a CA-12 salvo duplicados y reintentos), fallos de modelos con su `TurnError`, PC-8, sin excepciones hacia fuera salvo `ScriptExhaustedError`. **Desde aquí hay algo entregable.** |
| 5 | **Duplicados** (`domain/dedup.py`) integrados en `handle_turn`, con el `registry` opcional en el constructor de `BaseAgent` (PC-9 B). *(Pieza de Miguel.)* | Huella y registro; no se reenvía lo idéntico; un `FAILED` no se marca. |
| 6 | **Reintentos con el Decorator** (`infrastructure/http/retry.py`; `max_attempts` y `base_delay` en `Settings`). *(Pieza de Miguel: `RetryingHttpClient.send`.)* | 3 intentos, solo 5xx y errores de transporte, esperas crecientes, misma clave. **Sin tocar `handle_turn`, los agentes ni `HttpActionSender`.** |
| 7 | **Demo** (`__main__.py`). | `python -m ringr_agents` muestra varios turnos (feliz, duplicado, corrección, fallo con reintento) y su log. |

Después: verificación, revisión y README (fases 4 y 5 del flujo).

---

## 3. Piezas que escribe Miguel

Decididas por Miguel (ver `PIEZAS` en `DECISIONES.md`). El constructor las deja con la firma, un docstring y `NotImplementedError`.

1. **`BaseAgent.handle_turn`** (`agents/base_agent.py`, paso 4). El corazón del enunciado: el orden de los pasos, qué pasa en cada fallo, qué `TurnError` se anota, cuándo se usa la respuesta de emergencia, por qué no se envía si falla `answer_user` y por qué `ScriptExhaustedError` sí sale. Refleja AMB-2, AMB-5, AMB-11 y PC-8. En el paso 4, todavía sin duplicados.
2. **El control de duplicados** (`domain/dedup.py`, paso 5): `fingerprint`, `SentActionRegistry` y su uso dentro de `handle_turn` (consultar antes de enviar, marcar solo tras un envío correcto). La otra garantía explícita del enunciado (RF-17), con AMB-1 y PC-5.
3. **`RetryingHttpClient.send`** (`infrastructure/http/retry.py`, paso 6). La política de reintentos de AMB-4 (3 intentos, solo 5xx y errores de transporte, espera creciente, la misma request y por tanto la misma `Idempotency-Key`) y el Decorator de PC-7.1 B, que se añade sin tocar lo anterior.

**Pendiente de Miguel:** el porqué de esta elección todavía no está apuntado en `DECISIONES.md` (fila `PIEZAS`).
