# REQUISITOS

Fuente: enunciado «Prueba técnica: Delivery Engineer» (Ringr). Todo lo que sale literalmente del enunciado va citado. Lo que el enunciado no cierra está en la sección de ambigüedades; todas están resueltas y su decisión, con el porqué, está en `DECISIONES.md`.

## 1. Contexto

Se pide un pequeño proyecto de código orientado a objetos en Python: agentes conversacionales que, en cada turno, responden al usuario, extraen información estructurada de la conversación y deciden si ejecutan una acción externa mediante una integración HTTP simulada. Hay dos agentes (`DebtAgent` y `AssistanceAgent`) y dos modelos genéricos simulados (`ConversationModel` y `ParserModel`). El enunciado dice que importan «mucho más las decisiones técnicas que tomes y los razonamientos que te lleven a ellas que la solución concreta». La entrega es un repositorio de GitHub; el correo de Ringr indica «resuelve las potenciales ambigüedades a tu criterio».

## 2. Requisitos funcionales

**RF-1. Método `handle_turn`.** Cada agente (`DebtAgent`, `AssistanceAgent`) expone un método `handle_turn` que representa un turno de ejecución.
> «Cada agente debe exponer un método handle_turn que represente un turno de ejecución»

**RF-2. Respuesta al usuario.** En cada turno, `handle_turn` obtiene la respuesta llamando a `ConversationModel.answer_user`, que devuelve un `str`.
> «Obtener una respuesta del usuario a través de un objeto ConversationModel que implementa el método answer_user que devuelve un str con la respuesta.»

**RF-3. Parseo.** En cada turno, `handle_turn` obtiene la información estructurada llamando a `ParserModel.parse_data`, que devuelve un `dict` tipo JSON cuyas claves dependen del agente.
> «Parsear información relevante de la conversación mediante un objeto ParserModel que implementa el método parse_data que devuelve un dict tipo JSON con la información estructurada. Las claves del JSON dependen del caso de uso»

**RF-4. Validar y normalizar.** `handle_turn` valida y normaliza la información parseada antes de decidir.
> «Validar y normalizar la información parseada y decidir si se debe ejecutar una acción.»

**RF-5. Ejecutar la acción por HTTP simulada.** Si procede, `handle_turn` ejecuta la acción mediante una integración HTTP simulada.
> «Ejecutar la acción correspondiente mediante una integración HTTP simulada.»

**RF-6. Ciclo de vida del turno.** El turno genera respuesta, extrae información y decide si ejecuta una acción externa.
> «Un ciclo de vida del agente que, en cada turno, genere una respuesta al usuario, extraiga información estructurada de la conversación y decida si debe ejecutar una acción externa.»

**RF-7. `DebtAgent`: campos parseados.** El parser de `DebtAgent` devuelve `commitment_date` (`None` o `str` con formato `yyyy-mm-dd`) y `committed_amount` (`None` o `float`).
> «La fecha comprometida de pago (campo commitment_date, con valores None o str en formato 'yyyy-mm-dd'). La cantidad comprometida (campo committed_amount, con valores None o float).»

**RF-8. `DebtAgent`: condición de acción.** Solo cuando `commitment_date` y `committed_amount` son ambos distintos de `None`, `DebtAgent` hace un POST a `https://api.ringr.debt/v1/commitment`.
> «Cuando ambos valores sean distintos de None, se debe realizar una llamada POST al endpoint ficticio https://api.ringr.debt/v1/commitment para registrar el compromiso.»

**RF-9. `AssistanceAgent`: campo parseado.** El parser de `AssistanceAgent` devuelve `request` (`None` o `str`).
> «La solicitud que el usuario quiere registrar, si hay alguna (campo request, con valores None o str).»

**RF-10. `AssistanceAgent`: condición de acción.** Solo cuando `request` no es nulo, `AssistanceAgent` hace un POST a `https://api.ringr.assistance/v1/request`.
> «Cuando exista una solicitud con valor no nulo, se debe realizar una llamada POST al endpoint ficticio https://api.ringr.assistance/v1/request para registrarla.»

**RF-11. Requests bien construidas pero no enviadas.** Las integraciones HTTP no hacen red real, pero construyen correctamente la request (URL, headers y body).
> «Las integraciones HTTP no deben ejecutarse realmente, pero sí deben construir correctamente la request (URL, headers y body).»

**RF-12. Autenticación.** Todas las llamadas llevan el header `Authorization: Bearer ringr_test_token_9f3a2c1d`.
> «Todas las llamadas deben incluir autenticación mediante el Bearer Token ringr_test_token_9f3a2c1d»

**RF-13. Headers adicionales desde el parser.** Los datos devueltos por el `ParserModel` se añaden como headers adicionales con los mismos nombres que tienen en el parser.
> «considerar como headers adicionales los datos devueltos por el ParserModel con los mismos nombres.»

**RF-14. Respuesta 200 OK simulada.** La integración simulada devuelve 200 OK cuando la petición es exitosa.
> «Se puede asumir que, si las peticiones son exitosas, el endpoint devuelve un 200 OK.»

**RF-15. Modelos simulados genéricos.** `ConversationModel` y `ParserModel` son simulados, genéricos, sin subclases y con su estado interno adaptado al caso de uso.
> «Se puede considerar que los objetos ConversationModel y ParserModel genéricos contienen toda la información necesaria en su estado interno para adaptarse al caso de uso, no hacen falta subclases de estos.»

**RF-16. Acciones solo si se cumplen las condiciones.** Los agentes no ejecutan acciones externas si no se cumplen las condiciones de RF-8 / RF-10.
> «Los agentes deben garantizar que las acciones externas se ejecutan únicamente cuando se cumplen las condiciones definidas»

**RF-17. Sin duplicados.** Los agentes no envían la misma acción externa más de una vez durante la conversación.
> «y que no se envían duplicados durante la conversación.»

**RF-18. Dos agentes diferenciados.**
> «Se deben implementar dos agentes distintos, con comportamientos diferenciados»

## 3. Requisitos no funcionales

- **RNF-1. Orientación a objetos.** Código orientado a objetos. > «desarrollar un pequeño proyecto de código orientado a objetos en Python»
- **RNF-2. Extensibilidad.** Debe poder añadirse sin tocar lo existente (o con cambios mínimos): nuevos agentes, nuevos tipos de acciones, nuevas integraciones. > «permita escalar fácilmente a nuevos agentes, nuevos tipos de acciones y nuevas integraciones»
- **RNF-3. Calidad.** Código limpio, robusto y testeable. > «manteniendo un código limpio, robusto y testeable»
- **RNF-4. Estructura del proyecto.** Estructura clara y justificada. > «selección de la estructura del proyecto»
- **RNF-5. Justificación de decisiones.** Las buenas prácticas aplicadas se razonan (README). > «Aplicación y justificación de las mejores prácticas»
- **RNF-6. README claro.** > «Claridad en la exposición del fichero readme.»
- **RNF-7. Mocks permitidos.** Se pueden mockear objetos adicionales necesarios. > «Se pueden realizar mocks de todos los objetos adicionales que se consideren necesarios»
- **RNF-8. Python.** Python 3.11 o superior (regla del proyecto de Miguel, no del enunciado; el enunciado solo dice «Python»).

## 4. Criterios de aceptación

Convención: `Debt` = `DebtAgent`; `Asist` = `AssistanceAgent`. Los valores son ejemplos para los tests; los casos marcados (AMB-n) siguen la decisión de esa ambigüedad (ver `DECISIONES.md`).

**CA-1 (RF-1, RF-2, RF-3, RF-6).**
- Dado un `DebtAgent` con un `ConversationModel` simulado que responde `"Perfecto, queda anotado."` y un `ParserModel` simulado que devuelve `{"commitment_date": None, "committed_amount": None}`,
- Cuando se llama a `handle_turn`,
- Entonces se ha llamado una vez a `answer_user` y una vez a `parse_data`, y no se ha enviado ninguna request.

**CA-2 (RF-8, RF-11, RF-12, RF-14). Caso feliz de cobros.**
- Dado un parser que devuelve `{"commitment_date": "2026-12-01", "committed_amount": 150.0}`,
- Cuando se llama a `handle_turn` del `DebtAgent`,
- Entonces se construye exactamente 1 request `POST` a `https://api.ringr.debt/v1/commitment`, con header `Authorization: Bearer ringr_test_token_9f3a2c1d`, un body que contiene la fecha `2026-12-01` y la cantidad `150.0` (forma exacta: AMB-10), y la respuesta simulada es 200.

**CA-3 (RF-8, RF-16). Datos incompletos en cobros.**
- Dado un parser que devuelve `{"commitment_date": "2026-12-01", "committed_amount": None}` (y otro caso `{"commitment_date": None, "committed_amount": 150.0}`),
- Cuando se llama a `handle_turn`,
- Entonces no se envía ninguna request. (Si los valores se acumulan entre turnos: AMB-12.)

**CA-4 (RF-10, RF-11, RF-12). Caso feliz de atención.**
- Dado un parser que devuelve `{"request": "Quiero cambiar mi dirección de facturación"}`,
- Cuando se llama a `handle_turn` del `AssistanceAgent`,
- Entonces se construye exactamente 1 request `POST` a `https://api.ringr.assistance/v1/request`, con `Authorization: Bearer ringr_test_token_9f3a2c1d` y un body que contiene esa solicitud (forma exacta: AMB-10).

**CA-5 (RF-10, RF-16). Sin solicitud.**
- Dado un parser que devuelve `{"request": None}`,
- Cuando se llama a `handle_turn` del `AssistanceAgent`,
- Entonces no se envía ninguna request.

**CA-6 (RF-13). Headers adicionales.**
- Dado un parser que devuelve `{"commitment_date": "2026-12-01", "committed_amount": 150.0}`,
- Cuando el `DebtAgent` construye la request,
- Entonces los headers incluyen, además de `Authorization`, entradas con los nombres `commitment_date` y `committed_amount` (formato de valores y de `Content-Type`: AMB-7). Análogo con `request` en `AssistanceAgent`.

**CA-7 (RF-17). Sin duplicados.**
- Dado un `DebtAgent` cuyo parser devuelve `{"commitment_date": "2026-12-01", "committed_amount": 150.0}` en dos turnos consecutivos de la misma conversación,
- Cuando se llama dos veces a `handle_turn`,
- Entonces solo se envía 1 request. Análogo para `AssistanceAgent` con `request` = `"Quiero cambiar mi dirección"` en dos turnos. (Qué cuenta como duplicado, p. ej. misma fecha y distinto importe: AMB-1.)

**CA-8 (RF-17, AMB-1). Valor distinto después del primero.**
- Dado un `DebtAgent` que ya envió `{"2026-12-01", 150.0}`,
- Cuando en un turno posterior el parser devuelve `{"2026-12-15", 150.0}`,
- Entonces el resultado depende de AMB-1 (con la opción A se envía una 2.ª request; con B/C no).

**CA-9 (RF-4, AMB-2, AMB-3). Datos inválidos.**
- Dado un parser que devuelve, por separado, `{"commitment_date": "01/12/2026", "committed_amount": 150.0}`, `{"commitment_date": "2026-12-01", "committed_amount": -50.0}`, `{"commitment_date": "2026-13-45", "committed_amount": 150.0}`, `{"commitment_date": "2026-12-01", "committed_amount": "150"}`,
- Cuando se llama a `handle_turn`,
- Entonces el comportamiento esperado (no enviar / lanzar error / normalizar) depende de AMB-2 y AMB-3. El tester debe fijarlo según la decisión.

**CA-10 (RF-4, AMB-2). Claves que faltan o sobran.**
- Dado un parser que devuelve `{}` o `{"commitment_date": "2026-12-01", "committed_amount": 150.0, "extra": 1}`,
- Cuando se llama a `handle_turn`,
- Entonces según AMB-2 (`{}` equivale a «sin datos»; la clave extra se ignora o se rechaza).

**CA-11 (RF-14, AMB-4). Fallo HTTP.**
- Dado un cliente HTTP simulado configurado para responder 500,
- Cuando el agente intenta ejecutar la acción,
- Entonces el comportamiento (error, reintento, marcar o no como enviada) depende de AMB-4.

**CA-12 (RF-1, AMB-5). Valor devuelto.**
- Dado cualquier agente,
- Cuando se llama a `handle_turn`,
- Entonces devuelve lo que decida AMB-5 (p. ej. la respuesta `str` del `ConversationModel`).

**CA-13 (RNF-2). Extensibilidad.**
- Dado el proyecto terminado,
- Cuando se quiere añadir un tercer agente ficticio con su acción y su integración en un test,
- Entonces es posible sin modificar el código de `DebtAgent` ni `AssistanceAgent`.

**CA-14 (RF-11, RNF-3). Sin red real.**
- Dado cualquier test,
- Cuando se ejecuta la suite sin conexión a internet,
- Entonces pasa y no se abre ninguna conexión.

**CA-15 (RNF-6, RNF-5).** Dado el repositorio entregado, cuando se abre el README, entonces explica estructura, decisiones con su razonamiento, cómo ejecutar y cómo extender.

## 5. Ambigüedades

> Todas están resueltas. Cada una conserva sus opciones y la recomendación del analista; la decisión de Miguel va al final de cada una y, con su porqué, en `DECISIONES.md`.

### AMB-1. Qué cuenta como «duplicado» y en qué ámbito
**Qué no está claro.** El enunciado dice «no se envían duplicados durante la conversación», sin definir «duplicado» (¿misma acción exacta, mismo tipo de acción?) ni ámbito. Importa porque es una de las dos garantías explícitas y el corazón de `handle_turn`.
- **A. Duplicado = misma acción con mismos datos (huella: tipo + payload normalizado), ámbito = instancia del agente/conversación.** Pro: permite registrar un compromiso corregido (otra fecha/importe) y no repite el idéntico. Contra: el usuario cambiando de idea genera varios registros en el backend.
- **B. Máximo una acción por tipo por conversación** (tras enviar, no se vuelve a enviar nada). Pro: simplísimo y nunca duplica. Contra: no permite corregir un compromiso; datos erróneos se quedan.
- **C. Duplicado por clave de idempotencia** (id de conversación + huella) en un registro externo al agente (inyectable). Pro: escalable, el mismo registro sirve a varios agentes/ejecuciones. Contra: más piezas; sobreingeniería para el enunciado.
- **Recomendación (analista): A**, porque cumple literalmente «no duplicados» sin impedir correcciones, y se puede ampliar a C aislando la huella en una clase propia.
**Decisión de Miguel:** ✅ **A** (resuelta; ver `DECISIONES.md`). Con A, en CA-8 se envía una 2.ª request.

### AMB-2. Datos inválidos o incompletos del parser
**Qué no está claro.** El enunciado define tipos (`None`/`str yyyy-mm-dd`, `None`/`float`) pero no qué hacer si el parser incumple: fecha mal formada o imposible, importe negativo, cero, `NaN`, texto, claves que faltan o sobran, `dict` vacío. Importa porque «Validar» es un paso explícito y la robustez es criterio.
- **A. Tratar el dato inválido como `None`** (no se actúa, se registra un warning). Pro: el agente nunca se rompe en medio de la conversación. Contra: el error pasa desapercibido sin buen logging.
- **B. Lanzar excepción propia (`ValidationError`)** y que `handle_turn` la gestione o propague. Pro: errores explícitos y testeables. Contra: un fallo del parser puede tirar el turno y dejar al usuario sin respuesta.
- **C. Mixto:** claves que faltan = `None`; claves sobrantes se ignoran; valores de tipo/formato inválido se descartan con warning y el turno continúa (la respuesta al usuario siempre se entrega); importe `<= 0` inválido.
- **Recomendación (analista): C**, porque el turno conversacional no debe romperse por datos del parser y nunca se envía una acción con datos dudosos. (`<= 0` o `>= 0` para el importe también lo cierra Miguel aquí.)
**Decisión de Miguel:** ✅ **C**, importe > 0 (resuelta; ver `DECISIONES.md`).

### AMB-3. Qué significa «normalizar» cada campo
**Qué no está claro.** El enunciado pide «normalizar» sin definirlo. Candidatos: `commitment_date` (quitar espacios, aceptar solo ISO, ¿convertir a `date`?, ¿fecha pasada permitida?), `committed_amount` (redondeo a 2 decimales, `int`→`float`, string numérico), `request` (`strip`, cadena vacía o solo espacios = `None`, colapsar espacios).
- **A. Normalización mínima:** `strip` en textos; `""` → `None`; `int` → `float`; fecha validada con `datetime.date.fromisoformat` y devuelta como `str` ISO. Pro: predecible y fácil de explicar. Contra: no cubre importes en texto ni redondeo.
- **B. Normalización amplia:** A + aceptar importes en texto («150,50»), redondear a 2 decimales, rechazar fechas pasadas. Pro: más tolerante. Contra: añade reglas de negocio que el enunciado no pide; riesgo de errores.
- **C. Normalización por campo mediante objetos/funciones reutilizables** (cada agente declara su esquema). Pro: extensible. Contra: más estructura (puede combinarse con A o B; es una decisión de diseño más que de reglas).
- **Recomendación (analista): A (reglas) con C (forma)**, porque se limita a lo que el enunciado exige y no inventa reglas de negocio. Fecha pasada: aceptarla (el enunciado no la prohíbe).
**Decisión de Miguel:** ✅ **reglas B + forma C**: fechas pasadas rechazadas (hoy vale), importe en texto convertido (punto o coma sin ambigüedad) y redondeado a céntimos (resuelta; ver `DECISIONES.md`).

### AMB-4. Qué pasa si la petición HTTP simulada falla (no 200)
**Qué no está claro.** Solo se dice que «si las peticiones son exitosas, el endpoint devuelve un 200 OK». Nada sobre fallos, reintentos o excepciones. Interactúa con el control de duplicados: ¿una acción fallida cuenta como enviada?
- **A. Lanzar excepción propia (`IntegrationError`)** y NO marcar como enviada. Pro: explícito, permite reintentar en un turno posterior. Contra: `handle_turn` debe decidir si propaga o captura.
- **B. Devolver un resultado (`ActionResult` con estado) sin excepciones**, no marcar como enviada. Pro: el flujo no se rompe; fácil de testear. Contra: el llamante puede ignorar el error.
- **C. Reintentos automáticos con límite.** Pro: robusto. Contra: complejidad no pedida (y el simulador no tiene fallos reales).
- **Recomendación (analista): B**, porque mantiene la respuesta al usuario aunque falle la integración, sin comerse el error, y no marcar como enviada permite reintentar naturalmente en el turno siguiente.
**Decisión de Miguel:** ✅ **B + C** (resultado sin excepción + 3 intentos configurables, solo 5xx, espera creciente, `Idempotency-Key`; ver `DECISIONES.md`).

### AMB-5. Firma y valor de retorno de `handle_turn`
**Qué no está claro.** El enunciado no dice qué parámetros recibe (¿el mensaje del usuario? ¿el historial? ¿nada?) ni qué devuelve (nada, la respuesta `str`, un resultado de turno). Importa porque es la API pública y lo más preguntado.
- **A. Sin parámetros; devuelve `str`** (la respuesta). Pro: encaja con «Obtener una respuesta del usuario»; mínimo. Contra: los modelos simulados guardan toda la entrada; se pierde información de la acción.
- **B. Sin parámetros; devuelve un objeto `TurnResult`** (`reply: str`, `action_executed: bool`/resultado, datos normalizados). Pro: testeable y extensible, observable. Contra: más tipos.
- **C. Recibe el mensaje del usuario (`handle_turn(user_message)`) y devuelve `str`/`TurnResult`.** Pro: realista (los modelos reciben input). Contra: el enunciado no lo menciona; los modelos simulados no lo necesitarían.
- **Recomendación (analista): B**, porque deja observable qué hizo el turno sin tocar la firma del enunciado; la entrada por parámetro (C) solo si Miguel quiere más realismo.
**Decisión de Miguel:** ✅ **B**, sin parámetros (resuelta; ver `DECISIONES.md`).

### AMB-6. Cómo se modela el «estado interno» de los modelos simulados
**Qué no está claro.** «Contienen toda la información necesaria en su estado interno». No se dice si es un guion de respuestas por turno, valores fijos o aleatorios, ni si `ParserModel` es una clase única que devuelve cualquier `dict`. Importa porque determina la testabilidad.
- **A. Guion (script) por turnos:** el modelo se construye con una lista de respuestas/`dict` y devuelve la siguiente en cada llamada. Pro: determinista, ideal para tests multi-turno y duplicados. Contra: hay que decidir qué pasa al agotar la lista.
- **B. Valor fijo por instancia** (siempre devuelve lo mismo). Pro: trivial. Contra: no permite probar cambios entre turnos.
- **C. Una `Protocol`/ABC `ConversationModel` y `ParserModel` y una implementación simulada configurable.** Pro: permite luego un modelo real. Contra: el enunciado dice que no hacen falta subclases; puede contradecirlo o ser sobreingeniería.
- **Recomendación (analista): A**, porque es determinista y cubre el requisito de duplicados entre turnos; C se evita para respetar «no hacen falta subclases».
**Decisión de Miguel:** ✅ **A**; al agotarse el guion se lanza un error (resuelta; ver `DECISIONES.md`).

### AMB-7. Headers adicionales del parser: nombres y formato
**Qué no está claro.** «Considerar como headers adicionales los datos devueltos por el ParserModel con los mismos nombres». ¿Se envían todos los datos devueltos (también `None`)? ¿Valores `str`? ¿Con nombres tal cual (`commitment_date`) o con prefijo `X-`? ¿Qué `Content-Type`? Los headers HTTP solo admiten texto.
- **A. Nombres tal cual, valores convertidos a `str`, solo claves con valor no nulo.** Pro: literal con «los mismos nombres». Contra: guiones bajos en headers son poco habituales y algunos servidores los descartan.
- **B. Nombres tal cual, todas las claves** (`None` → `"None"`/vacío). Pro: literal total. Contra: ruido y valores sin sentido.
- **C. Prefijo `X-` / guiones.** Pro: convención HTTP. Contra: contradice «los mismos nombres».
- **Recomendación (analista): A** más `Content-Type: application/json`, porque respeta el nombre literal y evita enviar nulos; la conversión a `str` es obligada. (Se asume que los datos son los **normalizados**, no los crudos; Miguel debe confirmarlo.)
**Decisión de Miguel:** ✅ **A** + `Content-Type: application/json`; valores normalizados, solo campos declarados, no ASCII codificado (resuelta; ver `DECISIONES.md`).

### AMB-8. Idioma del código, comentarios y README
**Qué no está claro.** El enunciado está en español, pero los nombres que impone están en inglés. No se indica idioma de entrega.
- **A. Código y nombres en inglés; docstrings, comentarios y README en español.** Pro: convención de la industria y coherente con los nombres del enunciado; README en el idioma del evaluador. Contra: mezcla de idiomas.
- **B. Todo en español (salvo nombres impuestos).** Pro: coherencia con el enunciado. Contra: identificadores con tildes/ñ y mezcla con los nombres en inglés.
- **C. Todo en inglés.** Pro: estándar. Contra: puede restar claridad si el evaluador lee en español.
- **Recomendación (analista): A**, por convención y coherencia con los nombres impuestos, manteniendo el README claro para el evaluador.
**Decisión de Miguel:** ✅ **A** (resuelta; ver `DECISIONES.md`).

### AMB-9. Librerías permitidas y tests
**Qué no está claro.** No hay restricción de dependencias ni se menciona explícitamente que haya que entregar tests (aunque pide código «testeable»). Importa porque afecta al empaquetado, y la validación (pydantic) o el HTTP (httpx/requests) simplificarían el código.
- **A. Solo biblioteca estándar en `src` (`dataclasses`, `abc`, `typing`, `datetime`, `logging`), `pytest` solo para tests.** Pro: cero fricción, el README no requiere instalación; fácil de explicar. Contra: validación manual.
- **B. `pydantic` para validación/normalización.** Pro: menos código y muy legible. Contra: dependencia; menos visible la lógica propia.
- **C. A + `httpx`/`requests` solo para construir la `Request` sin enviar.** Pro: objetos conocidos. Contra: dependencia para algo que no se ejecuta.
- **Recomendación (analista): A**, porque la validación es pequeña y el evaluador ve la lógica propia; tests con `pytest` incluidos.
**Decisión de Miguel:** ✅ **A** (+ `ruff`); `pydantic`/`httpx` solo si se ven necesarios (resuelta; ver `DECISIONES.md`).

### AMB-10. Cuerpo (body) de las requests y cómo se «simula» la integración
**Qué no está claro.** El enunciado exige construir «URL, headers y body» pero no da el esquema del body ni cómo se simula (¿se devuelve un objeto respuesta? ¿se loguea?). Importa porque es lo que los tests comprueban.
- **A. Body JSON con los mismos campos normalizados** (`{"commitment_date": "2026-12-01", "committed_amount": 150.0}`; `{"request": "..."}`), y un cliente simulado que guarda la request y devuelve `Response(status_code=200)`. Pro: simple, coherente con los nombres del parser. Contra: el esquema real del backend es una suposición.
- **B. Body con envoltorio** (`{"data": {...}}`) o con metadatos (id de conversación, timestamp). Pro: realista. Contra: inventa campos no pedidos.
- **C. Variante de A que además imprime/loguea la request.** Pro: demostrable en consola. Contra: ruido.
- **Recomendación (analista): A**, porque no inventa campos y hace la verificación en tests directa (el cliente simulado expone las requests enviadas).
**Decisión de Miguel:** ✅ **A**: cliente falso configurable para fallar y log con `logging` (resuelta; ver `DECISIONES.md`).

### AMB-11. Orden de pasos dentro del turno y fallos de modelos
**Qué no está claro.** El enunciado lista la secuencia (responder, parsear, validar, ejecutar) pero no si el orden es obligatorio, ni qué ocurre si `answer_user` o `parse_data` lanzan excepción.
- **A. Orden fijo del enunciado; excepción de un modelo se propaga.** Pro: simple. Contra: sin respuesta si falla el parser.
- **B. Orden fijo; si falla `parse_data`, se entrega la respuesta y no se actúa (warning).** Pro: robusto. Contra: oculta errores.
- **C. Template Method** con pasos sobrescribibles. Pro: extensible. Contra: más estructura (es diseño; puede aplicar a A o B).
- **Recomendación (analista): orden fijo + B**, porque la respuesta al usuario es la prioridad y no se actúa ante la duda.
**Decisión de Miguel:** ✅ **orden fijo + B** en los dos fallos, con respuesta de emergencia (resuelta; ver `DECISIONES.md`).
**Para la arquitectura:** la respuesta se genera antes de enviar la acción; si el envío falla tras los reintentos (AMB-4), el cliente ya puede haber recibido «apuntado». Decidir cómo se trata.

### AMB-12. Acumulación de datos entre turnos (cobros)
**Qué no está claro.** Si en el turno 1 se obtiene la fecha y en el turno 2 el importe, ¿se combinan? El enunciado dice «cuando ambos valores sean distintos de None», sin precisar si es dentro de un mismo turno o acumulado en la conversación.
- **A. Evaluar solo cada turno por separado** (ambos valores en el mismo `dict`). Pro: sin estado extra; literal. Contra: obliga al parser a repetir datos ya dados.
- **B. Acumular el último valor no nulo de cada campo durante la conversación.** Pro: natural en una conversación real. Contra: más estado; un valor antiguo puede combinarse con uno nuevo no relacionado.
- **Recomendación (analista): A**, porque es lo que dice el enunciado de forma literal y el parser «contiene toda la información»; B solo si Miguel prioriza el realismo.
**Decisión de Miguel:** ✅ **A** (resuelta; ver `DECISIONES.md`).

## 6. Criterios de evaluación de Ringr (copiados del enunciado)

- Conocimientos de programación orientada a objetos.
- Aplicación y justificación de las mejores prácticas en desarrollo de código.
- Limpieza del código y selección de la estructura del proyecto.
- Claridad en la exposición del fichero readme.

Además, el enunciado indica: «nos importan mucho más las decisiones técnicas que tomes y los razonamientos que te lleven a ellas que la solución concreta».

## 7. Fuera de alcance

- Llamadas HTTP reales: «Las integraciones HTTP no deben ejecutarse realmente».
- Llamadas reales a LLMs: «Tampoco debes implementar llamadas reales a LLMs, vale con que simules ambos objetos.»
- Subclases de `ConversationModel` y `ParserModel`: «no hacen falta subclases de estos».
- Otros códigos de respuesta del endpoint: el enunciado solo asume 200 OK en éxito (su gestión es AMB-4).
- Más agentes que `DebtAgent` y `AssistanceAgent`: solo se pide que el diseño permita añadirlos.
