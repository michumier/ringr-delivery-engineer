# Flujo de trabajo con Claude Code

Versión adaptada para la entrega de las instrucciones de proyecto que se usaron con Claude Code durante el desarrollo de la prueba (con las rutas relativas a este repositorio). Se incluye en la entrega para mostrar cómo se ha trabajado con IA: un flujo por fases, con agentes especializados y con las decisiones técnicas siempre en manos del desarrollador.

## Principio: el desarrollador decide

La prueba evalúa las decisiones técnicas y su razonamiento, así que el flujo está pensado para que ninguna decisión relevante la tome la IA por su cuenta:

- **Toda decisión de diseño se presenta como pregunta**, con 2-3 opciones, sus pros y contras y, si procede, una recomendación. El desarrollador elige.
- **Cada decisión se registra en `docs/DECISIONES.md`** con su porqué, en palabras del desarrollador. La IA puede ordenar la redacción, pero no cambiar ni añadir argumentos.
- **Las decisiones menores** (convenciones, detalles sin impacto en el diseño) se aplican directamente y se registran como «delegadas en Claude», para que quede constancia.
- **Una fase, una parada:** no se avanza a la siguiente sin revisión y aprobación.

## Documentación del proyecto

| Ruta | Contenido | Lo escribe |
|---|---|---|
| `docs/enunciado.pdf` | El enunciado de la prueba | — |
| `docs/REQUISITOS.md` | Requisitos, criterios de aceptación y ambigüedades con opciones | `analista-requisitos` |
| `docs/DECISIONES.md` | Registro de decisiones con su porqué | Claude, a partir de lo que decide el desarrollador |
| `docs/ARQUITECTURA.md` | Diseño aprobado: clases, patrones, dependencias y extensibilidad | `arquitecto` |
| `docs/PLAN.md` | Estrategia de tests y plan de construcción | `arquitecto` |

## Agentes (`.claude/agents/`)

| Agente | Modelo | Papel | Escribe en |
|---|---|---|---|
| `analista-requisitos` | Sonnet | Enunciado → requisitos, criterios de aceptación y **ambigüedades con opciones** | `docs/REQUISITOS.md` |
| `arquitecto` | Opus | Propone el diseño, con **alternativas** en los puntos clave | `docs/ARQUITECTURA.md` |
| `constructor` | Sonnet | Implementa **un paso** del plan cada vez | `src/` y configuración del proyecto |
| `tester` | Sonnet | Tests a partir de los criterios de aceptación | `tests/` |
| `verificador` | Haiku | Comprobaciones mecánicas: ruff, pytest, trazabilidad, secretos | Nada |
| `revisor` | Opus | Revisa como el evaluador; veredicto APTO / NECESITA CAMBIOS | Nada |

Cada agente tiene un único papel y escribe solo en su carpeta, de modo que el constructor no toca los tests, el tester no toca el código y los dos revisores no modifican nada. El modelo de cada uno se eligió según la tarea: Opus para diseñar y revisar, Sonnet para construir y probar, Haiku para comprobaciones mecánicas.

## Fases (🙋 = parada para revisión y aprobación)

1. **Requisitos.** `analista-requisitos` extrae requisitos, criterios de aceptación y ambigüedades.
   🙋 Se decide cada ambigüedad; cada decisión queda en `DECISIONES.md` y se marca como resuelta en `REQUISITOS.md`.
2. **Arquitectura.** `arquitecto` propone el diseño a partir de los requisitos y las decisiones.
   🙋 Se revisa cada punto clave y sus alternativas, y se aprueba el plan de construcción (pasos y orden).
3. **Construcción, paso a paso.** El primer paso incluye el CI (GitHub Actions con `ruff` y `pytest` en cada PR). Cada paso va en **su propia rama**:
   a. `constructor` implementa el paso.
   b. `tester` escribe y ejecuta sus tests.
   c. 🙋 Se revisan los cambios y el resultado de los tests. Commit con un mensaje aprobado, push y PR hacia `main`.
   d. `revisor` revisa **solo el diff de la PR**. Su informe se publica como comentario en la PR, encabezado por «🤖 Revisión automática (Claude, agente revisor)».
   e. Se responde en la PR qué sugerencias se aceptan y por qué; lo aceptado se corrige en la misma rama. **Se fusiona solo con aprobación y el CI en verde.**
4. **Verificación.** `verificador` y después `revisor` sobre **el proyecto entero**.
   🙋 Se decide qué se corrige y qué no, y por qué. Lo que se corrige vuelve a la fase 3.
5. **README.** Qué hace, cómo se ejecuta, por qué está diseñado así (a partir de `DECISIONES.md` y `ARQUITECTURA.md`) y el flujo de trabajo.
6. **Entrega.** Repositorio de GitHub.

## Reglas técnicas

- Python 3.11 o superior, con su propio `pyproject.toml` y entorno virtual (`.venv`).
- **El enunciado manda.** Si algo no lo dice, es una ambigüedad que se decide, no una suposición.
- Los nombres que impone el enunciado (`handle_turn`, `ConversationModel.answer_user`, `ParserModel.parse_data`, `DebtAgent`, `AssistanceAgent`, `commitment_date`, `committed_amount`, `request`) se respetan tal cual.
- **Sin llamadas HTTP reales ni a LLMs:** todo simulado, como pide el enunciado. Los tests bloquean la red.
- Git: una rama por paso y PR hacia `main`; ningún commit, push ni PR sin aprobación.
- **Autoría:** los commits y las PR no llevan líneas de atribución a Claude. El uso de IA se explica en el README y en este archivo.
