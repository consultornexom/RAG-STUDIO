# Incidente 493c8033: diagnóstico de disponibilidad de las evidencias E1–E7

**Alcance:** documental. No se ejecutó ni reconstruyó nada sobre evidencias originales.

**Única operación hecha en este lado:**
- búsqueda de solo lectura de artefactos del proyecto `b17cc73c-…` y del trace en las carpetas disponibles para el consultor;
- cálculo de huellas de código de commits del repositorio, sobre extracciones temporales con `git archive`, sin tocar ninguna instalación.

**Procedimiento de referencia:** `Procedimiento_Evidencias_E1_E7.md`.

## 1. Qué hay en este lado (consultor)

| Búsqueda | Resultado |
|---|---|
| Texto «493c8033» o «b17cc73c» en archivos de texto y binarios (incluidas bases SQLite) de las carpetas RAG STUDIO, RAG CONTENT STUDIO, la descarga de Drive y los adjuntos | **Sin coincidencias**, salvo los documentos de diagnóstico de la Ronda 104 |
| Nombres internos de `.zip` y `.agentproj` disponibles (respaldos 01d, pruebas UDL, adjuntos) | **Ninguno** contiene el proyecto `b17cc73c` |
| `runtime.db` locales (`data/`, respaldos 01d) | Corresponden a otros proyectos (instalaciones de prueba 01d) |

**Conclusión:** el consultor **no tiene ninguna evidencia original del incidente.**

Lo único disponible en este lado:

**a) Datos del informe de NEXOM** (Ronda 104), transcritos y no verificados contra el original:
- la consulta;
- `action = responder`;
- `matched_intent = consultar_requisitos_bachillerato`;
- `confidence = 0.8868033100427436`;
- `snapshot_version = 2`;
- el trace `493c8033-…`;
- los ids de los dos fragmentos puente (`428a1151-…` en la fuente `686ef812-…`; `59baa137-…` en `f5cbd2fd-…`) y del fragmento de requisitos (`8fe5e2de-…` en `f3dcbe88-…`);
- que este último quedó fuera del top 5.

**b) La reproducción con supuestos de la Ronda 104** (archivos reales, intenciones y metadatos supuestos). **No es evidencia del incidente.**

**c) Huellas de referencia del código** de los commits candidatos (`huellas_codigo_candidatos.json`; ver sección 4).

## 2. Disponibilidad por evidencia

Estados:
- **D** = debería existir en el entorno de NEXOM;
- **R** = existe, pero en riesgo de haberse modificado o de perderse;
- **N** = no existe para este incidente;
- **?** = depende de cómo se operó el entorno.

| Ev. | Qué es | Estado | Dónde | Qué falta o qué riesgo hay |
|---|---|---|---|---|
| **E1** | Respuesta JSON completa recibida por Testing Agent | **D** / ? | Registros de NEXOM Testing Agent | Depende de si Testing Agent guarda la respuesta íntegra. Si solo guardó el resumen del informe, faltan los `score`, que indicarían si hubo reranking, y la lista exacta de `sources`. La respuesta del incidente **no** trae `execution` (anterior a la Etapa 0) |
| **E2** | Fila del trace en `runtime.db` | **R** | `runtime.db` del Runtime que atendió el incidente | Si la Etapa 0 se validó con el **mismo** `runtime.db`, esa base ya recibió las columnas nuevas (`chunk_ids`, `execution`) y la fila `bccc81c9-…`: la fila del incidente se conserva, pero el archivo ya no es el original. **La purga de conversaciones** (`purge_conversations --retention-days 90`, si está programada) la borraría pasados 90 días. **Faltan siempre:** `chunk_ids` y `execution` (NULL: no se registraban). Lo que sí trae: mensaje, intención, confianza, acción, `source_ids` (sin orden), latencia, `conversation_id`, fecha |
| **E3** | Solicitud enviada (`message`, `variables`, `conversation_id`) y tipo de credencial | **D** / ? | Registros de Testing Agent; `conversation_id` y `message` también en E2 | `variables` no se guarda en `runtime.db`: solo existe si Testing Agent lo registró. Tipo de credencial: configuración de Testing Agent |
| **E4** | Código del Runtime en el momento del incidente | **R** / ? | Instalación del Runtime | Si esa instalación se **actualizó en su lugar** a `40be219` para la Etapa 0, el código del incidente ya no está en la carpeta. Fuentes que podrían conservarlo: `git reflog --date=iso` del clon (historial de HEAD con fechas, solo lectura), el ZIP o clon previo si se instaló en otra carpeta, notas de despliegue, `pip freeze` si se guardó. **No existe** ningún registro del commit dentro del Runtime: `/health` y `runtime.db` no lo informaban antes de la Etapa 0 |
| **E5** | Variables de entorno y forma de arranque | ? | Configuración del servicio en Windows (script, servicio, `.env`) | Si cambiaron para la Etapa 0, solo queda la memoria del operador o un respaldo. **Excluir siempre** `RAGSTUDIO_API_KEY` y otros secretos |
| **E6** | Instantánea v2 servida | **D** (paquete) / **R** (carpeta) | Paquete de entrega `.zip` de la v2 (no se modifica al servir) y carpeta servida | La validación de la Etapa 0 informó `fingerprint_matches = true`: **en ese momento**, la carpeta servida era idéntica a la publicada. Pero el Runtime de la Etapa 0 (esquema 0024) la abrió después: si la v2 se publicó con un esquema anterior (0023), esa apertura **la migró**, y la carpeta ya no es la original. El paquete `.zip` original es la fuente segura |
| **E7** | Inspección de la instantánea | **D** si hay E6 | Se obtiene ejecutando `inspeccionar_instantanea.py` sobre el **paquete original** (lee una copia temporal, no escribe) | Sobre la carpeta ya servida, la revisión de esquema puede reflejar la migración de la Etapa 0 y no la publicación |

**Datos del incidente que no existen y no pueden recuperarse:**
- versión o commit registrados por el Runtime;
- reranking aplicado, registrado como tal (solo se puede deducir del régimen de puntajes de E1);
- texto exacto de búsqueda;
- orden de fragmentos en `runtime.db` (solo en E1, si se guardó).

El texto de búsqueda y el orden pueden **recalcularse** en una reproducción, pero eso es un resultado de reproducción, no una evidencia.

## 3. Indicios que podrían obtenerse sin modificar nada

Ninguno de estos indicios confirma el incidente; solo acotan las hipótesis.

1. **Régimen de puntajes (E1).**
   - Los `score` entre 0 y ≈0.05 corresponden a la fusión RRF sin reranking, que es lo esperado: el Runtime de RAG Studio nunca tuvo modelo de reranking.
   - Cualquier otro rango indicaría otra configuración.
2. **Revisión de esquema del paquete original (E7)** y apertura de la carpeta por el Runtime del incidente.
   - **Hipótesis de partida:** el Runtime del incidente sirvió la **misma carpeta** que luego validó la Etapa 0 con `fingerprint_matches = true`.
   - **Por qué acota el código:** ese Runtime la abrió sin modificarla. Al abrir, el Runtime lleva `project.db` a su revisión más reciente, y si esa revisión es anterior a la de la base, falla. Por tanto, su revisión más reciente coincidía con la del paquete:
     - 0023 → código entre `3340d37` y `d99be4a` (Rondas 100–101);
     - 0024 → `3621dd5` o posterior.
   - **Requisitos para usarlo:** confirmar antes que fue la misma carpeta. Es un **indicio**, no una confirmación (condición 4 de NEXOM).
3. **`fingerprint_matches` en la siguiente carga.**
   - Si al reiniciar el Runtime de la Etapa 0 con la misma carpeta `/health/details` informa `fingerprint_matches = false`, esa carpeta fue migrada por la carga anterior.
   - Eso indicaría que la v2 se publicó con un esquema anterior a 0024, es decir, con código anterior a la Ronda 102.
   - Leer `/health/details` no modifica nada. El reinicio en sí no agrega cambios si la carpeta ya está en 0024.
4. **`git reflog` del clon del Runtime (E4):** historial local de los commits por los que pasó la carpeta, con fecha. Es de solo lectura.

## 4. Huellas de referencia del código (para comparar con E4)

Calculadas con `infrastructure/build_info.py` sobre `git archive` de cada commit; carpetas presentes en el commit. Valores completos y por carpeta en `huellas_codigo_candidatos.json`.

| Commit | Fecha | Revisión de esquema más reciente | Huella global (16 primeros) | Motor de recuperación |
|---|---|---|---|---|
| `b43ae4f` | 2026-10-15 | 0021 | `fdd668939ddab11d` | anterior a la Ronda 97 |
| `85594c2` | 2026-11-09 | 0021 | `e2da3f7add84eba3` | Ronda 97 |
| `e92ed66` | 2026-11-09 | 0022 | `b6c303e86101a1a4` | Ronda 98 |
| `f8b6f2b` | 2026-11-09 | 0022 | `eeeed87d3f8c20bb` | Ronda 99 |
| `3340d37` | 2026-11-09 | 0023 | `7f8baa1e63f3336e` | Ronda 100 |
| `af7c123` = `d99be4a` | 2026-11-10 | 0023 | `4828cf198496b72c` | Ronda 101 (mismo código) |
| `3621dd5` = `a497ac3` = `b260e6d` = `1f36a2b` | 2026-11-10 a 11-17 | 0024 | `ed34f2e258457608` | Ronda 102 (mismo código) |
| `40be219` | 2026-11-17 | 0024 | `f1232d2b6b83aaf7` | Ronda 102 + trazabilidad de la Etapa 0 (mismo orden) |

**Cómo comparar con la instalación del incidente**, si se conserva:
- **Con el script de la Etapa 0:** `python scripts/escribir_build_info.py --verificar <carpeta>`, ejecutado desde un checkout en `40be219`, calcula la huella de la carpeta indicada. Su huella global solo es comparable con esta tabla si la carpeta tiene las mismas subcarpetas de código. Si no, comparar por carpeta con el JSON.
- **Sin el script:** con `git` en la propia instalación, `git rev-parse HEAD`.

## 5. Acciones sugeridas a NEXOM (todas de solo lectura o de copia)

1. **Preservar las evidencias**, por orden de urgencia:
   - copiar `runtime.db` (y sus archivos `-wal`/`-shm` si existen) con el Runtime detenido o desde un respaldo;
   - suspender cualquier purga programada hasta extraer la fila del incidente;
   - conservar sin abrir el paquete `.zip` original de la v2.
2. **Extraer E1** (respuesta íntegra) y **E3** (solicitud) de los registros de Testing Agent, sin encabezados de autenticación.
3. **Extraer E2** con la consulta del procedimiento, sobre la copia.
4. **Obtener E4:**
   - `git reflog --date=iso`, `git log -1` y `git status --short` del clon del Runtime;
   - si se instaló desde ZIP, su nombre y SHA-256.
5. **Registrar E5** sin secretos.
6. **Ejecutar E7** sobre el paquete original; opcionalmente, leer `/health/details` tras un reinicio (sección 3.3).
7. **Entregar las evidencias** al consultor. Con ellas se preparará, ya con autorización, la reproducción exacta y su clasificación:
   - **reproducido**, si se cumplen las cinco condiciones del procedimiento;
   - **compatible, no confirmado**;
   - **no reproducido**.
