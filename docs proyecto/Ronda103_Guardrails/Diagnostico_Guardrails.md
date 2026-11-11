# Ronda 103: canalización de «¿Cuál es la mejor pizza de León?» (diagnóstico)

**Caso.** AGENTE UDL, LOTE01_Bachillerato, instantánea v1. El Simulador y el Runtime coinciden:
- intención `solicitar_asesor_admisiones`, confianza 0.206;
- reglas activadas: `aclarar_baja_confianza` y `canalizar_solicitud_asesor`;
- decisión: Canalizar.

**Alcance.** Diagnóstico sin cambios de código. Reproducción en `diagnostico_guardrails.py`, con salida en `salida_diagnostico.txt`:
- el motor real (`SimulateConversation`, el mismo de `POST /messages`);
- los tres guardrails exactamente como los reportó NEXOM;
- los cinco documentos reales de LOTE01 y el modelo de embeddings real.

**Limitación de la reproducción.** No se tiene el texto real de la intención `solicitar_asesor_admisiones`, así que se usó una versión supuesta. Por eso el mecanismo se demuestra con el contexto exacto del caso: intención de asesor y confianza 0.206.

**Resultado:** reproduce las mismas reglas activadas y la misma decisión que observó NEXOM.

## A. Precedencia entre guardrails (comportamiento actual)

Código: `domain/conversational/rule_evaluation.py::select_firing_action` y `ACTION_SEVERITY`.

1. **Se evalúan todas las reglas activas.** Una regla dispara si se cumplen **todas** sus condiciones. Una regla sin condiciones dispara siempre.
2. **Entre las que disparan, gana la acción más severa:** canalizar (3) > abstenerse (2) > aclarar (1) > responder (0).
3. **El campo «Prioridad» de los guardrails no interviene en la decisión.** Se guarda, se edita y aparece en el informe de entregables, pero el motor no lo usa. El Manual (8.3) dice solo «Ajustar Prioridad (0 a 100)», sin aclarar que no tiene efecto. **Es un defecto de documentación y de interfaz.** (La prioridad de las **intenciones** sí se usa: desempata intenciones con igual margen.)
4. **Luego, la «regla de oro»:** si falta un dato mínimo, la decisión nunca es más leve que aclarar. Se toma lo más severo entre la decisión de las reglas y aclarar.

**Aplicado al caso.** Con 0.206 disparan `aclarar_baja_confianza` (aclarar) y `canalizar_solicitud_asesor` (canalizar), y gana canalizar por severidad.

**Consecuencia más importante.** Aunque la confianza fuera **menor que 0.20**, el resultado seguiría siendo canalizar: con 0.15 también dispara `abstenerse_confianza_insuficiente`, pero canalizar es más severo. Con la configuración actual, **la regla de abstención nunca puede impedir una canalización.**

| Contexto (intención de asesor) | Reglas que disparan hoy | Decisión hoy |
|---|---|---|
| confianza 0.206 (caso reportado) | aclarar_baja_confianza, canalizar_solicitud_asesor | **canalizar** |
| confianza 0.15 | aclarar_baja_confianza, abstenerse_confianza_insuficiente, canalizar_solicitud_asesor | **canalizar** |
| confianza 0.60 | canalizar_solicitud_asesor | canalizar |

## B. Condiciones compuestas

**Y (AND): ya existe.** Cada línea del cuadro «Condiciones» es una condición, y todas deben cumplirse. Así lo documenta el Manual (8.3.1). La regla que pide NEXOM se escribe en **dos líneas**:

```
intencion = solicitar_asesor_admisiones
confianza >= 0.45
```

Ya hay precedentes en el proyecto histórico de Bachillerato. La regla `abstenerse_fuera_de_dominio` usa dos líneas: `intencion = consultar_areas_programa` y `confianza < 0.15`.

**O (OR): no existe** (documentado). Para «esto o aquello» se crean dos reglas.

**Defecto encontrado: la interfaz acepta una condición escrita en una sola línea que el motor nunca cumple.** Si se escribe:

```
intencion = solicitar_asesor_admisiones AND confianza >= 0.45
```

1. **Cómo se interpreta.** La línea se separa en el primer operador. Queda campo `intencion`, operador `=` y valor `solicitar_asesor_admisiones AND confianza >= 0.45`.
2. **Qué valida la interfaz.** El campo existe, así que no hay error ni advertencia, y la regla se guarda.
3. **Resultado.** La condición **nunca se cumple**: la regla queda muerta sin aviso. Es justo el riesgo que NEXOM pidió evitar.

## C. Canalización con confianza 0.206

El motor no tiene ningún mecanismo general que proteja las acciones sensibles frente a coincidencias débiles:
- **Las reglas solo ven lo que dicen sus condiciones.** `canalizar_solicitud_asesor` solo pide `intencion = solicitar_asesor_admisiones`, así que dispara con cualquier confianza.
- **Las reglas de confianza baja no la pueden detener.** Proponen aclarar o abstenerse, que son menos severas que canalizar (punto A).

**El Manual empuja a esta configuración.** Su ejemplo «Canalizar a un asesor: Acción canalizar, condición intencion = Solicitar asesor humano» no incluye una condición de confianza. Es el mismo patrón que tiene el proyecto.

## D. Consultas fuera de alcance

`match_intent` asigna **siempre** la intención con mayor margen (similitud con su mejor ejemplo positivo menos la de su mejor ejemplo negativo) si ese margen es mayor que 0. No hay un umbral mínimo: solo devuelve «ninguna intención» si todos los márgenes son ≤ 0, y con embeddings eso casi nunca pasa.

Por eso «pizza» se asigna a alguna intención con confianza baja: en v1, la de asesor con 0.206; en la reproducción, otra intención con 0.131. Después solo los guardrails deciden.

**Confianza observada en la reproducción (11 consultas):**

| Grupo | Confianza |
|---|---|
| Fuera de alcance | 0.13 a 0.40 («¿Qué clima hará mañana en León?» llega a 0.40) |
| Asesor explícito | 0.60 a 1.00 |
| Documentales | 0.70 a 1.00 |

El umbral 0.45 que NEXOM ya usa separa los tres grupos en esta muestra. Con las intenciones reales hay que confirmarlo.

## Clasificación del caso (punto 3 de la solicitud)

1. **Problema de configuración (causa directa).** La regla de canalización no exige confianza, y como canalizar es lo más severo, ninguna regla de confianza baja puede frenarla.
2. **Defectos de documentación e interfaz:**
   - el campo «Prioridad» de los guardrails no tiene efecto y no se dice;
   - el Manual no explica la precedencia por severidad;
   - el ejemplo del Manual de «canalizar a un asesor» no tiene condición de confianza;
   - la condición «… AND …» en una línea se acepta y nunca se cumple.
3. **Limitación de diseño (no es un defecto de evaluación).** No hay un umbral mínimo para reconocer una intención, ni una protección general de las acciones sensibles ante coincidencias débiles.
4. **No es un defecto de consistencia.** El Simulador y el Runtime usan el mismo motor y coinciden, como era de esperar.

## Alternativa recomendada (antes de implementar nada)

**1. Corrección de configuración (resuelve el caso y no requiere código):**
- agregar a `canalizar_solicitud_asesor` una segunda línea, `confianza >= 0.45`;
- publicar una instantánea nueva (v2): el Runtime lee la configuración de la instantánea publicada.

| Contexto | Hoy | Con la alternativa |
|---|---|---|
| asesor, 0.206 (pizza) | canalizar | **aclarar** |
| asesor, 0.15 | canalizar | **abstenerse** |
| asesor explícito (0.60 a 1.00) | canalizar | canalizar |
| documentales | responder | responder (sin cambios) |

Así se cumplen los cuatro escenarios esperados de la sección 5 de la solicitud. Antes de publicar, conviene comprobar en el Simulador que las solicitudes explícitas reales superen 0.45. Si alguna forma legítima queda por debajo, se agrega como ejemplo positivo de la intención.

**2. Ajustes del motor propuestos** (pequeños; no cambian la decisión de ningún proyecto existente):
- **E1. Validar las condiciones compuestas en una sola línea.** Si el valor de una condición contiene un conector (` AND `, ` OR `, ` Y `, ` O `, `&&`, `||`) seguido de otro campo y operador, no se guarda la regla. La interfaz mostraría: «escriba cada condición en su propia línea; todas deben cumplirse (Y); para O cree dos reglas». En el Simulador se avisaría, además, de las reglas ya guardadas con ese problema.
- **E2. Transparencia de la precedencia:**
  - el reporte del Simulador y del Runtime diría qué regla decidió la acción y por qué («canalizar: acción más severa entre las reglas activadas»);
  - el campo «Prioridad» de los guardrails pasaría a llamarse «Prioridad (informativa; no cambia la decisión)»;
  - se corregirían el Manual (8.3 y 8.3.1, con la precedencia por severidad) y su ejemplo de canalización, agregándole la línea `confianza >= 0.45`.
- **E3. Pruebas automatizadas** de:
  - canalización válida;
  - asesor con baja confianza → aclarar;
  - asesor bajo el umbral de abstención → abstenerse;
  - coincidencia simultánea (aclarar + canalizar, abstenerse + canalizar);
  - consulta documental sin cambios;
  - la misma decisión en el Simulador y en `POST /messages`;
  - el rechazo de «… AND …» en una sola línea.

**3. Opciones que no recomiendo ahora** (cambian la semántica para todos los proyectos o necesitan calibración con datos reales):
- **Usar la «Prioridad» del guardrail para decidir entre acciones distintas.** Con las prioridades actuales del proyecto (80, 90, 69) daría justo lo esperado. Pero cambiaría silenciosamente la decisión de proyectos que hoy confían en la severidad. Si NEXOM lo prefiere, debería ser un ajuste explícito por proyecto, con el valor actual como predeterminado.
- **Un umbral mínimo de reconocimiento de intención por proyecto**: por debajo, «ninguna intención» → abstenerse, antes de evaluar guardrails, así que ninguna regla podría canalizar. Responde a C y D de forma general. Conviene evaluarlo con un conjunto real de consultas fuera de alcance y válidas, porque en la muestra hay consultas fuera de alcance con 0.40 y el margen con las válidas es estrecho.

## Punto 6: ¿configuración o motor?

- **Basta con la configuración:** el caso y el criterio de aceptación se resuelven con la segunda condición en la regla de canalización y la publicación de la v2. Simulador y Runtime quedan consistentes porque usan el mismo motor y la misma instantánea.
- **Requieren actualizar RAG Studio:** E1, E2 y E3 (no cambian decisiones; previenen el error y lo hacen visible). La misma actualización llega al Runtime de RAG Studio.
- **Requerirían una decisión de NEXOM:** la precedencia por prioridad y el umbral mínimo de intención.
