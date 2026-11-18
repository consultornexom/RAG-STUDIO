# Ronda 105: diagnóstico técnico del incidente 493c8033

**Alcance:** diagnóstico sin cambios de código, documentos, metadatos, índices ni evidencias.

**Experimentos:** se hicieron en memoria, sobre copias de los cinco archivos de LOTE01 (verificados por hash) y de dos proyectos de prueba (`.agentproj` extraídos a una carpeta temporal).

**Clases de evidencia** (cada afirmación lleva la suya):
- **[OBS]**: observación de NEXOM, no verificada por el consultor.
- **[COD]**: verificado en el código del repositorio.
- **[EXP]**: medido en un experimento controlado con textos reales y modelos reales.
- **[SUP]**: reproducción con supuestos (intenciones y metadatos no reales).
- **[HIP]**: hipótesis.

## 1. Conclusión

1. **[COD] El Runtime de RAG Studio nunca ha podido aplicar reranking.** En los 23 commits del repositorio (desde la línea base `74b132a`, 2026-10-14, hasta `11b7bb5`), `interfaces/api/runtime_context.py` construye su `RagService` sin reranker. El motor conversacional decide «reranking = sí hay modelo», así que en el Runtime la respuesta siempre es «no».
   - Antes de la Ronda 102: `rerank=self._rag.has_reranker`.
   - Desde la Ronda 102: «Automático» = si hay modelo; «Activado» sin modelo solo avisa.
   - Solo la app de escritorio (`app/bootstrap.py`) crea el modelo, y por eso el Simulador sí reordena.
   - Lo confirmó la validación de la Etapa 0 de NEXOM: modelo no disponible, `applied = false`.
2. **La premisa de la sección 4 del informe** («el incidente histórico registró reranking aplicado») **no puede provenir de un registro del Runtime de RAG Studio**:
   - antes de la Etapa 0 no existía ningún campo que registrara el reranking (ni en `runtime.db` ni en la respuesta);
   - el Runtime no tenía modelo.

   **Hay que identificar de dónde sale esa afirmación** (sección 8). Mientras tanto, se trata como no verificada.
3. **[HIP principal, confianza media-alta] La ejecución histórica corresponde a las condiciones de la prueba B** (sin reranking), y la omisión de `requisitos_ingreso.md` se explica por el mismo mecanismo de competencia de la sección 5, que la prueba B reproduce. La confianza pasa a **alta, confirmada** si:
   - (a) los `score` de la respuesta original (E1) están en el rango de la fusión RRF (0 a ≈0.05), y
   - (b) el código del Runtime del incidente (E4) es uno de los commits del repositorio.

   Si los `score` fueran logits de un cross-encoder, esta hipótesis cae: la respuesta no habría salido de ningún Runtime de RAG Studio conocido.
4. **La diferencia entre la prueba A y el incidente queda explicada por [COD]:** la prueba A se hizo en el Simulador de escritorio, que reordena con el cross-encoder; el Runtime no.

   **Por eso el incidente no puede darse por resuelto con la prueba A.** El Runtime sigue operando como en la prueba B.

## 2. Evidencias utilizadas y limitaciones

| Evidencia | Clase | Uso |
|---|---|---|
| Informe del incidente (consulta, acción, intención, confianza 0.887, v2, ids de puentes y del fragmento de requisitos) | OBS | Hechos del incidente |
| Hallazgos de la investigación de NEXOM (documento presente en la v2, en la base y en Qdrant, validado; `nivel_academico` vinculado y detectado; texto de búsqueda; `r102`) | OBS | Descarta indexación, validación y filtros como causa |
| Pruebas A/B/C (commit `11b7bb5`, huella `f1232d2b6b83`) | OBS | Comparación controlada |
| Historia de `runtime_context.py`, `bootstrap.py` y `simulate_conversation.py` en todos los commits | COD | Sección 1 |
| Textos reales de `requisitos_ingreso.md` y de los planes | COD | Sección 5.1 |
| `experimento_representacion.py` (salida en `salida_experimento_representacion.txt`) | EXP | Secciones 5.2, 5.3 y 6 |
| Reproducciones de las Rondas 102 y 104 | SUP | Orientativas, no del incidente |
| Revisión de dos proyectos de prueba UDL (Prueba A: 5 fuentes, 6 intenciones; Prueba B: 25 programas, 76 fragmentos) | EXP | Generalización (sección 7) |

**Limitaciones de la reconstrucción histórica** (detalle en `docs proyecto/Ronda104_Etapa0_Trazabilidad/Disponibilidad_Evidencias_493c8033.md`):
- **No hay registro del incidente** con commit, reranking, texto de búsqueda ni orden de fragmentos: son anteriores a la Etapa 0.
- **Sin la respuesta original completa (E1)** no se conocen los `score` ni la lista exacta de fuentes.
- **Sin el código del Runtime en ese momento (E4)** no se sabe si corría la Ronda 102 o una anterior. Una versión anterior (afinidad como clave principal, títulos «---») empeora el mismo mecanismo; no cambia la conclusión de la sección 1.

## 3. Comparación histórica

| Aspecto | Incidente (Runtime) | Prueba A (Simulador) | Prueba B (Simulador) | Prueba C (Simulador) |
|---|---|---|---|---|
| Componente | Runtime de RAG Studio | Simulador de escritorio | Simulador | Simulador |
| Código | desconocido (E4) | `11b7bb5` | `11b7bb5` | `11b7bb5` |
| Modelo de reranking disponible | **no** [COD] | sí | sí | sí |
| Reranking aplicado | **no** [COD], salvo que se demuestre otro origen | sí (Automático) | no (Desactivado) | no |
| Texto de búsqueda | «¿Qué documentos necesito para entrar ?» [COD: mismo motor y misma instantánea] | ídem | ídem | ídem |
| Filtro | `nivel_academico = bachillerato` | ídem | ídem | ídem + solo esa fuente |
| Candidatos | pool de 20 de todas las fuentes permitidas | ídem | ídem | solo los fragmentos de `requisitos_ingreso.md` |
| Orden final | RRF + afinidad: como clave principal si el código era anterior a la Ronda 102, combinada si era la 102 | RRF → reranker → afinidad combinada (Ronda 102) | RRF → afinidad combinada | trivial (una sola fuente) |
| `requisitos_ingreso.md` | ausente del top 5 [OBS] | puesto 5 en la búsqueda → 2.º final [OBS] | ausente [OBS] | 1.º [OBS] |

**Condiciones del incidente comparadas con las pruebas:** según [COD], coinciden con la B (sin reranking) y difieren de la A en el único factor que la A cambia. Lo que no se puede comprobar es la versión del código (E4) y los `score` (E1).

## 4. Diferencias entre las tres pruebas

- **A frente a B: un solo factor, el reranking.**
  - Con el cross-encoder, el fragmento de requisitos entra al puesto 5 de los candidatos.
  - Después, la afinidad combinada de la Ronda 102 lo sube al 2.º. Su título «Requisitos de ingreso — Bachillerato UDL» comparte raíces con la intención, y los puentes («Información compartida aplicable a este plantel») tienen afinidad 0.
- **Por qué sin reranking no alcanza el top 5** [COD]. En la combinación RRF de la Ronda 102, un fragmento con puesto *r* en la búsqueda y el mejor puesto de afinidad supera a otro con puesto 1 en la búsqueda y puesto *k* de afinidad solo si *r* < *k*. Sin reranking, el fragmento de requisitos queda muy abajo en la búsqueda (sección 5) y no hay afinidad que lo compense frente a varios fragmentos de los planes con afinidad propia.
- **C:** al restringir a una fuente, el único candidato es el propio documento.
  - Demuestra que está indexado y es recuperable.
  - **No dice nada sobre el orden en la búsqueda general.**
- **A no corrige al Runtime:** el Runtime opera como B (sección 1).

## 5. Competencia entre fragmentos: por qué el puente gana sin reranking

### 5.1 Plano léxico (BM25) [COD sobre los textos reales]

| Término del texto de búsqueda | `requisitos_ingreso.md` | Plan Torres Landa |
|---|---|---|
| «documentos» | 0 | 1, **solo** en el puente: «La aplicabilidad de esos documentos compartidos…» |
| «necesito», «entrar» | 0 | 0 |

**Consecuencia:** en la lista textual de la búsqueda híbrida, los únicos candidatos con coincidencia son los dos puentes. El fragmento de requisitos no entra en esa lista, y en la fusión RRF los puentes suman dos listas y el destino solo una.

### 5.2 Plano semántico [EXP, modelo `paraphrase-multilingual-MiniLM-L12-v2`]

Coseno con el texto de búsqueda «¿Qué documentos necesito para entrar ?»:

| Variante | Coseno |
|---|---|
| Contenido con el título del documento | **0.453** |
| Puente Torres Landa (tal cual) | **0.416** |
| Solo «Contenido» | 0.383 |
| Requisitos sin YAML | 0.356 |
| Puente sin las líneas que nombran archivos `.md` | 0.349 |
| Información general (plan) | 0.329 |
| **Requisitos completo, como se indexa con `documento_completo`** | **0.280** |
| Procedencia (plan) | 0.256 |

### 5.3 Reranker [EXP, `ms-marco-MiniLM-L-6-v2`, entrenado en inglés]

- Con el texto de búsqueda: puente −3.6 > requisitos completo −8.7.
- Con la consulta original («…al bachillerato?»): requisitos completo **+1.8** > puente −5.7.

## 6. Representación documental: hipótesis evaluadas

| Hipótesis | Resultado | Clase |
|---|---|---|
| El encabezado YAML diluye el vector del documento | **Sustentada:** quitarlo sube el coseno de 0.280 a 0.356. **Insuficiente por sí sola:** sigue por debajo del puente (0.416) | EXP |
| El fragmento único `documento_completo` (ámbito, contenido, procedencia) diluye la respuesta | **Sustentada:** solo «Contenido» da 0.383 y con su título 0.453, por encima del puente | EXP |
| Las referencias a archivos favorecen al puente | **Sustentada:** las líneas que nombran `.md` suben el coseno del puente de 0.349 a 0.416, y aportan la palabra «documentos» del plano léxico | EXP |
| El título de sección influye | Influye solo en la afinidad. **[COD]** Antes de la Ronda 102, el título de un `documento_completo` con YAML era «---» (afinidad 0). Desde la Ronda 102 es el primer encabezado. No afecta la búsqueda | COD |
| Quitar del texto el valor filtrado («bachillerato») empobrece la búsqueda | **Sustentada para el reranker** (de −8.7 a +1.8 con la consulta original). En el plano semántico el efecto es menor y mixto | EXP |
| Brecha de vocabulario: la pregunta dice «documentos» y el contenido enumera acta, certificado, CURP y fotografías | **Causa de fondo** de que ninguna señal favorezca el contenido. Es en parte editorial | COD + EXP |

## 7. Generalización: revisión en otros proyectos (sin modificarlos)

Detección de la resolución de referencias R (diseño de la Ronda 104b) sobre dos proyectos de prueba UDL con otros tipos de documento:

| Proyecto | Fuentes | Fragmentos | Puentes detectados | Citas en fragmentos largos | Solo-YAML |
|---|---|---|---|---|---|
| Prueba A (fichas de programa, 6 intenciones) | 5 | 15 | 0 | 0 | 0 |
| Prueba B (25 programas por OCR) | 25 | 76 | 0 | **3, falsos** | 0 |

**Falsos positivos en la Prueba B** [EXP]. Fuentes con títulos cortos sin extensión («fin», «comu») coinciden con palabras del texto: «con el **fin** de», «Psicología **Comu**…».
- Solo aparecieron en fragmentos largos, que R no trata como puentes, así que no habrían tenido efecto.
- **Aun así revelan un defecto del diseño:** el título completo de una fuente no debe contar como referencia si no tiene extensión de archivo ni forma de identificador.

Es exactamente el tipo de regla accidental que NEXOM pidió evitar; se incorpora a la propuesta.

## 8. Lo que impide cerrar la explicación histórica

| Pregunta | Evidencia que la responde | Efecto |
|---|---|---|
| ¿De dónde sale «el incidente registró reranking aplicado»? | El documento, el registro o la herramienta que lo afirma | Si es una inferencia o la configuración del proyecto («Automático»), la premisa cae y se sostiene la hipótesis principal |
| ¿Hubo reranking en la respuesta original? | E1: rango de los `score` | RRF (≤ 0.05) → confirma; logits → la respuesta no vino de un Runtime de RAG Studio conocido |
| ¿Qué código corría? | E4 (`git reflog` o ZIP) | Ronda 102 o anterior: cambia el detalle del orden, no la causa |
| ¿Qué estrategia tenían los compartidos? | E7 sobre el paquete original (NEXOM indica «su fragmento», en singular, compatible con `documento_completo`) | Confirma qué variante de la sección 5 aplica |

**Estado de cierre:**
- La hipótesis principal es compatible con todas las observaciones y con el código.
- **No se puede declarar verificada** sin E1 y sin aclarar el origen de la afirmación sobre el reranking.
- Si esas evidencias no existen, se documentará formalmente como «explicación compatible, no confirmada», con las limitaciones de la sección 2.

## 9. Propuesta de corrección generalizable (para autorización posterior)

| # | Propuesta | Atiende | Estado de la evidencia |
|---|---|---|---|
| P1 | **Misma configuración efectiva de reranking en el Simulador y el Runtime** (Etapa 3; alternativas A/B del diseño de la Ronda 104b) | La discrepancia A frente al incidente | COD: es la diferencia comprobada. La elección A o B sigue pendiente de NEXOM |
| P2 | **Y + R** (diseño de la Ronda 104b) con este **ajuste nuevo**: un título sin extensión ni forma de identificador no cuenta como referencia | La competencia de los puentes (sección 5) | SUP (Ronda 104b: puente detrás de su destino en las 4 configuraciones) + EXP (sección 7) |
| P3 | **El reranker recibe la consulta original**, sin quitar los valores filtrados; los filtros siguen aplicándose a las fuentes | Pérdida de señal al quitar «bachillerato» | EXP en un solo caso. **Debe evaluarse ampliamente antes de proponerse** |
| P4 | **Excluir el encabezado YAML del texto indexado** (vector y BM25), conservándolo como metadato | Dilución por YAML | EXP: mejora parcial (0.280 → 0.356), **insuficiente sola** y obliga a reindexar. No se recomienda como primera medida |
| P5 | **Recomendación editorial (RAG CONTENT STUDIO), no del motor:** vocabulario de las preguntas en las secciones de respuesta (p. ej. «Documentos requeridos») y documentos compartidos fragmentados de modo que el contenido quede con su título | Brecha de vocabulario | COD + EXP |

**Orden recomendado:**
1. Decidir P1: es lo que explica la diferencia entre lo que se prueba en el Simulador y lo que responde el Runtime.
2. Implementar P2 por etapas, desactivada por defecto.
3. Evaluar P3 en el conjunto ampliado.
4. Dejar P4 y P5 como opciones.

## 10. Riesgos de regresión y pruebas necesarias

**Conjunto de evaluación ampliado** (para cualquier propuesta):
- LOTE01: 14 consultas, documentos compartidos con `documento_completo` y con `por_encabezado`;
- el corpus sintético de la Ronda 100 (16 casos, varias estrategias de fragmentación);
- la Prueba A UDL: fichas de programa, 6 intenciones y 4 casos de prueba propios;
- la Prueba B UDL: 25 programas por OCR, sin intenciones; sirve para comprobar que no hay referencias falsas ni cambios en la recuperación;
- consultas nuevas que NEXOM aporte para otros lotes.

**Criterios:**
- ninguna consulta empeora;
- destino por delante del puente;
- ninguna referencia falsa;
- restricciones de fuentes respetadas;
- el mismo resultado en el Simulador y el Runtime con la misma configuración (prueba E2E);
- medición con y sin reranking.

**Riesgos principales:**
- **P1:** cambia el orden del Simulador o del Runtime, según la alternativa elegida.
- **P2:** falsos positivos de referencia (mitigado con el ajuste de la sección 7).
- **P3:** puede cambiar el orden de todas las consultas con filtros cuando hay reranking.
- **P4:** exige reindexar y cambia todos los vectores.

**Validación del incidente:** con E1 disponible, comparar la lista de fuentes original con una ejecución del Runtime en condiciones B sobre una copia de la instantánea, siguiendo el criterio de las cinco condiciones de `Procedimiento_Evidencias_E1_E7.md`.
