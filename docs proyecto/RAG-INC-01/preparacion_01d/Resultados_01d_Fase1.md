# RAG-INC-01d · Fase 1 — Datos reales y paquetes NKP candidatos

Fecha: 2026-10-15 · Rama `rag-inc-01/01d`, creada desde `b2e692e` (`rag-inc-01/01c` sin cambios) · **Sin commit, sin tag, sin push.** No se tocó Runtime: no hubo INC-013G, ni smoke formal, ni multilote.

Todo se hizo sobre **copias verificadas**; los orígenes congelados no se modificaron. Los artefactos (instalaciones de trabajo, paquetes e informes) están en `_respaldos_rag_inc_01/01d/`, fuera de Git.

## 1. Corpus B: saneamiento controlado

Origen: `Prueba_A_E2E_Oferta_Academica_UDL.agentproj` (`e7d81510…4ebe`, verificado).

**Duplicados.** Son 3 nombres con 2 filas cada uno. Comparé todos los campos salvo `id`, `created_at` y `updated_at`: descripción, ejemplos positivos y negativos, prioridad, riesgo, variables obligatorias y opcionales, preguntas aclaratorias, regla de respuesta, canalización, modo de resolución y estado activo.

| Nombre | Se conserva (más antigua) | Se elimina | ¿Duplicado exacto? |
|---|---|---|---|
| Consultar perfil del egresado y campo laboral | `14d1c17e…` (20:11:35.94) | `bd3dd88e…` (20:15:41.39) | **Sí**, 0 campos distintos |
| Consultar plan de estudios | `04970176…` (20:11:35.86) | `dc8c9164…` (20:15:41.32) | **Sí**, 0 campos distintos |
| Consultar requisitos de ingreso | `b3ca566b…` (20:11:35.91) | `b6bd5264…` (20:15:41.35) | **Sí**, 0 campos distintos |

Las tres segundas copias se crearon 4 minutos después, en el mismo segundo: es una carga repetida.

**Referencias.** Las demás tablas referencian intenciones **por nombre** (`test_case.expected_intent`, `evaluation_result_item.actual_intent`), y ninguna tabla contiene los ids eliminados. Conservar una fila por nombre no rompe nada.

**Saneamiento aplicado**, solo en la copia de trabajo y con la regla autorizada para duplicados exactos:
- Script: `sanear_intenciones_duplicadas.py --aplicar`.
- 6 → 3 intenciones; 0 nombres duplicados; `integrity_check` ok.
- `project.db` de la copia: `640eb8c7…2b9c` antes → `6ab156ee…0467` después.
- Informe: `_respaldos_rag_inc_01/01d/B/saneamiento_intenciones.json`.

La copia de B también lleva la corrección de `test_case.code` que NEXOM autorizó para 0017 (`UDL-001-02`, `UDL-002-02`) y el relleno de huellas (5 → 0). El original sigue intacto: `validar_backfill_corpus.py` verifica el hash del origen antes y después.

## 2. Corpus D: instalación real

**No es accesible desde este entorno.** La instalación de AGENTE UDL está en el equipo macOS de NEXOM, y su `evidencia.tar.gz` tampoco está aquí. Preparé la herramienta y la probé con una instalación simulada con las mismas condiciones: proyecto vivo en 0020, v5 anterior a 0021 con `snapshot_identity.json`, y una v1 registrada sin carpeta.

- **Herramienta:** `preparar_candidato_D.py`, con su guía `README_VALIDACION_D_01d.md`.
- **Código para ejecutarla:** `_respaldos_rag_inc_01/01d/D/RAG_STUDIO_codigo_01d_F1.zip` (SHA-256 `7e5b8e1c73c8923ea27aa5719b47bd62edb7a1c13c022bf1026d89e72812f117`).

**Garantías de la herramienta:**
- Nunca abre la instalación original con la aplicación (eso migraría el `project.db` vivo, que está en 0020) y nunca escribe en ella.
- **Parte 1, solo lectura** (desde copias temporales):
  - Alembic del proyecto vivo, huellas faltantes e instantáneas registradas;
  - de v5: carpeta física, `snapshot_identity.json`, legibilidad e integridad del `project.db`, presencia de 0021;
  - compuertas 01b/01c aplicadas directamente a v5.
- **Parte 2:** copia la instalación completa, publica la v6 **en la copia** y genera el candidato con la compuerta 01c.
- **Parte 3:** verifica que el original no cambió.

**Resultado con la instalación simulada:**
- v5 bloqueada por `SnapshotInconsistentError`, porque es anterior a 0021;
- v6 en la copia: PASS, ERRORES: 0, reproducible byte a byte;
- original intacto: sigue en 0020, con el mismo hash y la misma huella de v5.

**Lo que se espera en la instalación real:** v5 bloqueada por la misma razón, porque el proyecto vivo de D estaba en 0020 al congelarse. Hará falta la instantánea nueva, que solo se publica en la copia. **Ejecutado por NEXOM: D = PASS real (ver §9).**

## 3. Instantáneas nuevas (en las copias de trabajo)

| Corpus | `project_id` | `knowledge_base_id` | `snapshot_id` | Versión | Fecha (UTC) | Fuentes | Chunks |
|---|---|---|---|---|---|---|---|
| A | `42ac4489-e6c6-4185-b912-7e8540f69f54` | `15abff46-a4ea-43af-8f88-1699a6ce33e0` | `fbe0fcb7-dc8e-4ced-a98c-49363fdca32f` | v1 | 2026-10-15 15:54:24 | 1 | 1 |
| B | `9a3a0a10-b678-41a2-b758-db1503ad7399` | `4199f879-f151-47c4-be1c-8bce933c9087` | `4f9078ed-16af-4126-a579-805469f07bfe` | v2 (*) | 2026-10-15 15:53:29 | 5 | 15 |
| C | `aa0c6d50-66a3-4a3d-bb96-fdb6f05dfac0` | `821e1532-0975-491f-ac5f-f96e25e0d46b` | `eb99dd03-2833-469b-8f57-edb284ff02b7` | v1 | 2026-10-15 15:54:14 | 25 | 76 |

(*) La v1 de B (`b174946b…`) se publicó en el primer intento, que falló al exportar (§6.1). Se conserva sin tocar.

Los `knowledge_base_id` son los que 0021 asignó a cada copia de trabajo: los paquetes `.agentproj` de origen son anteriores a 0021. Las instantáneas anteriores no se modificaron, y la exportación no alteró las nuevas (huella igual antes y después).

## 4. Paquetes candidatos

`tenant = nexom-udl-candidato`; perfil CORE.

| | A (canario) | B (saneado) | C |
|---|---|---|---|
| `package_id` | `urn:nexom:package:355957b3e8f2c60a5cbd52e065aa4358` | `urn:nexom:package:fd662435e0928cf0646365c0fa8bd5c8` | `urn:nexom:package:018d39bc28bbad9af71a4a782331fab3` |
| sources / chunks / evidence / media | 1 / 1 / 1 / 0 | 5 / 15 / 15 / 0 | 25 / 76 / 76 / 0 |
| intents / guardrails | 0 / 0 | 3 / 1 | 0 / 0 |
| metadata schema | v1 local, 0 campos, 0 catálogos | v1 local, 0 campos, 0 catálogos | v1 local, 0 campos, 0 catálogos |
| embedding identity | fastembed · `paraphrase-multilingual-MiniLM-L12-v2` · 384 · cosine | igual | igual |
| índice (puntos / tipos) | 1 / `texto` | 15 / `texto` | 76 / `texto` |
| acceptance cases | 0 (INC01-D5) | 0 | 0 |
| `content_digest` | `d15a13d8…8e6ad` | `b011d058…4b282` | `649ab995…c747` |
| ZIP SHA-256 | `508dfaf865bee5189efb80310841ecf6b5ebd52426630dab21be7c6ff813eb97` | `585af5cd82f6175d2dfa54c7f62c19a24118cc62ffedd8d953f81042dcadfc01` | `21a6bd8894c0b2272a37ff6eef48792b6e2cf19fe64a79d4904f6e7055e773d0` |
| sidecar SHA-256 | `67ececc6315b4cf30c7f07103c5c2512e19a8bc3eaa38cc00a205c66b1618588` | `d26f8ef95e5a617793ca98d574f2b7eddbe284b83634e87755071591d4998164` | `979d6793565dc3fc6c1c267acc29aa03a2cad6fdef2abc76a9cb538d80eca2cd` |
| Compuerta 01c | **PASS** (72) | **PASS** (203) | **PASS** (768) |
| Validador firmado v1.0.0 | **ERRORES: 0** | **ERRORES: 0** | **ERRORES: 0** |

Omisiones declaradas en los tres: `ORIGINALS_NOT_INCLUDED`, `VECTORS_NOT_INCLUDED`, `EVIDENCE_NOT_VERIFIED`. Capacidades: `text_retrieval=true`, `structured_retrieval=false`, `image_retrieval=false`.

Ubicación: `_respaldos_rag_inc_01/01d/<A|B|C>/candidato/a/`. Comprobé el hash de la copia en el repositorio.

## 5. Reproducibilidad (A, B y C)

Se exportó dos veces la misma instantánea, en las carpetas `a/` y `b/`. Coinciden `package_id`, `content_digest`, conteos, ids portables (fuentes, chunks, evidencias, media y metadatos) y los 13 archivos internos byte a byte. **El ZIP también es idéntico byte a byte** en los tres (`cmp a b`).

## 6. Hallazgos

1. **Exportador, entorno con FUSE (clasificación: exportador).** En el primer intento de B, la salida estaba sobre el montaje FUSE de la carpeta del proyecto.
   - La publicación terminó: el ZIP y el sidecar quedaron en su sitio.
   - Pero al calcular `zip_sha256` releyendo el ZIP **ya publicado**, el sistema de archivos respondió `FileNotFoundError` de forma transitoria, justo después de crear el enlace duro y borrar el staging.
   - Resultado: una excepción con los archivos ya publicados, que es justo el estado inconsistente que el exportador debe evitar. Los archivos se apartaron a `_respaldos_rag_inc_01/01d/hallazgo_fuse/`.
   - Al repetir con la salida en un disco local, todo pasó.
   - **Corregido** (autorización NEXOM, §10): el SHA del ZIP se calcula en staging, antes de publicar, y no se vuelven a leer los archivos publicados.
2. **Duplicados de `test_case` en B.** También son cargas repetidas (`UDL-001`, `UDL-002`). Se tratan con la corrección ya autorizada para 0017. No afectan al NKP, porque los casos de aceptación no se exportan.

## 7. Riesgos pendientes

- ~~D sin validar~~: resuelto, D = PASS real en Mac (§9).
- **Instalación real de D.** El proyecto vivo sigue en 0020 (sin identidades persistentes). Su candidato sale de una copia; migrar la instalación real requiere una decisión aparte.
- ~~Corrección del exportador sin aplicar~~: aplicada (§10).
- Los `knowledge_base_id` de A, B y C nacen en estas copias. Otra copia o migración de los mismos orígenes produciría otros.
- Siguen los riesgos aceptados en 01b y 01c: PyInstaller sin probar, dependencias fijadas, ventana entre ZIP y sidecar, zlib, y validador firmado sin control de unicidad (cubierto por la compuerta).

## 8. Corpus D: primera ejecución real y saneamiento autorizado

La primera ejecución en macOS confirmó la Parte 1:
- `alembic_vivo = 0020`; 35 fuentes, 0 sin huella, 668 chunks;
- v5 presente, con `snapshot_identity` correcto, `integrity_check` ok y `con_0021 = false`;
- compuerta BLOQUEADA con `SnapshotInconsistentError`;
- original intacto.

La Parte 2 falló con `BrokenReferenceError`: la intención "Consultar programa específico" declara `optional_variables = ["modalidad", "nivel_academico"]` y ninguno de esos códigos existe como variable conversacional (sí existen como campos de metadatos y como catálogos).

**Clasificación NEXOM: DATA_DEFECT.**
- Ya estaba identificado en la auditoría de la Ronda 90; esos códigos se ignoraban en silencio.
- El exportador actúa correctamente al bloquear, conforme al Alcance §5 y a `conversational_bundle.schema.json` con el validador firmado.

**Saneamiento autorizado.** En una copia nueva y antes de migrarla, `optional_variables` pasa de `["modalidad", "nivel_academico"]` a `[]`. No se cambia nada más, no se crean variables y no cambia el código del exportador.
- Herramienta: `sanear_optional_variables.py`, invocada desde `preparar_candidato_D.py` con `--vaciar-optional-variables-de` y `--optional-variables-esperadas`.
- Probada con una instalación simulada que reproduce D:
  - sin saneamiento, el mismo `BrokenReferenceError`;
  - con un valor esperado incorrecto, aborta sin escribir;
  - con el saneamiento, PASS y ERRORES: 0, exportación reproducible byte a byte y original intacto.
- Código para la Mac: `_respaldos_rag_inc_01/01d/D/RAG_STUDIO_codigo_01d_F1_saneamiento_D.zip`, SHA-256 `92ffd5905dc2b1e257d86f09f692baef9b6ca1a474632c9662dcd61ef4919f0a`. Se generó desde `rag-inc-01/01d` en HEAD `b2e692e3d819ca6defd7b8dfee4029f6c0b65cbd`, más los archivos de `preparacion_01d/` sin commit.

**Mejora pendiente (no implementada):** reportar todas las referencias rotas en un único error.

## 9. Corpus D: PASS real en Mac (ejecutado por NEXOM)

**Original, solo lectura:**
- `alembic = 0020`;
- `project.db` intacto y la instantánea v5 intacta;
- 35 fuentes, 0 sin `content_hash`, 668 chunks.

**Saneamiento DATA_DEFECT, aplicado solo en la copia.** En la intención "Consultar programa específico", `optional_variables` pasó de `["modalidad", "nivel_academico"]` a `[]`, con `integrity_check` ok. No se tocó nada más y no se crearon variables.

**Instantánea candidata (en la copia):** v6, `snapshot_id` `9fd22143-1bf6-42be-a595-ac185685f287`.

**Paquete NKP de D:**
- `package_id`: `urn:nexom:package:63e5074e4cc1323a443eb1b5ed2c3617`
- 35 fuentes · 668 chunks · 668 evidencias · 7 intenciones · 4 guardrails
- Compuerta 01c: **PASS**; validador firmado: **ERRORES: 0** (8974 comprobaciones)
- Reproducibilidad: mismos `package_id`, `content_digest`, conteos, ids portables y archivos internos; **ZIP idéntico byte a byte**
- Existen físicamente `candidato/a/*.zip`, `a/*.content.sha256`, `b/*.zip`, `b/*.content.sha256` e `informe_candidato.json`

| Artefacto | SHA-256 |
|---|---|
| `informe_D.json` | `8964aefa0f2573a571fdac64e40e8d9d3a008c311df1b5f5bb418ceb6ab27911` |
| `content_digest` | `bea18043dce8083a89cd4974e09e8c0bfe7aff2dba6d534b1255fca172aea04a` |
| ZIP | `98f3a13997aade992a65dbfee85cfc67965dda33ea8a2ead679d2bf0d563dfac` |
| sidecar | `9c610545a2e910beebf8e2f704996fd190a32b22d54d70c85a037b2f9575c607` |

**Resultado de la Fase 1: A = PASS · B = PASS · C = PASS · D = PASS.**

## 10. Corrección de la publicación segura del NKP (autorización NEXOM)

**Defecto (hallazgo con B, §6.1).** Después de publicar el ZIP y el sidecar, el exportador releía el ZIP **publicado** para calcular `zip_sha256`. En un sistema de archivos montado (FUSE) esa lectura falló de forma transitoria, y el resultado fue una excepción con la entrega ya publicada.

**Corrección** (solo `_publicar` y `_publicar_sin_sobrescribir` en `infrastructure/exporters/nexom_knowledge_package.py`). El flujo queda así:
1. ZIP en staging;
2. relectura y verificación del ZIP;
3. sidecar en staging;
4. compuerta 01c;
5. **`zip_sha256` calculado sobre el ZIP en staging**;
6. publicación.

El valor reportado es el del archivo que se publica sin modificación, y nunca se relee el publicado.

**Publicación.** Se sigue sin sobrescribir:
- primero `os.link` (atómico y sin sobrescribir);
- si no hay enlaces duros, se reserva el nombre en exclusiva y se hace `os.replace` (rename atómico).

**Segundo defecto encontrado al revisar.** En la vía sin enlaces duros, si el rename fallaba quedaba la reserva vacía con el nombre final. Ahora se retira.

La atomicidad es por archivo. La pareja la garantiza `_publicar`: si falla el sidecar, se retira el ZIP; si algo falla antes, no se publica nada; el staging se borra siempre. Resultado: **ZIP + sidecar, o ninguno.**

No cambian el contrato, el validador, `id_scheme`, el contenido lógico, `package_id`, `content_digest` ni los mapeos.

**Pruebas nuevas** (`tests/integration/test_nkp_publicacion_segura.py`, 8):
- el SHA se calcula en staging y nunca sobre el ZIP publicado;
- **ZIP final ilegible justo después de publicarse** (se simula el `FileNotFoundError` de B): la exportación ya no falla;
- fallo al publicar el ZIP: no queda nada;
- fallo al publicar el sidecar: se retira el ZIP;
- sin enlaces duros: se publica con reserva y rename;
- fallo del rename: se retira la reserva;
- salida existente: no se sobrescribe;
- exportación normal y reproducible.

**Control negativo.** Con el exportador anterior fallan 3 de las 8: SHA en staging, ZIP final ilegible y reserva del rename.

**Candidatos sin regresión.** Reexporté A, B y C desde sus mismas instantáneas: mismo `package_id`, mismo `content_digest`, mismo SHA-256 del ZIP y mismos conteos, con PASS. **B se exportó esta vez directamente sobre el sistema de archivos FUSE** donde ocurrió el fallo, y pasó.

D no se reexportó (vive en la Mac). La corrección no altera el contenido ni los bytes del ZIP, como demuestran A, B y C idénticos.

**Regresión:**
- unitarias 974/9;
- integración **546/14** (538 + 8 nuevas);
- smoke 15/2;
- ruff limpio (`ruff check .`: los mismos 14 avisos históricos);
- mypy con los mismos 22 errores en 7 archivos.

**Pendiente (sin implementar):** reportar todas las referencias rotas en un único error.
