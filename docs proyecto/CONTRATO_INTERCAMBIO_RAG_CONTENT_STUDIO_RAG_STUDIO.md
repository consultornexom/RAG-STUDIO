# Contrato de Intercambio: RAG Content Studio Desktop -> RAG Studio

**Version del contrato: 2 (2026-09-29).**

Este documento es la fuente unica de verdad del formato de entrega entre las dos herramientas. Existe una copia identica de este archivo en cada repositorio (`RAG CONTENT STUDIO/DOCS PROYECTO/` y `RAG STUDIO/docs proyecto/`) porque no comparten un repositorio comun -- **cualquier cambio a este contrato debe aplicarse en ambas copias a la vez**, y el codigo de ambos lados debe seguir referenciando este documento (no reinventar el formato leyendo solo el codigo del otro lado).

Origen: incidencia real reportada por el consultor (2026-09-29) -- un lote procesado en RAG Content Studio en un equipo Windows se copio a un equipo macOS con RAG Studio, y la importacion reporto "Importadas: 0 / Omitidas: 13" a pesar de que los 13 `.md` estaban fisicamente presentes en la carpeta de entrega. Causa raiz: `ruta_archivo` traia la ruta absoluta completa del equipo productor (con backslashes de Windows), y el importador de RAG Studio no podia interpretarla en un sistema POSIX. Este contrato v2 corrige eso y formaliza, con version explicita, lo que antes era un acuerdo implicito entre ambas herramientas.

## 1. Alcance

Describe el formato de la carpeta de entrega que RAG Content Studio produce (`14_entrega_rag_studio/`, copia de conveniencia de `12_exportaciones/manifiesto.csv` mas los `.md` liberados) y que RAG Studio consume mediante la accion "Importar carpeta de RAG CONTENT..." (`RegisterSourcesFromFolder`).

## 2. Estructura fisica del paquete

```
14_entrega_rag_studio/
├── manifiesto.csv
├── <archivo-1>.md
├── <archivo-2>.md
└── ...
```

Estructura plana (sin subcarpetas) en la version actual. `package_root` es la carpeta que contiene `manifiesto.csv` -- la misma carpeta que el operador selecciona al importar en RAG Studio.

## 3. Versionado del esquema

Columna `manifest_schema_version`, presente en cada fila del CSV:

- **Ausente o vacia -> manifiesto V1 (legado)**, generado por versiones de RAG Content Studio anteriores a esta correccion. `ruta_archivo` puede contener una ruta absoluta del equipo productor (Windows o POSIX), con cualquier separador.
- **`"2"` -> manifiesto V2 (contrato portable)**, generado desde esta version en adelante. `ruta_archivo` es SIEMPRE una ruta relativa POSIX (separador `/` unicamente) a `package_root`; nunca absoluta, nunca con segmentos `..`.

RAG Studio decide, fila por fila, que resolutor aplicar segun esta columna.

## 4. Columnas: encoding, separador y semantica

Encoding UTF-8, separador coma, comillas dobles si un valor contiene comas (comportamiento por defecto de `csv.DictWriter`/`csv.DictReader` de Python en ambos lados, `newline=""`). RAG Content escribe el manifiesto sin BOM; los lectores (RAG Studio, la verificacion previa a la entrega y el script de reparacion) lo leen con `utf-8-sig`, para tolerar el BOM que agrega Excel si alguien abre y guarda el archivo (precision 2026-09-30).

| Columna | Campo en RAG Studio | Notas |
|---|---|---|
| `manifest_schema_version` | (no se persiste) | Ver seccion 3. |
| `titulo` | `title` | Texto libre. |
| `tipo_fuente` | `source_type` | Uno de: txt, markdown, docx, pdf, xlsx, csv, imagen_escaneada. Siempre "markdown" en esta version de RAG Content. |
| `ruta_archivo` | `location` (tras resolucion) | Nunca se usa literal -- ver seccion 5. En V2: ruta relativa a `package_root`. En V1: ruta absoluta del equipo productor (solo se usa su nombre de archivo). |
| `area_propietaria` | `owner_area` | |
| `nivel_acceso` | `access_level` | Texto libre del lado de Content (metadato "nivel_confidencialidad", sin catalogo compartido). Un valor no reconocido cae a "interno" por defecto -- nunca "publico" en silencio. |
| `idioma` | `language` | Codigo de idioma, por ejemplo "es". |
| `hash_contenido` | `content_hash` + verificacion de integridad obligatoria | SHA-256 hexadecimal en minusculas del `.md` entregado (`Documento.hash_markdown`). Ver seccion 6. |
| `vigente_desde` / `vigente_hasta` | `valid_from` / `valid_to` | AAAA-MM-DD; vacio si no aplica. |
| `autoridad_fuente` | `source_authority` | Entero, 1 = maxima autoridad. Hoy RAG Content siempre lo deja vacio. |
| `sustituye_a` | `supersedes_source_id` | Solo se completa dentro de RAG Studio; RAG Content unicamente indica cual era el documento predecesor (via `Vigencia.sustituye_a`). |

## 5. Reglas de resolucion de `ruta_archivo`

### V2 (`manifest_schema_version` = `"2"`)

1. Debe ser una ruta relativa: no debe empezar con `/`, `~`, ni con un patron de unidad de Windows (`X:`).
2. Debe usar `/` como separador; nunca `\`.
3. No debe contener ningun segmento `..`.
4. Se resuelve como `package_root / ruta_archivo`; se verifica que el resultado, tras resolver symlinks, siga contenido dentro de `package_root` (defensa en profundidad -- mismo patron que `domain/projects/packaging.py` de RAG Studio usa para los paquetes `.agentproj`, con el mismo motivo: Zip Slip).
5. Cualquier violacion de 1-4 se rechaza con diagnostico explicito, sin intentar adivinar el archivo.

### V1 / legado (columna ausente o vacia)

1. Se extrae el ultimo segmento de `ruta_archivo` dividiendo por CUALQUIERA de los separadores `/` o `\` -- sin asumir cual uso el equipo productor (a diferencia de `pathlib.Path(...).name`, que solo reconoce el separador nativo del sistema operativo donde corre el proceso que lo interpreta, no el que genero la ruta).
2. Se buscan archivos con ese nombre exacto dentro de `package_root` (busqueda recursiva, por si un paquete legado tuviera subcarpetas).
3. 0 coincidencias -> rechazar.
4. Mas de 1 coincidencia -> rechazar como ambiguo (nunca elegir el primero en silencio).
5. Exactamente 1 coincidencia -> candidato valido, sujeto a verificacion de integridad (seccion 6).

## 6. Verificacion de integridad (obligatoria)

Antes de registrar cualquier fila (V1 o V2), con el archivo candidato ya localizado:

1. Si `hash_contenido` no esta vacio: se calcula el SHA-256 real del archivo candidato y se compara contra `hash_contenido`.
   - Coincide -> se continua.
   - No coincide -> se rechaza ("el archivo fue localizado, pero su contenido no coincide con el hash declarado en el manifiesto"). Nunca se registra un archivo cuyo contenido no coincide con lo declarado, aunque el nombre coincida.
2. Si `hash_contenido` esta vacio: se continua sin verificacion (caso puramente defensivo -- `Documento.hash_markdown` es obligatorio para que un documento llegue a LIBERADO en RAG Content, asi que no deberia ocurrir en un manifiesto real).

### 6.1 Precision (2026-09-30): el hash es de los bytes exactos

`hash_contenido` es el SHA-256 de los **bytes exactos** del `.md` entregado, en UTF-8 y sin ninguna traduccion de fin de linea. RAG Studio no normaliza CRLF/LF antes de comparar: hacerlo debilitaria la verificacion de integridad. Si el hash declarado viene en mayusculas (por ejemplo, editado a mano), RAG Studio lo pasa a minusculas antes de comparar; los bytes del archivo se comparan sin cambios.

Incidencia que origina la precision: un lote generado en Windows se rechazo completo ("Importadas: 0 / Omitidas: 14"). RAG Content escribia el `.md` en modo texto (Windows convierte `\n` en `\r\n`) y calculaba el hash sobre el texto con `\n`. Correccion en RAG Content:

- el `.md` se escribe como bytes (`write_bytes`), identico en cualquier sistema operativo;
- `hash_markdown` se calcula sobre los bytes del archivo ya escrito;
- la copia del `.md` en la carpeta de entrega se nombra con la misma funcion multiplataforma que `ruta_archivo` (`domain.documents.rutas`);
- "Preparar entrega" aplica la misma verificacion de esta seccion antes de dejar lista la carpeta; si algo no coincide o falta, no deja ninguna entrega y lista los archivos afectados (`EntregaIntegridadError`);
- `scripts/reparar_fin_de_linea_markdown.py` repara lotes ya generados: solo reescribe con `\n` los archivos cuya unica diferencia con el hash declarado son los CRLF, nunca cambia el hash, no toca filas ambiguas ni rutas fuera de la carpeta, y deja respaldo de los originales.

En RAG Studio solo cambiaron la lectura del manifiesto con `utf-8-sig` y la comparacion del hash declarado en minusculas. Pruebas de regresion: en RAG Studio, `test_register_sources_from_folder.py` (CRLF con hash de LF se sigue rechazando; manifiesto con BOM se lee como V2; hash en mayusculas); en RAG Content, `test_extraction_output_store.py`, `test_generar_markdown.py`, `test_entrega_rag_studio_store.py`, `test_ejecutar_pruebas_aceptacion.py` y `tests/unit/scripts/test_reparar_fin_de_linea_markdown.py`.

## 7. Deteccion de ambiguedad entre filas (no solo dentro de una fila)

Antes de importar, se agrupan todas las filas resueltas por archivo fisico final (ruta ya resuelta):

- Si dos o mas filas resuelven al MISMO archivo con `hash_contenido` DISTINTO -> todas esas filas se rechazan como ambiguas (no se importa ninguna; nunca "se elige la primera").
- Si dos o mas filas resuelven al mismo archivo con el MISMO `hash_contenido` -> se procesan en orden; la deduplicacion ya existente por `content_hash` (`RegisterSource`) decide cual se importa y cuales quedan como "ya estaba registrada" -- politica explicita y ya existente, no nueva.

## 8. Identidad, ubicacion e integridad (separacion conceptual)

- **Identidad** del documento: `Documento.id` (RAG Content) / `Source.id` (RAG Studio) -- nunca la ruta.
- **Ubicacion** dentro del paquete: `ruta_archivo` (V2: relativa validada; V1: nombre resuelto por busqueda).
- **Integridad** del contenido: `hash_contenido`, verificado fisicamente (seccion 6).

Estos tres conceptos no deben mezclarse ni sustituirse entre si en ningun cambio futuro de este contrato.

## 9. Catalogo minimo de mensajes de error

Ambos lados deben usar el mismo vocabulario para que un operador que ve un mensaje de un lado reconozca la misma situacion documentada aqui:

- "el manifiesto no trae ruta_archivo"
- "no se encontro '<nombre>' dentro del paquete"
- "referencia ambigua: '<nombre>' coincide con mas de un archivo dentro del paquete"
- "referencia ambigua: coincide con el mismo archivo que otra fila del manifiesto, con hash declarado distinto"
- "el archivo fue localizado, pero su contenido no coincide con el hash declarado en el manifiesto"
- "ruta_archivo no puede ser una ruta absoluta" (V2)
- "ruta_archivo no puede contener un segmento '..'" (V2)
- "ya estaba registrada (mismo contenido)" (deduplicacion, ya existente)

## 10. Compatibilidad hacia atras

Ningun paquete generado antes de esta version necesita ser editado a mano. RAG Studio sigue aceptando manifiestos V1 indefinidamente mediante el resolutor legado (seccion 5). RAG Content Studio genera SIEMPRE V2 desde esta version en adelante.

## 11. Pruebas de contrato exigidas (numeracion compartida entre ambos repos)

1. Paquete nuevo (V2), mismo equipo.
2. Paquete generado en Windows, importado en macOS/Linux.
3. Paquete generado en macOS/Linux, importado en otro entorno.
4. Paquete legado (V1) con ruta absoluta inexistente en destino, pero el `.md` si presente en el paquete.
5. Manifiesto que referencia un archivo que realmente no existe -> rechazar con diagnostico.
6. Ambiguedad legado: dos archivos candidatos para el mismo nombre resuelto -> rechazar.
7. V2 con `ruta_archivo` absoluta -> rechazar.
8. V2 con `ruta_archivo` conteniendo `..` -> rechazar.
9. Archivo encontrado pero `hash_contenido` no coincide -> rechazar.
10. Dos filas resuelven al mismo archivo con hash declarado distinto -> rechazar ambas.
11. Manifiesto sin version + ruta Windows -> aceptar via resolutor legado.
12. Manifiesto sin version + ruta POSIX -> aceptar via resolutor legado.
13. Manifiesto V2 con referencia relativa valida -> aceptar.
14. Paquete de ejemplo canonico ("golden package"): la misma estructura de archivos y manifiesto que produciria una corrida real de RAG Content Studio, verificada tanto del lado productor (el manifiesto que genera coincide con este contrato) como del lado consumidor (se importa correctamente) -- sin que exista un solo test que ejecute ambos repositorios en un mismo proceso (viven en entornos/virtualenvs separados), este caso se cubre con un fixture identico versionado en ambos repos.

## 12. Responsables por lado (donde vive el codigo de este contrato)

- **RAG Content Studio**: `application/documents/commands/generar_manifiesto.py`, `infrastructure/filesystem/csv_manifest_writer.py`, `domain/documents/entities.py::FilaManifiesto`.
- **RAG Studio**: `application/documents/commands/register_sources_from_folder.py` y el modulo de resolucion de manifiesto asociado (`domain/documents/manifest.py` + helpers de aplicacion).

## 13. Ronda 92 (2026-10-06): tolerancia de sistema de archivos e identidad de lote

**Resolucion tolerante (sin relajar integridad).** Si `ruta_archivo` (V2) o el nombre (V1) no existe literalmente, RAG Studio busca dentro del paquete un archivo cuya ruta relativa coincida salvo forma Unicode (NFC/NFD: macOS guarda acentos descompuestos) o mayusculas (Windows/macOS no las distinguen; Linux si). Solo se acepta si hay exactamente un candidato, y la verificacion de `hash_contenido` (seccion 6) se aplica igual. Mas de un candidato -> "referencia ambigua".

**Lectura del manifiesto.** Se acepta `;` como separador (Excel en configuracion regional en espanol) detectandolo en el encabezado. Un manifiesto que no esta en UTF-8 se rechaza con un mensaje que explica la causa. Un manifiesto sin la columna `ruta_archivo` se rechaza completo.

**Identidad del lote (multi-lote).** RAG Studio calcula, por cada carpeta importada, una huella `sha256:` sobre los pares (`nombre logico`, `hash_contenido`) ordenados -- nombre logico = `ruta_archivo` en V2, nombre de archivo en V1, separadores `/` y Unicode NFC. No participan rutas absolutas, carpeta de importacion, equipo, usuario, fecha ni orden de filas. Cada importacion queda en `projects/<id>/lotes_importados.jsonl` (append-only, viaja en `.agentproj` y en la instantanea) con su relacion respecto de lotes previos:

- `lote_nuevo`: sin documentos en comun;
- `reimportacion_identica`: misma huella que un lote importado completo (no se duplica nada);
- `nueva_version`: comparte nombres con un lote previo pero con contenido distinto;
- `comparte_documentos`: comparte documentos identicos y agrega o quita otros.

Una version nueva nunca retira ni sustituye fuentes del lote anterior en silencio; eso sigue siendo decision explicita con "Sustituye a". La etiqueta (`<lote>/vN` o nombre de carpeta) es informativa, no identidad. RAG Content no necesita cambios para este contrato.
