# Ronda 100: contexto jerárquico persistido y usado en la recuperación

Base: Ronda 99 (`f8b6f2b`). Origen: hallazgo real de NEXOM en AGENTE UDL - LOTE01_Bachillerato. Los fragmentos [9] y [12] de `bachillerato_torres_landa.md` se llaman ambos «5.º semestre», pero pertenecen a áreas distintas.

**Las cifras de este documento salen de un corpus SINTÉTICO. No son resultados del proyecto AGENTE UDL.** La validación funcional con sus documentos reales queda pendiente; ver la sección 8.

## 1. Decisiones de diseño (sección 4 de la solicitud)

| Punto | Decisión |
|---|---|
| 1. Identificar y persistir la ruta | La estrategia `por_encabezado` calcula, para cada sección, la ruta de encabezados Markdown que la rige (`domain/ingestion/heading_context.py`, la misma lógica que el diagnóstico de la Ronda 99). Se guarda en el fragmento con orden y nivel. Los fragmentos hijos y su fragmento padre comparten la ruta de su sección. |
| 2. Dominio | Nuevo `SectionHeading(level, title)` y `Chunk.section_path: list[SectionHeading]`, vacío por defecto. `Chunk.text` no cambia. Es jerarquía documental: no se mezcla con `parent_chunk_id` (padre e hijos de fragmentación) ni con `inherited_metadata` (metadatos estructurados). |
| 3. Migración | **0023**: `chunk.section_path` TEXT NULL (JSON), sin default ni backfill, con downgrade. NULL se lee como ruta vacía. |
| 4. Índices | El índice vectorial no cambia de representación: la ruta **no** se concatena al texto que va al modelo de embeddings. BM25 se calcula al consultar sobre los fragmentos guardados, así que basta con volver a fragmentar. |
| 5. Motor de recuperación | `domain/rag/hierarchy.py` (funciones puras), `TextSearch`, `HybridSearch` y la entrada del reranker. Ver la sección 2. |
| 6. Instantáneas y Runtime | Ver la sección 6. |
| 7. Pipeline incremental | La huella de política de la Ronda 98 incluye ahora una versión de fragmentador para `por_encabezado` (`ruta-de-encabezados-v1`). Solo las fuentes con esa estrategia se reprocesan, con el motivo «Nueva versión del fragmentador…». Las demás se omiten y no hay reconstrucción global. La huella de fragmentos solo incluye la ruta cuando existe, así que los fragmentos sin ruta conservan su huella. |

**Estructuras irregulares, cubiertas por pruebas:**
- **Niveles omitidos:** `#` seguido de `###` da la ruta `[(1, …), (3, …)]`.
- **Títulos repetidos bajo padres distintos:** cada uno conserva su propia ruta.
- **Preámbulo sin encabezado:** ruta vacía.
- **Secciones subdivididas:** los hijos y el padre comparten la ruta.

La solución es general (reglamentos, manuales, procedimientos): no depende de la estructura de los planes de UDL.

## 2. Cómo usa la búsqueda la jerarquía

1. **Ordinales normalizados** (`ordinal_terms`). «5.º semestre», «5º», «5°», «5to», «5to.», «quinto semestre», «semestre 5» y «5.o semestre» producen todos el mismo término `semestre_5`.
   - **Exige una unidad de periodo:** semestre, cuatrimestre, trimestre, bimestre, grado, año, ciclo o periodo.
   - **Sin falsos positivos:** «artículo 5», «apartado 5», «inciso 5», «6 semestres», «5 semestres», «el semestre 2026», «semestre 10%» y «Cap. 5 o semestre» no producen nada.
   - **Las unidades no se mezclan:** «5.º grado» da `grado_5`, distinto de `semestre_5`.
   - **El texto original no se modifica:** el término canónico se **agrega** al vocabulario de búsqueda.
2. **Búsqueda textual (BM25).**
   - Puntúa el texto del fragmento más los títulos de sus encabezados **superiores** y sus ordinales canónicos; a la consulta también se le agregan sus ordinales.
   - Sin ruta ni ordinales, el documento es exactamente `chunk.text`.
   - Además, la textual ya no devuelve fragmentos que solo contienen su encabezado. Es la misma regla que ya aplicaba la indexación semántica, y explica lo que NEXOM observó: «la búsqueda recuperó fragmentos de encabezado».
3. **Búsqueda híbrida: tercera lista RRF jerárquica.**
   - Usa los mismos candidatos que ya trajeron la semántica y la textual: nunca agrega candidatos ni pasa por encima de los filtros.
   - Los ordena por términos de la consulta presentes en los encabezados superiores, más los ordinales de toda la ruta.
   - Los ordinales cuentan doble, porque separan «5.º» de «6.º».
   - **Solo cuentan términos que distinguen:** se ignora uno que aparece en la ruta de más de la mitad de los candidatos, como el título raíz «Bachillerato».
   - **No cuentan las palabras del título propio**, que ya puntúa BM25. Contarlas favorecía a cualquier sección titulada «Requisitos de ingreso» por encima del documento compartido.
4. **Reranking.**
   - El cross-encoder recibe «ruta\ntexto», solo como entrada de esa consulta.
   - Su orden se fusiona con la lista jerárquica. Sin esa fusión, el reranker, que es un modelo en inglés, deshacía la mejora.
5. **Trazabilidad.**
   - `SemanticSearchResult.hierarchy_terms` registra qué términos de la consulta coincidieron con la ruta.
   - El Laboratorio RAG muestra la ruta completa y `[jerarquía: …]` en cada resultado.
   - `use_hierarchy=False` permite desactivar la señal para comparar.
6. **Filtros estructurados.** Campus, multivalor, tipo documental, vigencia y validación, y acceso se aplican **antes**, como hasta ahora. La jerarquía no los sustituye.

**Alternativas evaluadas y descartadas:**
- Concatenar la ruta al texto que va al modelo de embeddings (lo prohíbe la solicitud, y la Ronda 99 midió que perjudica al semestre).
- Contar las palabras del título propio (regresión en documentos compartidos).
- Contar los términos comunes a todo un documento (regresión: «Requisitos de ingreso» cayó del top 10).
- Usar solo los encabezados superiores (el sexto semestre empeoraba).
- Reranking sin la ruta, o con la ruta pero sin fusión jerárquica (peor que la variante elegida).

## 3. Resultados antes/después (corpus sintético)

**Corpus:**
- dos planes de bachillerato (Torres Landa y Hilario Medina) con la estructura descrita por NEXOM: plantel > plan de estudios > área > semestre, con títulos «5.º/6.º semestre» repetidos bajo dos áreas;
- documentos compartidos con `documento_completo`: requisitos de ingreso, cualidades del aspirante, áreas de formación;
- un reglamento `por_articulo` y un calendario `por_tamanio`.

**Configuración:**
- 14 casos con fragmento esperado verificable: cada fragmento correcto lleva una clave única, y **solo cuenta como acierto si el fragmento recuperado la contiene**.
- Modelos reales del proyecto, sin red: `paraphrase-multilingual-MiniLM-L12-v2` (embeddings) y `ms-marco-MiniLM-L-6-v2` (reranker).
- «Antes» es el código de `f8b6f2b` y «Después», esta ronda. Se ejecutó el mismo script sobre los dos (`evaluacion_recuperacion.py`). Resultados completos: `resultados_antes.json` y `resultados_despues.json`.

**Métricas globales.** Fragmento: si se recuperó el fragmento correcto. Fuente: si se recuperó el documento correcto. Son métricas distintas.

| Modo | Filtro campus | Frag R@1 | Frag R@3 | Frag MRR | Fuente R@3 | Fuente MRR |
|---|---|---|---|---|---|---|
| semántica | no | 0.50 → 0.50 | 0.79 → 0.79 | 0.66 → 0.66 | 1.00 → 1.00 | 0.82 → 0.82 |
| semántica | sí | 0.79 → 0.79 | 0.79 → 0.79 | 0.83 → 0.83 | 1.00 → 1.00 | 1.00 → 1.00 |
| textual | no | 0.43 → 0.71 | 0.43 → 0.79 | 0.45 → 0.80 | 1.00 → 1.00 | 1.00 → **0.89** |
| textual | sí | 0.43 → 0.71 | 0.43 → 0.79 | 0.47 → 0.80 | 1.00 → 1.00 | 1.00 → **0.89** |
| híbrida | no | 0.43 → 0.86 | 0.57 → 1.00 | 0.52 → 0.93 | 1.00 → 1.00 | 1.00 → 1.00 |
| híbrida | sí | 0.43 → 0.93 | 0.57 → 1.00 | 0.57 → 0.96 | 1.00 → 1.00 | 1.00 → 1.00 |
| híbrida + reranking | no | 0.43 → 1.00 | 0.50 → 1.00 | 0.51 → 1.00 | 1.00 → 1.00 | 0.73 → 1.00 |
| híbrida + reranking | sí | 0.43 → 0.93 | 0.50 → 1.00 | 0.55 → 0.96 | 1.00 → 1.00 | 0.75 → 1.00 |

**MRR de fragmento por grupo de casos:**

| Grupo | Híbrida sin filtro | Híbrida con filtro | Híbrida + reranking con filtro | Textual |
|---|---|---|---|---|
| Área (A, B) | 0.15 → 1.00 | 0.21 → 1.00 | 0.13 → 0.75 | 0.00 → 0.25 |
| Plantel (C) | 0.10 → 0.75 | 0.20 → 1.00 | 0.12 → 1.00 | 0.00 → 0.62 |
| Ordinal (D) | 0.19 → 0.88 | 0.31 → 0.88 | 0.29 → 1.00 | 0.07 → 0.88 |
| Falso positivo («artículo 5») | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |
| Compartida (E) | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |
| Otras estrategias (F) | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |

La búsqueda semántica pura no cambia, como se esperaba: los vectores no cambian.

## 4. Análisis de regresiones

Revisé caso por caso los 14 casos, en los 8 modos y combinaciones de filtro.

- **Híbrida, con y sin reranking, con y sin filtro** (el modo que usan el Simulador y Runtime):
  - **ningún caso empeora** en posición de fragmento ni de fuente;
  - los casos que ya funcionaban (compartidos, otras estrategias, falso positivo) quedan iguales.
- **Textual sola:** en A, B y C1 la **fuente** correcta pasa de la posición 1 a la 2, mientras el **fragmento** correcto pasa de no aparecer en el top 10 a la posición 4.
  - **Causa:** el documento compartido «Áreas de formación» nombra las dos áreas y el «quinto semestre», y BM25 lo sube al primer lugar. Es relevante para la pregunta, pero no es el fragmento esperado.
  - Se documenta como regresión menor de la métrica de fuente en el modo textual puro. La híbrida no la tiene.
- **Lo que no se resolvió del todo:**
  - en la híbrida, las consultas de **sexto** semestre dejan el fragmento correcto en la posición 2 (C2 sin filtro; D3 con y sin filtro), detrás del 5.º semestre de la misma área;
  - en la híbrida con reranking y filtro, el caso B deja el fragmento correcto en la posición 2.
- **Criterio de la solicitud:** no hay regresiones relevantes en semestre, plantel ni documentos compartidos en los modos de producción. La regresión de la textual pura queda explícita.

## 5. Procedimiento de actualización para instalaciones existentes

1. Actualiza el código (`git pull`) y cierra RAG Studio.
2. Al abrir un proyecto, la migración 0023 se aplica sola. Solo agrega la columna `chunk.section_path`, sin modificar datos. La búsqueda sigue funcionando igual con los fragmentos existentes (sin ruta).
3. En Ingesta > Pipeline, pulsa «Revisar políticas por fuente (sin procesar)».
   - Las fuentes `por_encabezado` deben aparecer como «se procesará», con el motivo «Nueva versión del fragmentador por_encabezado… misma política».
   - Las demás deben aparecer como «se omitirá».
4. Ejecuta el pipeline completo. Solo esas fuentes se re-fragmentan y re-indexan. Las políticas, los catálogos y los metadatos no cambian. Los documentos originales no se tocan.
5. Comprueba un fragmento en Fragmentación > Ver detalle > Contexto jerárquico: «Ruta almacenada» debe coincidir con la reconstruida, y «Señal jerárquica… ACTIVA».
6. Publica una instantánea nueva para que Runtime use la ruta (ver la sección 6).

Si una fuente se re-fragmenta a mano en Fragmentación, también guarda la ruta.

## 6. Impacto en Runtime, instantáneas y paquetes publicados

- **Runtime de RAG Studio (API `POST /messages`, widget):**
  - usa el mismo `HybridSearch`, así que con una instantánea **publicada después** de re-fragmentar aplica la señal jerárquica;
  - el contrato de respuesta **no cambia**: `SourceSnippet` no agrega campos.
- **Instantáneas anteriores:**
  - al abrirlas, Runtime las lleva al esquema vigente, igual que con las migraciones anteriores: se agrega la columna con NULL;
  - su contenido no cambia y su búsqueda se comporta como antes, sin señal jerárquica;
  - para usar la ruta hay que publicar una instantánea nueva.
- **Paquetes NKP v1.0.0:**
  - el contrato no tiene campo para la ruta, y el exportador no la incluye;
  - los paquetes ya publicados (por ejemplo, el candidato de Bachillerato `e3a6c6be…`) **no cambian**, y su re-exportación reproduce los mismos bytes;
  - el Runtime externo de NEXOM no recibe la ruta mientras el contrato no la defina. Llevarla en el NKP requiere una versión del contrato y queda propuesto, no implementado.

## 7. Consideración para RAG Content Studio

Para preguntas del tipo «materias de X semestre del área Y en el plantel Z», un plan de estudios es, en esencia, una tabla: plantel, área, semestre, materia (y clave). Entregarlo así permitiría:

- responderlo con la consulta estructurada (Pista B.2: estrategia `por_tabla` o `por_hoja_estructurada`), con filtros exactos y sin depender del ranking;
- mantener el Markdown para la lectura humana.

**No se hicieron cambios en RAG Content Studio.** Antes hay que acordar el contrato de intercambio:
- columnas y códigos de catálogo (plantel y área como códigos, semestre como número);
- formato (CSV/XLSX en el lote, o una tabla Markdown normalizada);
- cómo se declara en el manifiesto del lote.

La mejora de esta ronda es general y no depende de esa representación.

## 8. Pendiente

**Validación funcional con AGENTE UDL - LOTE01_Bachillerato y sus documentos reales.** En particular: los casos A a E con `bachillerato_torres_landa.md` y `bachillerato_hilario_medina.md`, después del paso 4 de la sección 5, y con los casos de prueba de Calidad del proyecto. Los resultados de la sección 3 son sintéticos y **no** deben atribuirse a ese proyecto.

---

# Ronda 101: reranking y señal jerárquica (hallazgo en la validación real)

**Hallazgo de NEXOM con los documentos reales de LOTE01_Bachillerato.**
- **Consulta:** «¿Qué materias se cursan en quinto semestre del área Físico-Matemática y Químico-Biológicas en el plantel Torres Landa?».
- **Sin reranking:** el fragmento correcto queda en posición 1.
- **Con reranking:** queda primero el 6.º semestre de la misma área y el 5.º pasa a la posición 2. El MRR de fragmento baja de 1.00 a 0.50.

**Diagnóstico: era un defecto, no una limitación del modelo.**
- En la Ronda 100, el orden del cross-encoder se fusionaba con la lista jerárquica sumando 1/(60+posición) de cada lista.
- En este caso, el 6.º quedaba 1.º en el reranker y 2.º en la jerarquía, y el 5.º al revés: **la suma es idéntica**.
- El empate se resolvía con el orden del reranker. La señal jerárquica no tenía ningún peso real frente al reranker cuando los dos discrepaban.
- El corpus sintético ya mostraba el mismo efecto en el caso B con reranking y filtro (posición 2), documentado como no resuelto en la sección 4.

**Corrección** (`domain/rag/hierarchy.py::ordinal_conflicts`, `application/rag/queries/hybrid_search.py::_final_key`):
1. **Conflicto de ordinal explícito.** Si la consulta pide un ordinal de una unidad (`semestre_5`) y la RUTA del fragmento tiene otro ordinal de la misma unidad (`semestre_6`) y ninguno coincidente, el fragmento contradice la consulta. Queda **después** de los que no la contradicen, en la híbrida con y sin reranking.
   - Solo mira la ruta de encabezados, nunca el texto libre.
   - No aplica si la consulta no menciona un ordinal de periodo.
   - «quinto y sexto semestre» acepta ambos.
   - «5.º grado» o «artículo 5» no generan conflicto con un semestre.
2. **Desempate.** A igual score de fusión, gana el de mayor coincidencia jerárquica (área, plantel, semestre). Antes ganaba el orden del reranker.
3. **Trazabilidad.** `SemanticSearchResult.hierarchy_conflicts` (p. ej. `["semestre_6"]`). El Laboratorio RAG lo muestra como «[no coincide con el ordinal pedido: …]».

**Respuesta a los puntos 1 a 4 de NEXOM:**
1. **Cómo se combina:** el puntaje del cross-encoder se convierte en posición y se fusiona por RRF con la posición jerárquica; después se aplican la regla de conflicto y el desempate.
2. **Peso de área, plantel y semestre:**
   - **Semestre (ordinal explícito):** decide el orden cuando hay contradicción, porque es la única coincidencia verificable sin ambigüedad.
   - **Área y plantel:** no se convirtieron en regla dura, porque son texto libre y el **plantel ya lo garantiza el filtro estructurado de campus**. Cuentan en la fusión y en el desempate.
3. **Sin regresiones** en consultas sin semestre ni en otros tipos documentales:
   - sin ordinal en la consulta, la regla no hace nada y el reranker decide como antes (prueba `test_ronda101_sin_semestre_en_la_consulta_se_respeta_el_reranker`);
   - los documentos sin ruta (`documento_completo`, `por_tamanio`, `por_articulo`) nunca tienen conflicto.
4. **Caso real en las pruebas de regresión:**
   - la consulta exacta de NEXOM está en `tests/integration/test_contexto_jerarquico.py`, con un reranker de prueba que reproduce la preferencia del cross-encoder por el 6.º semestre, con y sin filtro de campus;
   - también está en el corpus de evaluación (casos B2 y B3).
   - Con el código de la Ronda 100, esa prueba falla («TL-FM-6» primero).

**Evaluación** (corpus SINTÉTICO, 16 casos con B2 y B3; modelos reales del proyecto). Archivos: `resultados_ronda101_antes.json` (código de la Ronda 100, `3340d37`) y `resultados_ronda101_despues.json`.

| Modo | Filtro campus | Frag R@1 | Frag MRR | Fuente MRR |
|---|---|---|---|---|
| semántica | no | 0.44 → 0.44 | 0.63 → 0.63 | 0.78 → 0.78 |
| semántica | sí | 0.75 → 0.75 | 0.82 → 0.82 | 1.00 → 1.00 |
| textual | no / sí | 0.69 → 0.69 | 0.80 → 0.80 | 0.88 → 0.88 |
| híbrida | no | 0.88 → 1.00 | 0.94 → 1.00 | 1.00 → 1.00 |
| híbrida | sí | 0.94 → 1.00 | 0.97 → 1.00 | 1.00 → 1.00 |
| híbrida + reranking | no | 0.94 → 1.00 | 0.97 → 1.00 | 1.00 → 1.00 |
| híbrida + reranking | sí | 0.94 → 1.00 | 0.97 → 1.00 | 1.00 → 1.00 |

Mejoran los casos B2 (con reranking), B (con reranking y filtro), C2 y D3 (sexto semestre, híbrida). Caso por caso, **ningún caso empeora** en ningún modo.

**Pendiente:** repetir la validación con los documentos reales de LOTE01_Bachillerato, con el reranking activado, antes de darlo por aceptado. Los resultados de esta tabla son sintéticos.
