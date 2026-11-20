# Ronda 105f: complemento final con la intención real de AGENTE UDL

**Alcance:** validación técnica sin cambios de motor, intenciones, documentos, fragmentos, índice, casos de Calidad ni configuración de reranking. P1 sin cambios; incidente 493c8033 abierto.

**Reproducción:** `experimento_post_p1.py --intenciones real --compartidos documento_completo`.
- **Corpus:** los cinco archivos reales de LOTE01.
- **Políticas confirmadas:** planes `por_encabezado`, compartidos `documento_completo`, 500/60/80; 29 fragmentos indexados, igual que el proyecto.
- **Intención `consultar_requisitos_bachillerato`:** descripción y los 8 + 8 ejemplos reales; datos opcionales `campus` (aquí `plantel`) y `nivel_academico`; prioridad 50; sin datos obligatorios.
- **Demás intenciones:** las supuestas (no se proporcionaron).
- **Modelos y procedimiento:** reales, r105b sin reranking.
- **Salidas:** `resultados_intencion_real.json`, `salida_detalle_intencion_real.txt`, `resultados_sintetico_r102.txt`.

**Estado del repositorio:** el commit documental `695149e` ya está en `origin/main` (verificado con `git fetch` y `git branch -r --contains`).

## 1. La reproducción coincide con lo observado en el Simulador

| UDL-BACH-003 (r105b) | Observado por NEXOM | Reproducción |
|---|---|---|
| 1.º | Torres Landa, «Información general», búsqueda #1, afinidad **0.18** | Torres Landa, «Información general», búsqueda #1, afinidad **0.19** |
| 2.º | `requisitos_ingreso.md`, búsqueda #2, afinidad **0.57** | requisitos, búsqueda #2, afinidad **0.64** |
| Intención, confianza, acción | consultar_requisitos_bachillerato, 0.789, responder | consultar_requisitos_bachillerato, **0.789**, responder |

**De dónde sale la afinidad de «Información general»:** la descripción real contiene «requisitos **generales**» e «**información** institucional autorizada». Las raíces «gener» e «infor» coinciden con las dos palabras del título. Es una coincidencia de vocabulario genérico, no de tema.

**Consulta de documentos con r105b:** el fragmento de requisitos queda fuera del top 5. El orden reproducido es:
1. y 2. los puentes «Información compartida»;
3. y 4. «Información general»;
5. un fragmento solo-YAML.

## 2. Comparación solicitada

Configuración real; 14 consultas de LOTE01; tres conteos de tokens (subpalabras, palabras, x3), con resultados **idénticos** en los tres. MRR: 1.000 = fragmento correcto siempre en primer lugar; «—» = fuera del top 5.

| Variante | MRR | UDL-BACH-003 (R1) | Documentos (R2) | R3 | Resto (11 consultas) |
|---|---|---|---|---|---|
| **r105b** | 0.857 | 2.º | — | 2.º | 1.º |
| **V** | **1.000** | **1.º** | **1.º** | 1.º | 1.º |
| **Y + R** | 0.964 | 2.º | 1.º | 1.º | 1.º |
| **V + Y + R** | **1.000** | **1.º** | **1.º** | 1.º | 1.º |
| (V + R) | 1.000 | 1.º | 1.º | 1.º | 1.º |
| (V + Y) | 1.000 | 1.º | 1.º | 1.º | 1.º |

**Respuesta a los puntos 3 y 4:**
- **V mantiene `requisitos_ingreso.md` en 1.º** en UDL-BACH-003 y en la consulta de documentos.
- **Con V + Y + R**, en la consulta de documentos el fragmento con los requisitos (1.º) queda por delante de los dos puentes (6.º y posteriores).
- **Y + R sin V no corrige UDL-BACH-003.**

**Otras estrategias de fragmentación** (con la intención real; ninguna consulta empeora respecto de r105b con V + Y + R):

| Configuración | r105b | V | Y + R | V + Y + R |
|---|---|---|---|---|
| Compartidos `por_encabezado` | 0.696 | 0.696 | **0.905** | 0.857 |
| Todo `por_tamanio` | 0.788 | 0.871 | 0.788 | **0.871** |

**Nota sobre `por_encabezado`:** con esta estrategia, V + Y + R mejora r105b pero queda por debajo de Y + R. En la consulta de documentos, R2 queda 3.º con V + Y + R y 1.º con Y + R. La causa: la sección con la respuesta se titula «Contenido» (afinidad 0), y cualquier fragmento con afinidad, como «Información general» (0.19), pasa por delante. V no cambia eso. Corresponde a la afinidad heredada de encabezados superiores (P, Ronda 104), fuera de este alcance. **No afecta a AGENTE UDL**, cuyos compartidos son documento completo.

## 3. Reconocimiento de intención y decisiones (punto 5)

**Por diseño, V, Y y R no pueden cambiarlos.** Actúan después de decidir: V e Y al reordenar por afinidad, y R entre la búsqueda y ese reordenamiento. Solo cambian el **orden** de los fragmentos entregados.
- **[COD]** No intervienen la intención, la confianza, los datos detectados, los filtros, los guardrails ni la acción.

**Comprobado [EXP]:** en las cinco configuraciones medidas, las **14 consultas** tienen la misma intención, acción, confianza y filtros en todas las variantes que en r105b (`resultados_intencion_real.json`, campo `decisiones`).

**Orden de las demás consultas:** las 11 restantes siguen en 1.º en la configuración real con todas las variantes. Puede cambiar el orden de los fragmentos que **no** son el correcto (posiciones 2 a 5), algo propio de cualquier cambio de reordenamiento. Los casos de Calidad de NEXOM lo medirán.

## 4. Regresión sintética de la Ronda 102 (punto 6)

**Corpus:** se reprodujo con el corpus sintético de la Ronda 102 (`corpus_sintetico_r102/`): planes con una sección «Requisitos de ingreso» que solo dice que los requisitos están en `requisitos_ingreso.md`.

| Variante | `requisitos_ingreso.md` en la consulta de requisitos |
|---|---|
| r105b | 1.º |
| **V** | **3.º**, la regresión de la Ronda 102 vuelve |
| **V + Y** | **3.º** |
| V + R | 1.º |
| V + Y + R | 1.º |
| Y + R | 1.º |

Resultados iguales con la intención real y con la supuesta.

**Explicación [COD]:**
- Con V, la afinidad cuenta por su valor. Las dos secciones puente, con título exacto «Requisitos de ingreso» (afinidad 1.00), superan al documento (0.86, búsqueda #1).
- R reconoce esas secciones como puentes (cortas y que nombran `requisitos_ingreso.md`) y coloca su destino por delante.

**Conclusión:** **V solo es seguro si R está activa.** Con R desactivada por defecto, el criterio «Protección contra la regresión de la Ronda 102» **no se cumple**.

## 5. Respuestas expresas

1. **¿Se mantiene la recomendación V + Y + R?** Sí. Es la única combinación medida que cumple a la vez:
   - UDL-BACH-003 en 1.º;
   - requisitos antes de los puentes;
   - ninguna consulta de LOTE01 peor que r105b, en tres estrategias y tres conteos;
   - intención y decisiones sin cambios;
   - protección del patrón de la Ronda 102.

   V sola o V + Y reabren la Ronda 102. Y + R no corrige UDL-BACH-003.
2. **¿Qué se activa por defecto?** **V, Y y R juntas**, como un solo procedimiento nuevo (p. ej. `r106`). Para revertir, un ajuste por proyecto «Reordenamiento conversacional» con dos valores:
   - **r106** (predeterminado);
   - **r105b** (anterior: desactiva los tres a la vez).

   No se recomienda un interruptor independiente para R: desactivarla dejando V activa reabre la Ronda 102.
3. **¿R desactivada por defecto permite cumplir los criterios?** No. O bien R activa, o bien V también desactivada; esto último deja UDL-BACH-003 sin corregir. Por eso R debe estar activa siempre que V lo esté. **Esto corrige la recomendación 3 de la Ronda 105e** (`Complemento_politicas_reales.md`), que proponía R desactivada por defecto.
4. **Riesgos pendientes:**
   - Las **demás intenciones** de AGENTE UDL son supuestas; la validación con los 14 casos reales de Calidad lo cubrirá.
   - **Compartidos fragmentados por encabezado:** V + Y + R (0.857) queda por debajo de Y + R (0.905), aunque sobre r105b. La mejora corresponde a P (Ronda 104), fuera de alcance.
   - **R puede traer fragmentos poco pertinentes** de la fuente referida («Procedencia»); límites: 2 por fuente y 5 por consulta.
   - **La escala de V** (afinidad/61) equipara una afinidad de 1.0 con el primer puesto de la búsqueda. Es coherente con la fórmula actual, pero conviene vigilarla con más proyectos.
   - **Sin reranking (P1):** los resultados no dependen del cross-encoder.
5. **Alcance exacto de la implementación propuesta:**
   - **V:** en `domain/conversational/section_affinity.py`, nueva combinación por valor: 1/(61 + puesto) + afinidad/61, empates por puesto en la búsqueda. Se usa en `SimulateConversation._search_and_filter`, solo en la rama con filtros, donde hoy se aplica la afinidad.
   - **Y:** en `affinity_title`, un fragmento sin texto fuera del YAML tiene título vacío (afinidad 0).
   - **R:** resolución de referencias según el diseño de la Ronda 104b (`prototipo_referencias.py`): puente ≤ 80 palabras; destino con contenido; 2 por fuente y 5 por consulta; sin recursión; restricción final; trazado `referenced_from`. Con el ajuste de la Ronda 105: un título sin extensión ni forma de identificador no cuenta.
   - **Configuración y trazado:** ajuste de proyecto «Reordenamiento conversacional» (r106 / r105b), con migración aditiva nullable de la tabla de proyecto; `RETRIEVAL_PIPELINE = "r106"`; trazado de la combinación y de las referencias en el Simulador y en `execution`.
   - **Sin cambios en:** P1 (reranking), índice, documentos, fragmentos, intenciones, casos de Calidad, M, P3, P4 y P.

**Pruebas necesarias:**
1. **Unitarias:**
   - V (incluido el empate exacto de UDL-BACH-003);
   - Y;
   - R (los 15 casos borde de la Ronda 104b, más el ajuste de títulos);
   - las pruebas de afinidad de las Rondas 91 y 102, que deben seguir pasando.
2. **Integración con LOTE01 real:**
   - configuración real con la intención real de requisitos: R1 y R2 en 1.º;
   - otras estrategias sin regresión respecto de r105b;
   - corpus sintético de la Ronda 102 con requisitos en 1.º.
3. **Decisiones:** intención, confianza, acción y filtros idénticos a r105b en las 14 consultas.
4. **Equivalencia Simulador–Runtime** con la misma instantánea, en r106 y r105b; reranking P1 sin cambios.
5. **NEXOM, sobre la corrida base `085fe5a5-…`:**
   - los 14 casos de Calidad: Recall@3 100 %, MRR ≥ 0.90, UDL-BACH-003 corregido, ningún caso empeorado;
   - lo mismo con el ajuste en r105b, como control de reversión.
