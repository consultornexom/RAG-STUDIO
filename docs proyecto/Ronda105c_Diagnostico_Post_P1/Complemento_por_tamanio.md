# Ronda 105d: complemento con la configuración real de AGENTE UDL (`por_tamanio` 500/60/80)

**Alcance:** diagnóstico sin cambios de motor, fuentes, índice ni casos de prueba. P1 sin cambios; incidente 493c8033 abierto.

**Herramienta:** `experimento_post_p1.py --compartidos por_tamanio_todos`, con todas las fuentes en `por_tamanio`, objetivo 500, solapamiento 60, mínimo 80.

**Reproducción:**
- cinco archivos reales de LOTE01, modelos reales, procedimiento r105b **sin reranking**;
- intenciones y metadatos supuestos;
- resultados en `resultados_por_tamanio.json` y `salida_detalle_por_tamanio.txt`.

## 0. Limitación: número de fragmentos

| Conteo de tokens | Fragmentos |
|---|---|
| AGENTE UDL real (informe de NEXOM) | **29** |
| `palabras` (1 por palabra) | 5 |
| `subpalabras` (tokenizador del modelo de embeddings) | 7 |
| `x3` (3 por palabra) | 12 |

- **Por qué no coincide con la app:** la app cuenta tokens con tiktoken `cl100k_base`, cuya codificación no puede descargarse en este entorno. Por eso se midió con tres conteos.
- **Lo que sugiere el 29:** ningún conteo plausible lo produce con solo estos cinco archivos. El índice real probablemente contiene **otras fuentes o versiones**.
- **Cómo cerrar esta brecha:** el listado de fragmentos por fuente (`inspeccionar_instantanea.py` sobre la instantánea o el `.agentproj`).
- **Las conclusiones no dependen del conteo:** se repiten igual con los tres.

## 1. Los 14 casos de LOTE01 con `por_tamanio` (preguntas 1 a 3)

MRR (1.000 = el fragmento correcto siempre primero) y posición del fragmento correcto en R1 (UDL-BACH-003) y R2 (incidente, documentos):

| Variante | `palabras` (5 frag.) | `subpalabras` (7) | `x3` (12) |
|---|---|---|---|
| **r105b actual** | 0.917 (R1 **2**, R2 3) | 0.792 (R1 **2**, R2 3) | 0.833 (R1 **2**, R2 3) |
| Y (P2a) | 0.917, sin cambios | 0.792, sin cambios | 0.833, sin cambios |
| R (P2b) | 0.917, sin cambios | 0.792, sin cambios | 0.881 (R2 → 1) |
| Y + R (P2 completo) | 0.917, sin cambios | 0.792, sin cambios | 0.881 (R2 → 1) |
| T (P3) | 0.917, sin cambios | 0.845 (R1 1, R2 2) | 0.863 (R2 1; **O1 empeora 2→4**) |
| **M** (nuevo, sección 3) | **1.000** (R1 1, R2 1) | **0.875** (R1 1, R2 1) | **0.917** (R1 1, R2 1) |
| M + Y, M + R, M + Y + R | iguales a M | iguales a M | iguales a M |

**Respuestas:**
- **P2a (Y) no tiene ningún efecto con `por_tamanio`.** Con esta estrategia no existen fragmentos que contengan solo el encabezado YAML: el YAML queda dentro del primer fragmento de cada documento. **No resuelve UDL-BACH-003 ni mejora la consulta de documentos.**
- **R tampoco**, salvo con la granularidad más fina (`x3`), donde la sección puente queda en un fragmento corto propio.
- **Consultas que empeoran respecto de r105b:**
  - con M: **ninguna**, en los tres conteos;
  - con T: O1 (RVOE) baja de 2.º a 4.º en `x3`.
- **Problemas previos, ajenos a la causa analizada:** con los conteos más finos, P4, P5 y O1 ya no están en 1.º **en r105b**. Ninguna variante los empeora, salvo T en `x3`.

## 2. Por qué el primer resultado real es «Información general» de Torres Landa con afinidad 0.18 (pregunta 4)

1. **[COD]** Con `por_tamanio`, el **primer fragmento** de cada plan contiene, en este orden:
   - el encabezado YAML;
   - el título `# Bachillerato — Plantel Torres Landa`;
   - la sección `## Información general`;
   - el comienzo del plan.

   Su contenido visible es «Información general», pero el fragmento no tiene título de sección. Por la regla C2 de la Ronda 102, su título para la afinidad es el **primer encabezado Markdown: «Bachillerato — Plantel Torres Landa»**.
2. **[COD]** La afinidad de ese título se debe a una sola raíz, «bachi».
   - **Dónde coincide:** con el **nombre de la intención**, `consultar_requisitos_bachillerato`.
   - **Dónde sí se quita:** el valor de catálogo «Bachillerato» se quita de la consulta, de la descripción y de los ejemplos de la intención (Rondas 90 y 91).
   - **Dónde no se quita:** el reconocimiento de menciones trata el guion bajo como parte de la palabra, así que **no** lo reconoce dentro de un nombre en snake_case. Comprobado: `find_mentions("consultar_requisitos_bachillerato", ("Bachillerato",))` devuelve vacío.
   - **Valor resultante:** 0.15 en la reproducción y 0.18 observado.
   - **Lo mismo ocurre con:** «Requisitos de ingreso — Bachillerato UDL» y «Cualidades del aspirante — Bachillerato UDL», que reciben parte de su afinidad por la misma raíz.
3. **[COD + EXP]** El fragmento del plan es 1.º en la búsqueda, y el de requisitos 2.º o 3.º. Por la combinación de la Ronda 102:
   - el plan (búsqueda #1, afinidad #2) obtiene 1/61 + 1/62 = **0.03252**;
   - requisitos (búsqueda #3, afinidad #1) obtiene 1/63 + 1/61 = **0.03227**.

   Una afinidad que solo debía distinguir el *nivel* (Bachillerato) actúa como si distinguiera el *tema*.

**Coincidencia con lo observado:** la reproducción `por_tamanio` da exactamente la forma observada por NEXOM.
- **UDL-BACH-003:** requisitos 2.º, por detrás de un fragmento general con afinidad baja (0.15 frente a 0.18 observado), y requisitos con la mayor afinidad (0.65 frente a 0.57).
- **Consulta de documentos:** los dos planes primero.

**Cómo comprobarlo en el Simulador:** la línea de ese fragmento debería indicar «afinidad 0.18 con «Bachillerato — Plantel Torres Landa»».

**Diferencia con el diagnóstico de la Ronda 105c:** allí, con `documento_completo` y `por_encabezado`, el papel del rival lo cumplía el fragmento solo-YAML, porque el YAML quedaba aislado. Con `por_tamanio`, el YAML no se aísla y la causa es directamente la afinidad espuria por «bachi». **La causa de fondo es la misma** (afinidad de títulos que solo nombran el nivel). La corrección que la ataca en cualquier estrategia es M; Y solo cubre el caso del YAML aislado.

## 3. Corrección que resolvería el caso: M (nueva, no incluida en P2–P4)

**M: enmascarado de valores de catálogo también en nombres de intención en snake_case.** Al calcular la afinidad, y por coherencia también al reconocer la intención, el nombre `consultar_requisitos_bachillerato` se trata como «consultar requisitos bachillerato». El valor «Bachillerato» se quita igual que ya se quita de la consulta, la descripción y los ejemplos.

**Características:**
- **Generalidad:** aplica a cualquier proyecto cuyos nombres de intención contengan valores de catálogo (programas, niveles, planteles), sin reglas por nombre.
- **Coherencia:** completa el principio de la Ronda 90 (transformar por igual la consulta y todos los textos de la intención).

**Efecto medido:**
- con `por_tamanio`, resuelve UDL-BACH-003 y la consulta de documentos en los tres conteos, sin empeorar ninguna consulta;
- en otras estrategias:
  - `documento_completo`: M sola sube R2 al 1.º pero baja R3 de 1.º a 2.º, porque la sección puente obtiene afinidad 0.20 por la palabra «plantel» de la consulta;
  - `por_encabezado`: mejora parcial;
  - **M + Y + R** no empeora ninguna consulta en ninguna estrategia: `documento_completo` 1.000, `por_encabezado` 0.952, `por_tamanio` 1.000 / 0.875 / 0.917.

**Riesgo:**
- cambia la afinidad de cualquier título que contenga un valor de catálogo presente en el nombre de la intención;
- hay que revisar el efecto en el reconocimiento de intención, que también usa el nombre (ver criterios).

## 4. ¿P2a aislado o P2 completo? (pregunta 5)

**Para AGENTE UDL, con su configuración real, ninguno de los dos resuelve el problema.** P2a (Y) no actúa con `por_tamanio`, y P2 completo (Y + R) apenas.

**Recomendación actualizada para autorización:**

1. **Etapa 1: M.**
   - Corrige UDL-BACH-003 y la consulta del incidente con la configuración real, sin regresiones en la reproducción.
   - Nuevo identificador de procedimiento.
   - Sin cambios de índice ni de documentos.
2. **Etapa 2: Y + R, con R desactivada por defecto.** Para proyectos fragmentados por encabezado o con documentos completos, donde M sola no basta (R3 en `documento_completo`, consulta de documentos en `por_encabezado`). **No es necesaria para AGENTE UDL mientras use `por_tamanio`.**
3. **P3 y P4:** siguen sin recomendarse por ahora. P3 tiene efecto mixto y empeora O1.

**Criterios de aceptación de la Etapa 1:**
1. **AGENTE UDL, 14 casos de Calidad** (línea base `085fe5a5-…`):
   - UDL-BACH-003 con la fuente esperada en 1.º, sin cambiar expectativas;
   - ningún caso empeora;
   - Recall@3 = 100 %;
   - MRR ≥ 0.90.
2. **LOTE01, 14 consultas,** en `por_tamanio` (tres conteos), `documento_completo` y `por_encabezado`:
   - ninguna consulta peor que r105b en `por_tamanio`;
   - en las otras estrategias, las diferencias documentadas (R3 en `documento_completo`), que se resolverán en la Etapa 2.
3. **Reconocimiento de intención sin cambios:** misma intención y misma decisión en los 14 casos de AGENTE UDL y en las 14 consultas de LOTE01. Las confianzas pueden variar; deben informarse.
4. **Equivalencia Simulador–Runtime** con la misma instantánea (prueba de la Ronda 105b, extendida).
5. **Suites completas** sin fallas nuevas.

**Datos que pedimos a NEXOM para confirmar con su proyecto real:**
- el listado de los 29 fragmentos por fuente;
- el título de afinidad que muestra el Simulador para el 1.º resultado de UDL-BACH-003.
