# Ronda 99: ¿la estrategia por_encabezado conserva la jerarquía de encabezados?

Origen: validación real de NEXOM en AGENTE UDL - LOTE01_Bachillerato, con `bachillerato_torres_landa.md`.

La consulta sobre las materias de 5.º semestre del área Económico-Administrativa de Torres Landa no priorizó el fragmento esperado. Los fragmentos [9] y [12] se llaman ambos "5.º semestre", pero pertenecen a áreas distintas.

## 1. Conclusión

**Hay pérdida de contexto.** `split_by_headings` (`domain/ingestion/splitting.py`) corta el texto en cada línea `#`..`######`, pero:

- **Se pierde el nivel.** El encabezado `### 5.º semestre` y el `## Área …` se tratan igual.
- **Se pierden los ancestros.** Cada fragmento guarda solo el título de SU encabezado en `section_title`. Su texto empieza en esa línea, de modo que el área (`## Área …`) y el plantel (`# Bachillerato — Plantel …`) no aparecen en ningún dato del fragmento.
- **Lo que se indexa es solo `chunk.text`** (`index_source.py`). Los fragmentos que solo contienen un encabezado, como "Área Económico-Administrativa…", no se indexan, porque no tienen cuerpo propio. Su título no pasa a los fragmentos hijos.
- **Los dos "5.º semestre" son indistinguibles por su sección.** Su texto solo difiere en las materias, y las de ambas áreas coinciden en buena parte (Geografía, Estructura Socioeconómica, Finanzas, Ventas y Difusión).

El plantel no depende de la jerarquía: llega por los metadatos estructurados. `campus` se hereda a los fragmentos y el filtro de recuperación lo usa (Rondas 89 y 97). El **área** y el **semestre** no existen como metadatos; solo están en los encabezados.

## 2. Diagnóstico disponible desde ahora

Ingesta > Fragmentación > "Ver detalle del fragmento" (o doble clic). Muestra, sin modificar nada:

- **Texto del fragmento:** lo que de verdad se guarda y se indexa.
- **Metadatos heredados:** datos estructurados que usa el filtro, como `campus`, con sus valores múltiples.
- **Contexto jerárquico:** ruta completa de encabezados DERIVADA del texto extraído, con sus niveles, y una lista de los encabezados que el texto indexado NO contiene. Este contexto **no** se guarda ni se usa en la búsqueda; es solo para diagnóstico.

Para los dos fragmentos "5.º semestre" del caso, la ruta derivada es distinta:

- `# Bachillerato — Plantel Torres Landa > ## Área Económico-Administrativa y Humanidades > ### 5.º semestre`
- `# Bachillerato — Plantel Torres Landa > ## Área Físico-Matemática y Químico-Biológicas > ### 5.º semestre`

En ambos casos, la ventana avisa que el texto indexado no contiene ni el área ni el plantel.

## 3. Medición (recuperación densa, sin filtros)

El script `experimento_contexto_jerarquico.py`, en esta carpeta, usa el modelo del proyecto (`paraphrase-multilingual-MiniLM-L12-v2`) sobre un plan de Torres Landa con la estructura descrita por NEXOM y las materias reales del plan histórico. Compara dos formas de indexar:

- **A:** el texto actual del fragmento;
- **B:** la ruta de encabezados antepuesta al texto.

| Consulta | A: posición del fragmento esperado | B: posición |
|---|---|---|
| quinto semestre, Económico-Administrativa, Torres Landa | 1.º (el 5.º del otro área, 2.º) | 1.º (el otro 5.º sale del top 3) |
| quinto semestre, área económico administrativa | 1.º | 1.º |
| 5.º semestre, Físico-Matemática | **2.º** (gana "4to. semestre") | **fuera del top 3** |
| sexto semestre, químico biológicas | 1.º | 1.º |

Lectura:

- **Con B, la separación por ÁREA mejora** cuando la consulta nombra el área.
- **Con B, el ordinal empeora.** La ruta repite "semestre" en todos los fragmentos, y el modelo confunde "5.º" con "4to.", "quinto" o "6.º".
- **Anteponer la ruta al texto que se vectoriza no es, por sí solo, una mejora segura.** Con este modelo ayuda en unas consultas y perjudica otras.
- **Alcance de la medición:** es una muestra chica y sintética, solo de búsqueda densa (sin BM25 ni reranking).

## 4. Propuesta compatible con la arquitectura actual (no implementada: requiere autorización)

**P1. Conservar la ruta como dato del fragmento** (recomendado; base de todo lo demás).
- `split_by_headings` devuelve también el nivel y la ruta.
- `Chunk.section_path`: una lista de títulos, en una columna nueva (migración de proyecto).
- `chunk.text` NO cambia. El NKP v1.0.0 no tiene campo para la ruta: puede viajar en `semantic_summary` o esperar a una versión del contrato.
- Requiere re-fragmentar. La incrementalidad de la Ronda 98 debe incluir la versión del fragmentador en la huella de política, para que el pipeline reprocese solo lo necesario.

**P2. Usar la ruta en la parte léxica y en la afinidad de sección, no en el vector.**
- Agregar `section_path` al texto que indexa BM25 (búsqueda híbrida) y a `SectionAffinity` (Ronda 91).
- Las palabras del área ("económico", "administrativa") pasan a distinguir fragmentos, sin mover los vectores.
- Normalizar ordinales en títulos y consultas ("5.º", "5to.", "quinto" → `5`). La medición muestra que el ordinal es el punto más débil del modelo denso.

**P3. Datos estructurados donde la respuesta depende de ellos.**
- Para preguntas tipo "materias de X semestre del área Y", el plan de estudios es una tabla: área, semestre y materia.
- RAG CONTENT puede entregarlo como tabla (estrategia `por_tabla` o `por_hoja_estructurada`, Pista B.2) y responderlo con la consulta estructurada, con filtros exactos por área y semestre.
- Es lo más confiable para este tipo de pregunta.

**P4. Opcional, por proyecto:** anteponer la ruta al texto vectorizado (opción B de la medición). Solo si los casos de prueba de Calidad del proyecto lo justifican, nunca como valor por defecto.

Recomendación: **P1 + P2** como siguiente ronda, y **P3** para los planes de estudio en RAG CONTENT. Antes y después, medir con casos de prueba de Calidad del proyecto real ("materias de 5.º semestre del área …" por plantel y área).

## 5. Qué NO cambió en esta ronda

- No se modificaron la fragmentación, las políticas, el índice ni la base de datos.
- Abrir el detalle solo lee los fragmentos guardados (prueba: el pipeline de la Ronda 98 sigue omitiendo la fuente).
- Los fragmentos generados antes de esta versión se pueden consultar igual.
- Si la fuente se volvió a extraer después de fragmentar, la ventana dice que el contexto no se pudo ubicar, en vez de inventarlo.
