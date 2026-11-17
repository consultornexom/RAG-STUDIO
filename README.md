# RAG STUDIO

Plataforma local de escritorio para diseñar, construir, evaluar y
liberar agentes conversacionales RAG, siguiendo el ciclo completo de
las 8 etapas del documento maestro: Núcleo + Gobierno documental +
Ingesta + RAG + Diseño conversacional + Calidad + Liberación +
Complementos (Etapas 1-8).

Esqueleto de código construido siguiendo **ADR-001 (Arquitectura y
modelo de dominio)**.

**Etapa 1 (Núcleo).** Módulo 1 — administración de proyectos: crear,
clonar, archivar, exportar, importar, validar integridad y respaldar
proyectos, sobre SQLite global + SQLite por proyecto, con migraciones
Alembic independientes y una interfaz PySide6 mínima que nunca
bloquea.

**Etapa 2 (Gobierno documental).** Módulos 2 y 3 — inventario de
fuentes y metamodelo de metadatos, siguiendo el análisis ampliado de
`RAG STUDIO INVESTIGACION.odt` (actividad A1): catálogos jerárquicos,
campos configurables (nunca columnas rígidas), y la distinción
explícita entre vigencia, validación y autoridad de una fuente. Incluye
interfaz PySide6 (pestañas Fuentes y Metadatos) sobre el mismo backend
probado.

**Etapa 3 (Ingesta — núcleo).** Extracción de texto (TXT, Markdown,
DOCX, PDF con capa de texto) y fragmentación configurable por tipo
documental (actividades A2/A3 de `RAG STUDIO INVESTIGACION.odt`), con
herencia de metadatos marcados `inherited_by_chunks` y trazabilidad de
página. Incluye interfaz PySide6 (pestaña Ingesta: Laboratorio de
extracción + Diseñador de fragmentación) que ejecuta extracción y
fragmentación en segundo plano, sobre la fuente activa elegida en la
pestaña Fuentes. Sin OCR, sin enriquecimiento automático todavía.

**Etapa 4 (RAG — núcleo).** Indexación vectorial y búsqueda semántica
sobre los `Chunk` que produce la Etapa 3, siguiendo el puerto
`VectorStore` de ADR-001 (sección 8) con una corrección confirmada
contra la documentación oficial vigente (ver "Limitaciones conocidas"
y bitácora): el adaptador por defecto usa el **Local Mode** estándar
de `qdrant-client` (`QdrantClient(path=...)`), no "Qdrant Edge" —
Qdrant Edge es un producto real pero distinto, en beta y orientado a
dispositivos embebidos/IoT, no a una app de escritorio. Los
embeddings se generan localmente con `fastembed` (modelo
multilingüe, sin API keys ni costo por uso). Incluye una sección "RAG"
dentro de la pestaña Ingesta (indexar la fuente activa + buscar
semánticamente sobre el proyecto o solo esa fuente), ejecutada en
segundo plano igual que extracción/fragmentación. Sin comparador de
configuraciones de embeddings ni reranking — eso queda para una
iteración posterior del Laboratorio RAG.

No cubre todavía RAG conversacional, reglas de negocio ni banco de
pruebas (Etapas 5-8) — esas entidades y módulos se añaden en las
siguientes iteraciones sin romper esta base.

## Requisitos

- Python 3.10 o superior.
- Para la interfaz de escritorio (opcional para correr pruebas):
  PySide6-Essentials y, en Linux, las bibliotecas nativas de Qt
  (`libegl1`, `libgl1`, `libxkbcommon0` o equivalentes). Ver
  "Limitaciones conocidas" más abajo.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
pip install -e .                 # instala el paquete en modo editable
pip install -r requirements.txt  # instala todas las dependencias (pruebas, interfaz, OCR, empaquetado)
```

`requirements.txt` unifica lo que antes eran cuatro archivos separados
(`requirements-dev.txt`, `requirements-ui.txt`, `requirements-ocr.txt` y
`requirements-packaging.txt`) -- un solo paso de instalación en vez de
tener que elegir cuáles de los cuatro instalar según lo que se vaya a
usar. Esos archivos separados siguen existiendo por compatibilidad,
pero ya no es necesario instalarlos aparte: su contenido ya está
incluido en `requirements.txt`. Si se prefiere instalar solo un
subconjunto (por ejemplo, para un entorno de producción sin
herramientas de desarrollo), los extras de `pyproject.toml` siguen
disponibles: `pip install -e .[ui,ocr]`.

OCR además requiere el binario de Tesseract instalado en el sistema
operativo (`requirements.txt` no lo incluye -- es un paquete de
Python, no el motor OCR en sí):

```bash
sudo apt install tesseract-ocr tesseract-ocr-spa   # Ubuntu/Debian
brew install tesseract tesseract-lang              # macOS
```

Sin esto, la app sigue funcionando igual que siempre (un PDF escaneado
solo produce una advertencia por página, sin extraer nada) -- OCR es
puramente opcional.

## Ejecutar la interfaz

```bash
python run_app.py
```

La primera vez crea automáticamente la instalación local en una
subcarpeta `data/` dentro de esta misma carpeta de la aplicación (junto
a `run_app.py`) -- ahí viven `application.db`, cada proyecto, los
modelos de embeddings en caché y los logs, autocontenidos junto al
código, sin dispersarse en una carpeta de perfil del sistema operativo.
(Antes de la tercera ronda de madurez post-8-etapas, el valor por
defecto sí era una carpeta de perfil del sistema operativo --
`%APPDATA%\RAGStudio` en Windows, `~/Library/Application Support/
RAGStudio` en macOS, `~/.local/share/ragstudio` en Linux -- ver
bitácora 2026-07-28 para el detalle del cambio.)

Puedes elegir otra ubicación de dos formas: fijando la variable de
entorno `RAGSTUDIO_HOME` (por ejemplo `RAGSTUDIO_HOME=/otra/ruta python
run_app.py`), o llamando a `app.lifecycle.start(base_dir=...)`
directamente en vez de usar el valor por defecto.

Por defecto, la búsqueda semántica usa un modelo de embeddings ligero
y simétrico. Si tus documentos son sobre todo listas cortas (planes de
estudio, catálogos, tablas) y buscas con preguntas en lenguaje natural,
puedes cambiar a un modelo más pesado pero más preciso en ese caso (ver
README, bitácora 2026-07-26) con una variable de entorno, sin tocar
código:

```bash
RAGSTUDIO_EMBEDDING_PROFILE=asimetrico_e5_large python run_app.py
```

Ten en cuenta: descarga ~2.25 GB la primera vez (contra ~250 MB del
modelo por defecto) y tarda más en indexar. Si ya tienes un proyecto
indexado con un modelo y cambias de perfil, reindexar esa fuente
lanzará `EmbeddingDimensionMismatchError` — hay que reindexar todo el
proyecto con el modelo nuevo, no se pueden mezclar los dos.

## Demo con un documento real

```bash
python demo_plan_estudios.py
```

Registra `plan de estudios ingenieria industrial.docx` como fuente,
la extrae, la fragmenta por encabezado, la indexa y corre tres
búsquedas semánticas de ejemplo, usando la misma instalación por
defecto que abre `run_app.py` (así que después puedes abrir la
interfaz y ver el proyecto y sus fragmentos ahí). Requiere internet la
primera vez, para que `fastembed` descargue el modelo de embeddings.

## Ejecutar las pruebas

```bash
pytest
```

Incluye pruebas unitarias (dominio y casos de uso con dobles de
prueba), de integración (exportación/importación .agentproj entre dos
"instalaciones" simuladas, con verificación de hash; migraciones
Alembic de las cuatro líneas independientes; extracción real de
archivos .txt/.md/.docx/.pdf generados en la propia prueba; indexación
y búsqueda semántica reales contra `qdrant-client` en modo local) y de
humo (arranque completo de la aplicación, no-bloqueo del administrador
de trabajos, redacción de datos sensibles en los registros). Dos
pruebas de `fastembed` real se omiten automáticamente si no hay
conexión a Hugging Face (ver "Limitaciones conocidas").

## Qué cubre esta iteración (criterios de aceptación)

**Etapa 1**

- [x] Un proyecto creado, exportado a `.agentproj` e importado en otra
      instalación produce el mismo contenido (hash idéntico).
- [x] Alterar un solo byte de un archivo dentro del paquete hace que la
      verificación de integridad lo detecte y rechace la importación.
- [x] El administrador de trabajos (`workers.jobs.ThreadJobRunner`)
      regresa el control de inmediato al iniciar una tarea larga; la
      tarea sigue avanzando en segundo plano y puede cancelarse.
- [x] Las dos líneas de migración Alembic (global y por proyecto)
      aplican y revierten sin pérdida de datos ni mezcla entre esquemas.
- [x] Ningún dato con forma de credencial (`password=`, `token=`, etc.)
      llega en texto plano al archivo de registro.
- [x] La UI (`ui/projects/main_window.py`) solo llama a `application`;
      nunca importa `domain` ni `infrastructure` directamente, y delega
      toda tarea larga a `application.jobs`.

**Etapa 2**

- [x] Un campo de tipo catálogo/selección (ej. plantel, programa)
      nunca puede crearse sin referenciar un catálogo — se rechaza a
      nivel de dominio, no solo en la interfaz.
- [x] Asignar a una fuente un valor fuera de su catálogo permitido se
      rechaza antes de guardarse.
- [x] Vigencia, validación y autoridad son campos independientes:
      `Source.is_usable_for_responses()` exige validado *y* vigente a
      la vez; ninguno de los dos por separado basta.
- [x] La migración `0002` (fuentes + metamodelo) aplica y revierte sin
      afectar las tablas de la Etapa 1 (`project`, `configuration`).
- [x] Fuentes, esquema, catálogos y valores de metadatos viajan dentro
      de `project.db` y sobreviven un export/import `.agentproj` entre
      dos instalaciones distintas, sin cambios en el empaquetador.
- [x] El reporte de cobertura (`MetadataService.get_coverage_report`)
      calcula qué porcentaje de fuentes tiene todos sus campos
      obligatorios completos — operacionaliza el criterio de A1 de
      INVESTIGACION.odt (≥95% de fuentes describibles sin texto libre
      no controlado). La interpretación exacta de la métrica está
      declarada en el docstring de `get_coverage_report.py`, no es cita
      literal de la fuente.
- [x] La interfaz (`ui/sources/panel.py`, `ui/metadata/panel.py`)
      cubre el inventario de fuentes (registrar, listar, cambiar
      estado de validación respetando las transiciones permitidas) y
      el diseñador de metadatos (crear esquema, agregar y editar
      campos con catálogo obligatorio cuando el tipo lo exige, crear/
      renombrar/eliminar catálogos y editar/eliminar sus entradas, y
      consultar el reporte de cobertura), siguiendo la misma regla de
      capa que Etapa 1: solo llaman a `application`, nunca a `domain`
      ni `infrastructure`.
- [x] No se puede eliminar un catálogo referenciado por un campo del
      esquema activo, ni una entrada de catálogo que ya esté guardada
      como valor de metadatos de alguna fuente — ambos bloqueos se
      aplican a nivel de dominio/aplicación, no solo deshabilitando el
      botón en la interfaz.

**Etapa 3**

- [x] `IngestionService.extract_source_text` extrae texto real de
      TXT, Markdown, DOCX y PDF con capa de texto (`pypdf`,
      `python-docx`); un tipo no soportado (XLSX, CSV, HTML, JSON,
      XML, imagen escaneada, API, base de datos) se rechaza con
      `UnsupportedSourceTypeError`, no con un error genérico.
- [x] Los encabezados DOCX (`Heading N`, `Title`) se normalizan a
      Markdown (`#`) en el extractor, así que la estrategia
      `POR_ENCABEZADO` funciona igual sin importar el formato de
      origen.
- [x] Cada `Chunk` conserva trazabilidad hasta su fuente, sección
      (`section_title`) y página (`page_start`/`page_end`, calculada a
      partir de los saltos de página reales del PDF) — criterio de
      aceptación de A2 (INVESTIGACION.odt).
- [x] Un campo marcado `inherited_by_chunks=True` en el esquema activo
      se copia al `inherited_metadata` de cada fragmento; uno sin esa
      marca nunca se propaga, aunque tenga valor guardado.
- [x] `FragmentationPolicy` se resuelve por `document_type_code` (un
      código libre, no un enum fijo: el tipo documental real vive como
      metadato configurable, no como columna rígida) con una cadena de
      resolución: política específica → política `"default"` del
      proyecto → parámetros internos de A2 (500/60/80 tokens).
- [x] Volver a fragmentar la misma fuente con la misma política borra
      los fragmentos anteriores (`delete_for_source`) y genera un
      conjunto lógico equivalente — criterio de aceptación de
      reproducibilidad de A3. Los identificadores nunca se prometen
      estables entre corridas.
- [x] La migración `0003` (extracción + fragmentos + políticas) aplica
      y revierte sin afectar las tablas de las Etapas 1-2.
- [x] Extracciones, fragmentos y políticas viajan dentro de
      `project.db` y sobreviven un export/import `.agentproj` entre
      dos instalaciones distintas, sin cambios en el empaquetador
      (tercera vez que se confirma esta propiedad, tras Etapas 1 y 2).
- [x] La interfaz (`ui/ingestion/panel.py`) cubre extracción y
      fragmentación de la fuente activa: ambas se ejecutan en segundo
      plano vía `application.jobs.submit_task` (nunca en el hilo de
      la interfaz), con vista previa del texto extraído y advertencias,
      configuración de política de fragmentación (document_type_code,
      estrategia, tokens objetivo/solapamiento/mínimo), y lista de los
      fragmentos resultantes con su sección y páginas. Un trabajo
      fallido (p. ej. tipo de fuente no soportado) se muestra como
      error, no como crash.
- [x] El botón "Cancelar" llama a `JobHandle.cancel()`
      (`workers.jobs.ThreadJobRunner`, Etapa 1) y se habilita/deshabilita
      correctamente según haya o no un trabajo en curso. Se reporta
      honestamente el resultado: como `extract_source_text` y
      `fragment_source` no son cooperativos (no revisan
      `is_cancelled()` a mitad de camino, a diferencia de
      `demo_long_task`), el trabajo ya en curso termina y sus datos se
      guardan igual; el panel lo dice explícitamente en el mensaje de
      estado en vez de dar la impresión de que la cancelación borró
      algo que en realidad se guardó.

**Etapa 4**

- [x] `RagService.index_source` embebe el texto de cada `Chunk` de una
      fuente (`fastembed`, modelo local) y lo sube al índice vectorial
      del proyecto (`qdrant-client` en modo local); una fuente sin
      fragmentos todavía devuelve 0 sin error, no una excepción.
- [x] Antes de subir los vectores nuevos de una fuente se borran los
      anteriores (`VectorStore.delete_for_source`) — volver a indexar
      la misma fuente nunca acumula puntos duplicados, incluso después
      de volver a fragmentarla (los ids de `Chunk` no son estables
      entre corridas de fragmentación, igual que en la Etapa 3).
- [x] Mezclar en el mismo índice vectores de dos modelos de embeddings
      con dimensiones distintas se rechaza con
      `EmbeddingDimensionMismatchError`, a nivel de dominio, no solo
      como una advertencia.
- [x] `RagService.search` embebe la consulta, busca en el índice y
      devuelve el `Chunk` completo (texto, sección, página) uniendo el
      resultado del índice vectorial con `ChunkRepository` — el
      índice solo guarda id + metadatos, nunca duplica el contenido.
- [x] La búsqueda admite filtrar por `source_id`; un punto huérfano
      (p. ej. el `Chunk` ya no existe) se omite en el resultado en vez
      de hacer fallar toda la búsqueda.
- [x] El estado del índice (proveedor, modelo, dimensiones, cantidad
      de puntos) se guarda por proyecto en `project.db`
      (`index_info`, migración `0004`) y se puede consultar sin abrir
      Qdrant.
- [x] El directorio del índice vectorial (`indexes/qdrant/` dentro de
      cada proyecto) viaja dentro de `.agentproj` y sobrevive un
      export/import entre dos instalaciones distintas, sin cambios en
      el empaquetador (cuarta confirmación de esta propiedad
      arquitectónica, tras Etapas 1, 2 y 3).
- [x] Se confirmó contra la documentación oficial vigente de
      `qdrant-client` (regla de actualización de información del
      Documento Maestro, sección 5) que "Qdrant Edge" nombrado en
      ADR-001 no aplica a este caso de uso; se corrigió hacia el
      Local Mode estándar, y esa corrección quedó registrada en
      bitácora en vez de dejarse como una nota perdida.
- [x] `IndexSource` descarta los fragmentos que son solo un
      encabezado sin cuerpo propio (su texto es exactamente su
      `section_title`, p. ej. "Plan de Estudios" antes de "1er.
      Cuatrimestre") antes de embeberlos e indexarlos — no aportan
      nada a la búsqueda semántica y competían contra fragmentos con
      contenido real; siguen existiendo como `Chunk` normal para
      navegar la estructura del documento, solo no se indexan.
- [x] La interfaz (sección "RAG" dentro de `ui/ingestion/panel.py`)
      permite indexar la fuente activa y buscar semánticamente
      (sobre todo el proyecto o solo la fuente activa, con una
      casilla), ambas en segundo plano vía
      `application.jobs.submit_task`; el estado del índice (modelo,
      dimensiones, cantidad de fragmentos) se muestra en cuanto hay un
      proyecto activo, sin necesidad de reindexar para verlo.

## Limitaciones conocidas

- **Clonar un proyecto solo copia metadatos administrativos del
  proyecto** (Módulo 1), no fuentes ni esquema de metadatos todavía.
- **El comparador de proyectos es parcial**: compara estado y número de
  entradas de configuración. La comparación completa (versiones de
  metadatos, fragmentación, reglas, pruebas e índice) llega junto con
  esas entidades en etapas posteriores.
- **El adaptador VectorStore (Qdrant local) ya existe** desde la Etapa
  4 (`infrastructure/vectorstores/qdrant_local_store.py`); esta nota
  quedó desactualizada en una iteración intermedia (se confirmó la API
  antes de construir, luego se construyó) y se corrige aquí para no
  dejar información falsa en el README.
- **Ya hay un andamiaje de empaquetado (PyInstaller), no un instalador
  terminado todavía** (ítem 7 de la segunda evaluación de madurez
  post-8-etapas, ver bitácora y `packaging/README.md` para el detalle
  completo y honesto). `packaging/ragstudio.spec` genera
  `dist/RAGStudio/` (modo *onedir*) con `pyinstaller packaging/ragstudio.spec
  --noconfirm --clean` -- pero PyInstaller nunca compila para un
  sistema operativo distinto al que lo ejecuta, así que hay que
  correrlo en Windows para Windows y en macOS para macOS. En este
  entorno de construcción (Linux) se validó que la fase de resolución
  de imports corre sin errores durante ~40 segundos reales sobre todo
  el árbol de dependencias (PySide6, SQLAlchemy/Alembic,
  `qdrant-client`, las dependencias transitivas de `fastembed`,
  `keyring`, los submódulos plugin de `tiktoken_ext`), pero **no se
  completó una compilación real de punta a punta ni se corrió el
  ejecutable resultante en ningún sistema operativo** -- este entorno
  mata cualquier proceso en segundo plano entre una llamada de shell y
  la siguiente, y una compilación completa de un árbol tan pesado tarda
  varios minutos. Sigue faltando: icono de la app, firma de código,
  empaquetado final por sistema operativo (`.msi`/`.dmg`/`.deb`, cada
  uno con su propia herramienta), y validar el almacén seguro de
  credenciales en los tres sistemas operativos reales (ADR-001, sección
  11) -- nada de eso es parte de este ítem. Como beneficio colateral
  real (no solo para el empaquetado): se corrigió un bug latente en
  `infrastructure.database.migrations` que habría impedido correr las
  migraciones Alembic dentro de un ejecutable congelado (buscaba
  `migrations/` subiendo desde el archivo hasta encontrar
  `pyproject.toml`, que no existe empaquetado) -- ahora también busca
  en `sys._MEIPASS` cuando la app corre así, con pruebas reales que lo
  confirman (aunque, otra vez con honestidad, simulando `_MEIPASS` con
  `monkeypatch`, no contra un ejecutable real).
- **La UI de Documentos/Metadatos sigue siendo deliberadamente
  simple** en algunos puntos: no hay reordenamiento de campos ni
  edición de field_id/tipo de dato una vez creado el campo (por
  diseño: cambiar el tipo podría invalidar valores ya guardados sin
  aviso); el reporte de cobertura se consulta a demanda (no se
  refresca solo). Editar y eliminar campos/catálogos/entradas ya está
  cubierto (ver bitácora). **Asignar valores de metadatos a una fuente
  ya tiene interfaz** (sub-pestaña "Valores por fuente" en Metadatos,
  ver bitácora 2026-07-27) -- `MetadataService.set_source_metadata_value`
  existía desde Etapa 2, pero hasta esta corrección solo era alcanzable
  llamando a `application` directamente (pruebas/scripts), nunca desde
  la interfaz: un usuario real no podía etiquetar una fuente sin
  código. El selector de valor cambia automáticamente a una lista
  desplegable de entradas válidas cuando el campo está ligado a un
  catálogo, para no depender de que el usuario escriba a mano un
  código de catálogo válido.
- **`SourceMetadataValue` no conserva historial.** `save_value` hace
  upsert por (source_id, field_id): guarda el valor vigente, no cada
  cambio. Si se necesita auditoría de cambios de metadatos, hay que
  versionar esta tabla en una iteración posterior.
- **Una fuente `SUSTITUIDO`/`VENCIDO`/`RECHAZADO` es terminal** en esta
  iteración (no hay "reactivar"); si se necesita revertir, se registra
  como fuente nueva.
- **OCR: opcional, no instalado por defecto.** Con el extra `ocr`
  instalado (`pip install ragstudio[ocr]` o `requirements.txt`, que ya
  lo incluye) más el binario de Tesseract en el sistema operativo,
  `PdfTextExtractor`
  reconoce el texto de páginas sin capa de texto (ver bitácora
  2026-07-27) e `ImageTextExtractor` reconoce el texto de una imagen
  registrada directamente como fuente `imagen_escaneada` (ver bitácora
  2026-07-27). Sin esas dependencias, ambos siguen igual que antes de
  Módulo 4: solo una advertencia clara, sin extraer nada -- no es un
  requisito para usar el resto de la app. **XLSX y CSV ya tienen
  extractor real** (`XlsxExtractor`/`CsvExtractor`, ver bitácora
  2026-07-27 -- cerraron una brecha real frente al alcance mínimo
  obligatorio de la primera versión, "Debe incluir: ... Extracción de
  PDF, DOCX, XLSX, CSV y texto."): cada hoja/archivo se convierte en
  una tabla Markdown (mismo formato que ya producía `DocxExtractor`
  para tablas DOCX), así que `FragmentationStrategy.POR_TABLA` los
  reconoce igual sin importar el origen. HTML, JSON, XML, API y base de
  datos siguen sin extractor (`UnsupportedSourceTypeError`) -- quedan
  pendientes para una iteración posterior si un caso real lo
  justifica.
- **6 de las ~11 estrategias de fragmentación de INVESTIGACION.odt
  están implementadas**: las 3 genéricas de Etapa 3 (`por_tamaño`,
  `por_encabezado`, `documento_completo`) más 3 por tipo documental de
  Módulo 5 (`por_articulo`, `pregunta_respuesta`, `por_tabla`, ver
  bitácora 2026-07-27). El resto de la tabla "Reglas recomendadas por
  tipo documental" —convocatoria, procedimiento, ficha de programa,
  formato, página web— no tiene estrategia dedicada todavía: se cubren
  razonablemente con `por_encabezado`/`por_tamaño` y quedan como
  trabajo futuro solo si un caso real lo justifica. Tampoco hay
  tratamiento dedicado de "excepciones que no deben separarse de su
  regla" fuera de mantener el artículo/pregunta completos.
- **`split_by_tables` reconoce tablas en formato Markdown (fila de
  encabezado + separador de guiones + filas, todas con "|")**, no
  cualquier tabla. Para DOCX esto ya no es una limitación real:
  `DocxExtractor` convierte las tablas reales del documento a este
  formato antes de fragmentar (ver bitácora 2026-07-27). Para PDF sigue
  siendo una limitación de fondo: `PdfTextExtractor` no reconstruye
  tablas (pypdf extrae el texto de una tabla como líneas sueltas, sin
  bordes ni columnas) -- una tabla en PDF hoy se fragmenta como texto
  narrativo, no como tabla.
- **El conteo de tokens ya puede usar un tokenizador real** (ver
  bitácora 2026-07-27) -- ya no es una limitación de fondo. `TiktokenCounter`
  (adaptador `tiktoken`, codificación `cl100k_base`) se conecta como
  `TokenCounter` opcional en `FragmentSource`; si no está disponible (sin
  conexión para la primera descarga, paquete no instalado) se cae de
  vuelta, en caliente y sin romper la corrida, a la aproximación por
  palabras de siempre (`domain.ingestion.splitting.word_count`). El
  conteo real de tokens BPE normalmente difiere del conteo por palabras
  (puntuación, subpalabras), así que el tamaño real de los fragmentos
  puede variar levemente respecto a corridas anteriores en proyectos ya
  fragmentados con la aproximación.
- **Búsqueda textual (BM25) e híbrida (RRF) ya implementadas** (ver
  bitácora 2026-07-27) -- ya no es una limitación real. El filtro
  "solo fuentes vigentes y validadas" (ver bitácora 2026-07-27, misma
  fecha) es opt-in -- por defecto la búsqueda sigue viendo todo lo
  indexado, incluidos borradores, porque Etapa 4 es un laboratorio de
  prueba; un motor conversacional real (Etapa 5, sin empezar) debería
  forzar siempre ese filtro para respuestas a un usuario final. El
  reranking por RRF combina semántica+textual, pero no hay un
  cross-encoder/LLM de reranking dedicado (decisión deliberada, ver
  bitácora, por el costo de esa dependencia).
- **Pipeline reproducible por lote (Etapa 3) ya implementado** (ver
  bitácora 2026-07-27) -- ya no es una limitación real. Queda un
  alcance deliberadamente acotado: `document_type_code` es un solo
  parámetro por corrida, no por fuente (no hay hoy manera de decirle al
  pipeline "esta fuente es un artículo, esta otra es pregunta+respuesta"
  dentro de la misma corrida); asignar tipo documental por fuente
  requeriría un campo nuevo en `Source` o una convención de metadatos,
  ambos fuera de alcance de esta pieza. La incrementalidad se basa en
  el hash real del archivo en `Source.location` al momento de la
  corrida (no en `Source.content_hash`, que existe en el modelo pero
  ninguna pantalla de la UI lo calcula todavía).
- **Diseño conversacional (Etapa 5) ya implementado** (ver bitácora
  2026-07-27) -- ya no es una limitación real. Alcance deliberadamente
  acotado para esta primera versión: cada catálogo (intenciones,
  guardrails, esquemas de canalización) admite Crear + Activar/
  Desactivar + listar, no edición completa campo por campo (ni
  duplicar, agrupar, detectar conflictos automáticamente, aprobación
  formal o versionado explícito -- del catálogo de acciones que pide
  el documento maestro para guardrails). El emparejamiento de
  intención es un heurístico léxico (similitud de Jaccard, con una
  lista de conectores comunes del español filtrada -- ver bitácora),
  no un clasificador de lenguaje natural ni un LLM -- mismo criterio ya
  usado para BM25 en Etapa 4 ("la pieza central no es el modelo
  generativo ni la base vectorial", documento maestro). La canalización
  se SIMULA (genera el paquete estructurado) en vez de integrarse con
  sistemas externos reales (correo, CRM, ticket...) -- decisión
  explícita del propio documento maestro para esta iteración. El
  simulador opera consulta por consulta (una sola ronda de aclaración),
  no mantiene una conversación multivuelta con memoria entre llamadas.
- **Calidad (Etapa 6) ya implementada** (ver bitácora 2026-07-27) -- ya
  no es una limitación real. El banco de pruebas evalúa lo que el
  `SimulationTrace` de Etapa 5 produce (intención, variables, acción,
  canalización, fuente/fragmento recuperado), no criterios que
  exigirían juzgar una respuesta en lenguaje natural -- "claridad",
  "citación", "ausencia de invenciones", "fundamentación" del
  documento maestro quedan fuera de alcance porque esta herramienta no
  genera texto con un modelo de lenguaje (misma decisión de fondo que
  Etapa 4/5: "la pieza central no es el modelo generativo"). De los
  tipos de ejecución del documento maestro ("Individual. Por
  categoría. Completa. Regresión. Comparación entre modelos. Comparación
  entre índices. Comparación entre reglas. Comparación entre prompts.")
  se cubren los primeros cuatro; comparar corridas completas entre
  distintos modelos de embeddings/índices/catálogos de reglas/prompts
  queda para una iteración posterior (el comparador de modelos A/B de
  Etapa 4 ya resuelve una comparación puntual a nivel de una sola
  búsqueda, no de todo el banco de pruebas). El banco de pruebas admite
  Crear + Activar/Desactivar + listar, sin edición completa.
- **Liberación (Etapa 7) ya implementada** (ver bitácora 2026-07-27) --
  ya no es una limitación real. `ReleaseService.evaluate_gates`
  verifica 6 compuertas (metadatos, fragmentación, pipeline, índice,
  diseño conversacional, calidad) contra los seis contextos previos, y
  `request_release` bloquea la liberación (`ReleaseStatus.BLOQUEADA`)
  si cualquiera falla -- exactamente lo que
  `EvaluationRun.has_blocking_failures` (Etapa 6) dejó preparado.
  Alcance deliberadamente acotado: no hay compuerta de Etapa 1
  ("Objetivo/Usuarios/Alcance/Fuentes iniciales/Riesgo") porque
  `Project` no tiene esos campos -- agregarlos sería alcance de Etapa 1,
  no de Etapa 7. Las compuertas se evalúan solo al solicitar una
  liberación, no como bloqueo preventivo dentro de cada pestaña anterior
  (sigue siendo posible, por ejemplo, crear un chunk sin esquema de
  metadatos aprobado) -- retrofitar ese bloqueo en cada pantalla de las
  Etapas 2-6 es un cambio mucho más invasivo que se deja para una
  iteración posterior si un caso real lo justifica. Los 8 entregables
  formales del documento maestro se siguen compilando como un dict JSON
  inline en `ReleaseRecord.deliverables_report` (consultable en el
  historial de liberaciones) Y AHORA además se pueden exportar como un
  paquete `.zip` real en disco (ítem 6 de la evaluación de madurez
  post-8-etapas, ver bitácora) con
  `ReleaseService.export_deliverables_package` -- un manifest.json, el
  dictamen en texto plano, el checklist de compuertas y un archivo JSON
  por entregable. Sigue sin haber perfiles de exportación
  (completo/plantilla/kit inicial/solo índice aprobado, como describe
  INVESTIGACION.odt) ni generación de documentos Word/PDF a partir del
  reporte -- el paquete es siempre "todo lo que hay", en JSON legible,
  no un documento con formato.
- **Complementos (Etapa 8) ya implementada** (ver bitácora 2026-07-27)
  -- ya no es una limitación real. El documento maestro enumera 4
  tipos bajo "Complementos": Plantillas, Nuevos proveedores,
  Importadores, Evaluadores personalizados; los 4 están cubiertos por
  un registro global (`application.db`, no `project.db` -- un
  complemento no pertenece a un proyecto) más un cargador dinámico real
  (`domain/plugins/loader.py`, vía `importlib`) que valida que la clase
  de un complemento realmente implemente el contrato de dominio
  esperado (`EmbeddingProvider` para proveedor, `TextExtractor` para
  importador, un `CustomEvaluator` nuevo para evaluador; una plantilla
  es solo datos de configuración, sin contrato de código). Alcance
  deliberadamente acotado, coherente con la propia recomendación del
  documento maestro de que "la primera versión no debería intentar
  cubrir todos los conectores y modelos posibles": esta iteración
  entrega el **mecanismo de registro y carga**, no complementos reales
  de terceros ya integrados -- registrar un proveedor de embeddings no
  hace que `RagService`/`app/bootstrap.py` lo usen automáticamente
  (seguir siendo necesario construirlo explícitamente en el bootstrap,
  como hoy). **Un `CustomEvaluator` ya se invoca de verdad durante una
  corrida real** (ver bitácora 2026-07-27): `RunEvaluation` carga y
  ejecuta cada complemento EVALUADOR activo contra cada caso de prueba,
  sumando sus rechazos como hallazgos AMARILLO -- ya no es una
  limitación real. Una plantilla se puede registrar con su
  configuración por defecto, pero no existe todavía un flujo "crear
  proyecto desde esta plantilla" que aplique esos valores
  automáticamente (`Project.template_id` sigue siendo solo una
  referencia de texto libre). **Los secretos de `Plugin.config` (API
  keys y similares) ya se guardan en el almacén seguro de credenciales
  del sistema operativo cuando hay uno disponible** (ítem 2 de la
  segunda evaluación de madurez post-8-etapas, ver bitácora) --
  `RegisterPlugin` detecta claves con nombre sensible (`api_key`,
  `secret`, `token`, `password`, `credential`...) y las guarda vía
  `KeyringCredentialStore` (Windows Credential Locker/Keychain de
  macOS/Secret Service en Linux), dejando solo un marcador en
  `application.db`. Sin un backend real disponible (headless, sin
  sesión gráfica/daemon de credenciales -- el caso de este entorno de
  construcción, confirmado) cae de vuelta a texto plano, igual que
  antes de este ítem, con una advertencia clara en el log -- nunca fue
  ni es un requisito para usar el resto de la app.
- **La extracción prefiere la copia local en `sources/original/`
  cuando existe** (ítem 4 de la evaluación de madurez post-8-etapas,
  ver bitácora), y si no, sigue leyendo `Source.location` directamente
  -- caso de fuentes registradas antes de este cambio, tipos sin
  archivo real (api/base_de_datos), o cuando la copia falló al
  registrar. La copia se intenta al registrar la fuente y se
  reintenta si se corrige la ubicación mientras siga sin bloquear
  (antes de la primera extracción); una vez que hay extracción
  guardada, ubicación y copia quedan congeladas junto con el resto de
  los campos estructurales.
- **Sin enriquecimiento automático** (clasificación temática,
  entidades, resumen, palabras clave): `chunk_type` solo se asigna
  como `TEXTO`; `REQUISITO` y `EXCEPCION` existen en el enum pero
  ningún divisor los produce todavía. `semantic_summary` siempre queda
  `None`.
- **La UI de Ingesta ya no apila todo en una sola columna** (ver
  bitácora 2026-07-27: sub-pestañas por etapa) -- lo que queda
  deliberadamente simple es de fondo, no de distribución: no hay
  comparador de políticas lado a lado (Módulo 5 lo pide: "Política A
  vs Política B" con número de fragmentos/tamaño promedio) ni edición
  manual de la extracción antes de fragmentar (Módulo 4: corregir
  secciones, marcar zonas excluidas, reprocesar páginas).
- **"Cancelar" ya interrumpe de verdad extracción y fragmentación —
  pero indexación y búsqueda todavía no.** `ExtractSourceText` y
  `FragmentSource` reciben ahora un `is_cancelled` (el mismo
  `JobHandle.is_cancelled` de `workers.jobs`) y lo revisan antes de
  persistir; `FragmentSource` además lo revisa en cada vuelta del
  bucle por fragmento, así que en una fuente con muchos fragmentos
  puede abortar a la mitad sin terminar el resto. En ningún caso se
  guarda un resultado parcial: si se cancela, los datos anteriores de
  la fuente (si había) quedan intactos. La extracción en sí
  (`pypdf`/`python-docx`) sigue siendo una sola llamada atómica sin
  puntos de control internos, así que ahí la cancelación es "antes de
  empezar" o "después de terminar pero antes de guardar", no una
  interrupción real a mitad del parseo — se documenta así para no
  sobrevender la mejora. `IndexSource.execute` (embeber + subir al
  VectorStore) y `RagService.search` todavía no revisan ningún
  indicador: son llamadas únicas a `embed_texts`/`upsert` sin un bucle
  propio donde el punto de control salga barato; queda para una
  iteración futura si se indexan lotes grandes.
- **`ThreadJobRunner` ya puede rechazar dos trabajos sobre el mismo
  recurso lógico a la vez** (ítem 3 de la segunda evaluación de madurez
  post-8-etapas, ver bitácora): `submit(fn, key=...)` reserva `key`
  antes de lanzar el hilo y lanza `JobAlreadyRunningError` si ya hay un
  trabajo en curso con esa misma clave, en vez de dejarlos correr en
  carrera. La UI usa esta clave para extraer/fragmentar/indexar una
  misma fuente (`f"ingesta:{project_id}:{source_id}"`, compartida entre
  las tres operaciones para que se excluyan mutuamente entre sí, no
  solo cada una consigo misma) y para el pipeline reproducible y una
  corrida de evaluación (`f"pipeline:{project_id}"` /
  `f"evaluacion:{project_id}"`, a nivel de proyecto). Alcance
  deliberadamente acotado: la búsqueda y el comparador de modelos son
  de solo lectura y no llevan `key` (no hay nada que proteger); el
  pipeline reproducible reserva su propia clave de proyecto pero no la
  de cada fuente individual que procesa por dentro, así que en teoría
  un trabajo manual sobre una fuente todavía podría solaparse con un
  pipeline que esté procesando esa misma fuente en ese instante --
  cerrar esa brecha del todo requeriría que el pipeline reserve también
  la clave de cada fuente mientras la procesa, lo que queda para una
  iteración posterior si un caso real lo justifica. En la práctica,
  cada panel de la interfaz ya se autolimitaba a un solo trabajo activo
  a la vez (`_active_job is not None`) antes de este ítem, así que la
  garantía nueva es sobre todo para cualquier otro llamador que no pase
  por ahí (un script, una prueba, un futuro trabajo por lote), no la
  corrección de un error reproducible desde la interfaz actual.
- **`ThreadJobRunner` ya admite un límite configurable de trabajos
  ejecutando de verdad al mismo tiempo** (ítem 4 de la segunda
  evaluación de madurez post-8-etapas, ver bitácora):
  `max_concurrent_jobs` (parámetro de `ThreadJobRunner`, expuesto en
  `AppSettings`/`load_settings`/`bootstrap`/`app.lifecycle.start` igual
  que `embedding_profile`, y por variable de entorno
  `RAGSTUDIO_MAX_CONCURRENT_JOBS`) -- `None` por defecto, sin límite,
  el comportamiento exacto de siempre. Cierra en parte lo que pide
  ADR-001 sección 10 ("configurar procesos máximos... de los trabajos
  en segundo plano"), pero solo la parte de "cuántos a la vez": memoria
  máxima, tamaño de lote, uso de CPU/GPU y prioridad siguen sin
  implementarse. `ProcessJobRunner` (procesos separados de verdad, en
  vez de hilos) sigue siendo un stub sin implementar -- su docstring
  ahora lo dice honestamente (antes decía, ya desactualizado, "se
  implementa junto con el orquestador de ingesta (Etapa 3)", y Etapa 3
  se completó hace tiempo sin que esto se construyera). En la práctica,
  todo el trabajo pesado real (OCR, fastembed, tiktoken, fragmentación)
  corre en hilos de `ThreadJobRunner`, no en procesos separados;
  funciona porque buena parte de ese trabajo libera el GIL de Python
  (E/S de archivos, las partes en C/C++ de `pypdf`/`pytesseract`/
  `onnxruntime`), pero implementar `ProcessJobRunner` de verdad
  requeriría resolver cómo cruzar `application`/`domain` (sesiones de
  SQLAlchemy no son picklables) entre procesos, y queda para una
  iteración futura si el volumen de datos reales de un proyecto lo
  justifica.
- **Las excepciones no capturadas ya quedan registradas en el log, y
  hay un paquete de diagnóstico exportable** (ítem 5 de la segunda
  evaluación de madurez post-8-etapas, ver bitácora): antes, un crash
  fuera de los `try`/`except` explícitos de application/UI/
  `ThreadJobRunner` no dejaba ningún rastro utilizable para
  diagnosticar un problema real del usuario. `install_global_exception_hooks`
  (`app/logging_setup.py`) instala `sys.excepthook`/`threading.excepthook`
  al bootstrapear, así que cualquier excepción así queda con su
  traceback completo en `ragstudio.log` (Ctrl+C/`KeyboardInterrupt` se
  excluye a propósito: es una interrupción intencional, no un error).
  Además, el menú "Ayuda -> Exportar diagnóstico…" de la ventana
  principal (no depende de un proyecto activo, igual que Complementos)
  exporta un `.zip` con `info.json` (versión de RAG STUDIO, versión de
  Python, sistema operativo) y una copia de `logs/`, listo para
  adjuntar a un correo o ticket de soporte sin que el usuario tenga que
  ir a buscar la carpeta de instalación a mano. Alcance deliberadamente
  acotado: no hay telemetría ni envío automático a ningún servidor --
  el usuario decide si comparte el paquete y con quién; tampoco hay un
  "modo diagnóstico" que aumente el nivel de detalle del log en
  caliente (habría que reiniciar con `log_level="DEBUG"` para eso, si
  algún día se agregan registros a ese nivel).
- **Ya hay medición de cobertura y un pipeline de integración continua
  real** (ítem 6 de la segunda evaluación de madurez post-8-etapas, ver
  bitácora): antes no existía ninguna configuración de `pytest-cov`,
  `ruff`, `mypy` ni `black` en `pyproject.toml`, ni ningún workflow de
  CI -- nada evitaba que una regresión pasara inadvertida hasta que
  alguien corriera `pytest` manualmente. `.github/workflows/tests.yml`
  corre en cada push/PR (aunque este repositorio no vive todavía en un
  remoto de GitHub -- queda listo para cuando lo haga): un job rápido y
  determinista (`unit + smoke`, sin red) que además exige
  `--cov-fail-under=80` sobre `app`/`application`/`domain`/
  `infrastructure`/`workers` (medido en ~82% en esta iteración), y un
  job informativo de `tests/integration/` (`continue-on-error: true`,
  sin gate de cobertura, porque varias de esas pruebas dependen de
  red/backend real y se omiten explícitamente cuando no están
  disponibles). Con integración incluida, esos mismos paquetes suben a
  ~95% de cobertura real -- ese número es informativo, no el que
  bloquea CI. `ui/` queda deliberadamente fuera del umbral: sus widgets
  Qt reales necesitan un servidor gráfico que no hay en este entorno de
  construcción ni en un runner de CI típico, y se siguen validando
  manualmente en la máquina del usuario (`checklist_validacion_visual.md`);
  la lógica ya extraída de Qt (`ui/conversational/parsing.py`,
  `ui/ingestion/search_highlighting.py`, `ui/release/gate_status_logic.py`)
  sí tiene pruebas reales y aparece con cobertura real en el reporte.
  Ruff/mypy/black siguen sin configurarse -- fuera de alcance de este
  ítem, que se centró en pruebas automatizadas, no en estilo estático.
- **Una extracción vigente por fuente (upsert), con historial de
  auditoría aparte** (ítem 5 de la evaluación de madurez
  post-8-etapas, ver bitácora): `extraction_record` sigue siendo la
  extracción vigente; `extraction_record_history` guarda cada intento
  anterior. Igual patrón para `source_metadata_value` (valor vigente)
  y la nueva `metadata_value_change` (auditoría de cada cambio real).
  `MetadataSchema`/`FieldDefinition` (esquema y campos) siguen sin
  historial propio -- fuera del alcance de este ítem.
- **`fastembed` necesita descargar el modelo de Hugging Face la
  primera vez que se usa.** Sin esa conexión inicial,
  `FastEmbedEmbeddingProvider.embed_texts` lanza
  `EmbeddingProviderError` con un mensaje claro (verificado: no es un
  traceback crudo). Una vez descargado, queda en caché
  (`InstallationPaths.models_dir()`, compartida por todos los
  proyectos de la instalación) y no vuelve a necesitar red. En este
  entorno de construcción no hay salida a Hugging Face, así que las
  pruebas que dependen de una descarga real se omiten explícitamente
  (ver bitácora) — en la laptop real del usuario, con internet, sí se
  ejecutan.
- **Modelo de embeddings por defecto:
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (384
  dimensiones, ~220 MB, multilingüe), elegido en vez del modelo de
  ejemplo de la documentación de fastembed/qdrant-client
  (`BAAI/bge-small-en-v1.5`, solo inglés) porque las fuentes reales de
  RAG STUDIO son en español. No se comparó exhaustivamente contra
  otros modelos multilingües disponibles (`multilingual-e5-large` da
  mejor calidad pero pesa 10× más) — cambiar de modelo es un parámetro
  del constructor de `FastEmbedEmbeddingProvider`, no un cambio de
  arquitectura.
- **Un índice vectorial por proyecto, sin versionado ni comparación de
  configuraciones de embeddings.** ADR-001, sección 5, describe
  `EmbeddingModelConfig`/`Index` como entidades versionadas para poder
  comparar varias configuraciones a la vez; esta iteración solo guarda
  el estado vigente (`IndexInfo`, upsert por proyecto) — cambiar de
  modelo sin reindexar todo el proyecto se bloquea
  (`EmbeddingDimensionMismatchError`), pero no hay todavía un flujo
  para comparar "modelo A vs modelo B" lado a lado.
- **Sin reranking ni orquestación conversacional.** `RagService.search`
  devuelve los resultados en el orden que da la similitud de coseno de
  Qdrant, sin un paso de reordenamiento adicional; `Intent`,
  `RetrievalConfig` y `Rule`/`Guardrail` de ADR-001 (sección 5) son
  trabajo de Etapas 5-6, no de este núcleo.
- **`RagService.index_source` opera una fuente a la vez.** No hay
  todavía un comando "indexar todo el proyecto" que recorra todas las
  fuentes automáticamente; se puede lograr llamando al método una vez
  por fuente desde código o desde la interfaz (una fuente a la vez,
  ver bitácora), pero no hay un atajo de conveniencia en la fachada.
- **La búsqueda semántica de la interfaz no tiene reranking ni
  resaltado del texto coincidente** — muestra el fragmento completo
  (recortado a ~140 caracteres) y el score de similitud, en el orden
  que da Qdrant. Suficiente para validar que la indexación funciona;
  una vista de resultados más rica es trabajo de UI futuro.
- **`demo_plan_estudios.py` (raíz del proyecto) ejecuta el pipeline
  completo sobre un documento real** (`plan de estudios ingenieria
  industrial.docx`, con texto real y encabezados `Heading 3`/`Heading
  4`): registra la fuente, extrae, fragmenta por encabezado (16
  fragmentos, uno por cuatrimestre, uno de ellos sin cuerpo propio y
  ya excluido de la búsqueda — ver bitácora) e indexa + busca
  semánticamente. Ya se ejecutó de punta a punta en la laptop real del
  usuario con `fastembed` real (modelo descargado, 384 dimensiones) —
  confirma que el pipeline completo de las Etapas 1-4 funciona sobre
  contenido real, no solo en pruebas con dobles.
- **El modelo de embeddings por defecto (simétrico) responde peor a
  preguntas en lenguaje natural contra listas de nombres de materias
  sin descripción que un modelo asimétrico -- CONFIRMADO con una
  corrida real comparando ambos (ver bitácora 2026-07-26).** Con
  `paraphrase-multilingual-MiniLM-L12-v2`, "¿Qué materias se llevan en
  el primer cuatrimestre?" no ubicaba "1er. Cuatrimestre" entre los
  tres mejores resultados (scores 0.25-0.32). Con
  `intfloat/multilingual-e5-large` (asimétrico, `embed_query`/
  `embed_texts` con prefijos `query:`/`passage:`), "1er. Cuatrimestre"
  pasó a ser el resultado #1 (score 0.860) -- confirma que la causa era
  el modelo, no un defecto de `IndexSource`/`SemanticSearch`. A cambio,
  es un modelo mucho más pesado (1024 dimensiones y ~2.25 GB de
  descarga, contra 384 dimensiones y ~250 MB del modelo por defecto) y
  sus scores de similitud viven en una escala distinta (todo por
  encima de ~0.8, típico de la familia E5 -- las diferencias relativas
  entre resultados siguen siendo informativas, pero un score absoluto
  ya no se puede comparar contra los del modelo simétrico). Sigue sin
  ser el modelo por defecto: cambiarlo es una decisión de producto
  (tamaño de descarga/RAM vs. calidad de búsqueda en lenguaje natural),
  no solo técnica -- pendiente de decidir con el usuario.

## Bitácora de esta iteración

- **2026-08-11 — ADR-002 (runtime de producción) y Fase 1: publicar
  instantáneas de proyecto.** A pedido explícito del consultor, se
  analizó si además de RAG CONTENT STUDIO y RAG STUDIO falta una
  tercera herramienta para cerrar el ciclo completo de un agente
  conversacional real. Conclusión, confirmada contra el código (sin
  ningún import de Qt en domain/ ni application/): no falta una
  tercera herramienta de escritorio -- falta una interfaz adicional que
  exponga el motor conversacional ya construido a un canal real. Se
  documentó la decisión en
  `docs proyecto/RAG_STUDIO_ADR-002_Runtime_Produccion.docx` (extensión
  de ADR-001) y se implementó su Fase 1: nuevo mecanismo
  `PublishProjectSnapshot` (`domain/release/entities.py` -- entidad
  `ProjectSnapshot`; `application/release/commands/
  publish_project_snapshot.py`; `infrastructure/filesystem/
  project_snapshot_publisher.py`, con checkpoint de WAL de SQLite antes
  de copiar; migración `0013_project_snapshot.py`) que copia
  project.db + índice Qdrant a un directorio de solo lectura
  versionado (`snapshots/<project_id>/v<n>/`), separado de
  `projects/<project_id>` donde la app sigue editando en vivo -- para
  que un futuro runtime no compita por el lock exclusivo que
  `QdrantClient(path=...)` toma sobre su directorio mientras está
  abierto. Se agregó una prueba de integración real (contra
  `qdrant_client`, no un doble) que reproduce ese lock y confirma que
  la estrategia de instantáneas lo evita
  (`tests/integration/test_project_snapshot_qdrant_isolation.py`).
  Nuevo botón "Publicar instantánea…" en la pestaña de Liberación,
  independiente de solicitar una liberación formal (mismo criterio que
  Exportar proyecto/Generar respaldo). Se continuó en la misma ronda
  con la Fase 2: una API HTTP mínima y separada (`interfaces/api/`,
  hermana de `ui/`) que sirve el motor conversacional ya construido
  (`ConversationalService.simulate`) leyendo siempre de la instantánea
  publicada más reciente -- nunca del proyecto en edición -- con
  bitácora de conversaciones reales (`domain/runtime/`,
  `SqlAlchemyConversationLogRepository`), caché por proyecto+versión
  (`RuntimeContext`) y autenticación por `X-API-Key`
  (`interfaces/api/app.py`, nuevo extra `api` en `pyproject.toml`).
  Deliberadamente no genera lenguaje natural: cuando la decisión es
  "responder", el texto de respuesta queda en `None` y solo viajan los
  fragmentos recuperados, igual que el Simulador -- RAG STUDIO nunca
  implementó ese paso (ADR-001, sección 8). Probada de punta a punta
  contra Qdrant/SQLite/FastAPI reales
  (`tests/integration/test_runtime_api.py`). Se cerró la ronda con la
  Fase 3: un widget de chat embebible en cualquier sitio web
  (`interfaces/api/widget_assets.py`, JavaScript sin dependencias ni
  paso de compilación, aislado del sitio anfitrión con Shadow DOM) que
  habla directamente con el endpoint de la Fase 2, servido desde un
  nuevo `GET /widget.js` público, más CORS configurable
  (`allowed_origins`/`RAGSTUDIO_WIDGET_ALLOWED_ORIGINS`, desactivado
  por defecto). Mismo criterio que el resto del runtime: sin
  generación de lenguaje natural (si no hay `response_text`, muestra
  los fragmentos recuperados tal cual). Dos límites documentados a
  propósito, no ocultos: no hay memoria de conversación entre turnos
  (mismo límite que ya tenía el motor, ahora visible para un visitante
  real) y la `X-API-Key` incrustada en el `<script>` solo es apta para
  un piloto de un solo sitio de confianza, no para una integración
  pública -- un token acotado por proyecto queda diferido a la Fase 4.
  Probado con `tests/integration/test_widget_channel.py`; el
  comportamiento real en un navegador (Shadow DOM, panel de chat) no
  se pudo automatizar en este entorno de construcción (sin acceso de
  red para descargar Chromium) y quedó como paso manual nuevo en
  `checklist_validacion_visual.md`. Se cerró la ronda con la Fase 4:
  token de widget acotado por proyecto (`domain/runtime.WidgetToken`,
  `POST`/`GET`/`DELETE /projects/{id}/widget-tokens`, protegidos por la
  API key global; el widget ahora prefiere `X-Widget-Token` sobre la
  API key global) -- cierra el riesgo de seguridad documentado en la
  Fase 3. Además, la primera integración real de canalización: hasta
  ahora, incluso en producción, CANALIZAR solo mostraba un texto --
  `infrastructure/channeling/webhook_dispatcher.py`
  (`WebhookChannelingDispatcher`) entrega de verdad un webhook HTTP
  saliente configurable (`RAGSTUDIO_CHANNELING_WEBHOOK_URL`/
  `_SECRET`), con solo `urllib.request` de la biblioteca estándar (sin
  agregar `requests`/`httpx` como dependencia nueva). El secreto se lee
  de una variable de entorno a propósito, no reforzando
  `infrastructure/security/keyring_credential_store.py` -- ese almacén
  está pensado para credenciales de la app de ESCRITORIO y degrada mal
  en un proceso de SERVIDOR headless; la inyección por variable de
  entorno es el mecanismo estándar para procesos de servidor, no un
  atajo. Un fallo de entrega nunca rompe la respuesta al visitante.
  Probado de punta a punta con un guardrail real disparando CANALIZAR
  a través de `POST /messages` (FastAPI real) hasta un servidor HTTP
  real (`tests/integration/test_channeling_end_to_end.py`), además de
  `test_widget_tokens_api.py` y `test_webhook_channeling_dispatcher.py`.
  Se cerró el plan de 5 fases del ADR-002 con la Fase 5, el "lazo de
  mejora continua": nueva pestaña **Monitoreo** en RAG STUDIO
  (`ui/monitoring/panel.py`) que lee la misma bitácora de
  conversaciones reales que ya escribe `interfaces/api/` (Fase 2) desde
  `runtime.db` -- filtrable por acción -- y permite promover cualquiera
  a un caso de prueba real del banco de calidad
  (`PromoteConversationToTestCase`, `application/runtime/
  service.py::RuntimeMonitoringService`, conectado en
  `app/bootstrap.py`). No necesita que el proceso API esté corriendo:
  `runtime.db` es un SQLite normal en modo WAL, se lee igual que
  cualquier otro `.db` de la instalación.
  `InstallationPaths.runtime_db_path()` es ahora el único punto de
  verdad para esa ruta (antes vivía repetida como literal en
  `interfaces/api/app.py`). Probado de punta a punta: `interfaces/api/`
  (FastAPI real) atiende un mensaje real y lo registra en `runtime.db`;
  después, con instancias de repositorio separadas (mismo patrón que
  dos procesos distintos), la app de escritorio lo lee y lo promueve a
  un `TestCase` real (`tests/integration/test_monitoring_end_to_end.py`,
  `test_runtime_repositories.py`). El panel Qt en sí no se pudo
  instanciar en este entorno de construcción (falta `libEGL`, mismo
  límite ya documentado para toda `ui/`) -- quedó como paso manual en
  `checklist_validacion_visual.md`. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 9, para el detalle
  completo -- con esto no queda ninguna fase pendiente del plan
  original del ADR-002.

  **Ronda 10, misma fecha -- paquete de entrega al cliente + auditoría
  fresca.** A pedido del consultor, antes de tocar el Manual del
  Usuario: (a) se verificó que existiera un paquete real para entregar
  el runtime a quien lo vaya a operar por cuenta del cliente -- no
  existía (lo único parecido, "Exportar entregables…" de Etapa 7, es
  evidencia de gobernanza, no artefactos de despliegue) -- y se
  construyó `DeploymentPackage`/`FilesystemDeploymentPackager`/
  `ExportDeploymentPackage` (nuevo botón "Exportar paquete de entrega
  al cliente…" en Liberación): instantánea + token de widget +
  snippet + guía técnica + informe formal en un solo .zip. (b) Una
  auditoría dedicada, independiente de la implementación, sobre todo
  ADR-002 y el paquete nuevo encontró y corrigió varios bugs reales no
  detectados durante las Fases: el widget no se dibujaba en el caso
  normal de uso (`document.currentScript` leído en el momento
  equivocado); dos visitantes concurrentes podían tumbar el runtime
  con un 500 (dos causas distintas: el lock de Qdrant y, descubierto
  al escribir la prueba de concurrencia, variables globales de Alembic
  no seguras entre hilos); el paquete de entrega no era desplegable en
  una máquina nueva (nueva variable `RAGSTUDIO_SNAPSHOT_DIR`, que de
  paso fija la instantánea servida en vez de seguir la última
  publicada sin aviso); una instantánea ausente respondía en silencio
  como proyecto vacío en vez de fallar explícito; y varios hallazgos
  menores (token huérfano/.zip truncado ante un fallo del
  empaquetador, clave operativa pública en la plantilla de entorno,
  comparación de la API key no en tiempo constante, límite de tamaño
  de mensaje ausente). Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 10 (puntos 35-36), para el detalle completo, incluida la lista
  de deuda técnica señalada pero deliberadamente no resuelta en esta
  ronda.

  **Manual del Usuario actualizado, misma fecha.** Tras cerrar (a) y
  (b) de la Ronda 10, se actualizó `RAG_STUDIO_Manual_de_Usuario.docx`:
  nuevo capítulo 11 "Pestaña Monitoreo" (con ejemplos concretos de
  conversaciones reales promovidas a caso de prueba), nuevas secciones
  10.4/10.5 ("Publicar instantánea"/"Exportar paquete de entrega al
  cliente…", que faltaban documentar desde antes de esta ronda), y
  renumeración de los capítulos 11-16 a 12-17 con todas sus referencias
  cruzadas. Se corrigió también una afirmación ya desactualizada en el
  anexo de alcance ("RAG STUDIO no sirve el agente en producción" --
  ya no es del todo cierto desde el runtime exportable).

  **Ronda 11, misma fecha -- ¿el entregable es de grado profesional?**
  A pedido del consultor, se analizó el código real del runtime
  (`interfaces/api/`) para responder si el paquete de entrega al
  cliente es de grado profesional. Diagnóstico: sólido en seguridad y
  arquitectura, pero le faltaba la capa operativa (observabilidad,
  límite de tasa, empaquetado reproducible, retención de datos). Se
  cerraron las dos brechas más rápidas de resolver: (1) se descubrió y
  corrigió un defecto real preexistente en `app/logging_setup.py` --
  `configure_logging` solo capturaba lo escrito directamente sobre el
  objeto que devolvía, no los `logging.getLogger(__name__)` que ya usa
  el resto del código (incluido el aviso de fallo del webhook de
  canalización), así que casi ningún log de módulo llegaba nunca a
  `ragstudio.log`, en TODA la aplicación, no solo en el runtime nuevo
  -- corregido configurando el logger raíz; (2) se agregó registro
  operativo real en `interfaces/api/` (arranque, accesos rechazados,
  mensajes atendidos sin texto de usuario) y un límite de tasa
  opcional por IP en `POST /messages` (`RAGSTUDIO_RATE_LIMIT_PER_MINUTE`,
  apagado por defecto), con `Retry-After` al excederse. Empaquetado
  reproducible (Docker/systemd), retención/cifrado de `runtime.db`,
  escalabilidad multi-proceso, reintentos del webhook y estado
  conversacional multi-turno del widget quedan documentados como deuda
  técnica explícita, no resueltos en esta ronda. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 11 (puntos 37-39).

  **Ronda 12, misma fecha -- cierre de las brechas restantes.** A
  pedido del consultor, se cerraron las cinco brechas que la Ronda 11
  dejó pendientes: (1) retención/purga de `runtime.db`
  (`PurgeOldConversations`, `python -m interfaces.api.purge_conversations
  --retention-days N`, sin valor por defecto a propósito -- cuántos
  días conservar es decisión del cliente); (2) empaquetado operativo
  reproducible (`packaging/api/`: Dockerfile, docker-compose de
  referencia y tres unidades systemd, con el comando `uvicorn`
  subyacente verificado real de punta a punta y las unidades validadas
  con `systemd-analyze verify`); (3) reintentos acotados del webhook de
  canalización ante fallos transitorios de red; (4) estado
  conversacional multi-turno en el widget (recuerda, en el navegador,
  la pregunta original y la variable pedida cuando el agente necesita
  aclarar algo, sin ningún cambio en el motor conversacional ni en el
  servidor); y (5) escalabilidad más allá de un proceso -- verificada
  con procesos `uvicorn` reales, no solo documentada: dos procesos
  apuntando a la MISMA carpeta de instantánea produjeron fallos reales
  con 500 bajo carga concurrente real (el candado exclusivo del índice
  local no protege entre procesos sin relación entre sí, solo dentro de
  uno), mientras que dos réplicas con una copia propia cada una
  atendieron la misma carga sin errores y con más rendimiento conjunto
  -- de ahí la recomendación documentada en `GUIA_DESPLIEGUE.md`
  (sección 11): varias réplicas detrás de un balanceador, cada una con
  su propia copia de la instantánea, compartiendo un solo `runtime.db`.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 12 (puntos 40-43),
  para el detalle completo, incluida la deuda técnica que sigue
  deliberadamente fuera de alcance.

  **Ronda 13, misma fecha -- desalojo de caché de RuntimeContext.**
  Del backlog de tres puntos que dejó la Ronda 12, el consultor pidió
  avanzar solo con el más rápido y de menor riesgo: `RuntimeContext`
  ahora desaloja, al cargar una versión nueva de un proyecto, las
  versiones anteriores del MISMO proyecto (nunca las de otros
  proyectos) -- sin esto, un proceso de larga duración al que se le
  publicara una instantánea nueva del mismo proyecto una y otra vez
  acumulaba en memoria, sin límite, cada versión superada (incluido su
  proveedor de embeddings), aunque `get_latest` nunca vuelve a pedirla.
  Enrutar la canalización por esquema, Monitoreo remoto por HTTP y el
  rendimiento del camino caliente (este último, de alcance mayor al
  runtime -- afecta a todos los repositorios `SqlAlchemy*` de la
  aplicación) quedan, a propósito, sin construir: backlog a la espera
  de un requerimiento concreto, no deuda olvidada. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 13 (punto 44).

  **Ronda 14, misma fecha -- verificación final antes de liberar.**
  Revisión dedicada a buscar detalles finos pendientes antes de cerrar
  esta serie de rondas: se encontró y corrigió uno real -- `send()` en
  el widget no bloqueaba un segundo envío mientras el primero seguía
  en curso, así que un doble clic por impaciencia podía disparar dos
  solicitudes cuyas respuestas, si llegaban fuera de orden, se pisaban
  el estado de conversación entre sí sin ningún error visible.
  Corregido con una bandera `sendInFlight` que ignora un segundo
  intento y deshabilita el campo mientras se espera. No se encontró
  nada más pendiente (sin `TODO`/`FIXME` sueltos, numeración de
  `GUIA_DESPLIEGUE.md` correcta, `manifest.json` del paquete de entrega
  sin necesidad de cambios). Ronda final de pruebas para liberar: 542
  unitarias, 230 de integración y 15 de humo en verde, `ruff` sin
  hallazgos -- ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 14
  (punto 45).

  **Ronda 15, 2026-08-12 -- brechas entre el modelo de dominio y los
  diálogos de la interfaz.** El consultor señaló una nota concreta del
  Manual del Usuario (sección 6.1, campo `multiple`/"valor múltiple" de
  `FieldDefinition`) y pidió revisar si el mismo patrón -- una
  capacidad que domain/application ya soportan por completo, pero
  ningún diálogo de `ui/` expone -- se repetía en otros lugares.
  Revisión sistemática de las nueve entidades con diálogo propio;
  cerradas dos brechas reales, documentada una tercera como backlog:
  (1) `FieldDefinition.multiple`/`filterable`/`inherited_by_chunks`
  ahora tienen casilla en "Agregar/Editar campo" -- cerrando además un
  hallazgo adicional: editar un campo sin estas casillas lo reseteaba
  en silencio a `False` aunque estuviera en `True` por otra vía; (2)
  `Source.language`, `supersedes_source_id` y la detección real de
  duplicados por huella de contenido (`content_hash`, ya soportada de
  punta a punta en `RegisterSource` pero nunca activada desde el alta
  manual) ahora tienen control en "Registrar/Editar fuente" -- de paso
  se reescribieron los mensajes de `DuplicateSourceError` y
  `SourceStructuralFieldsLockedError`, que citaban el nombre técnico
  del parámetro en Python en vez del nombre visible en la interfaz;
  (3) `Project` (siete campos descriptivos sin ningún control, más
  cinco transiciones de estado manuales sin control propio más allá de
  "Archivar") es, por un margen amplio, la brecha más grande del mismo
  patrón, pero se documenta como backlog en vez de construirse de
  forma apresurada -- requiere un formulario de alta nuevo (hoy es un
  solo `QInputDialog` de texto) y una decisión de producto sobre el
  mecanismo deseado para las transiciones de estado, no un ajuste de
  código. 546 pruebas unitarias y 230 de integración en verde (18
  omitidas, 2 fallas preexistentes y ajenas de `tiktoken`), `ruff` sin
  hallazgos. Se actualizaron el Manual del Usuario (5.2, 5.3, 6.1) y
  `checklist_validacion_visual.md` (secciones 2 y 3) -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 15 (puntos 46-48).

  **Ronda 16, misma fecha -- detalle fino final y precisión de
  ejemplos en el Manual del Usuario.** Antes de liberar, se revisó si
  quedaba algún detalle fino de la Ronda 15: el selector "Esta fuente
  sustituye a" listaba las fuentes candidatas sin su estado de
  validación, por lo que se podía elegir a ciegas una fuente ya
  "sustituido" o "rechazado" -- no fallaba, pero tampoco avisaba.
  Corregido mostrando el estado entre corchetes en cada candidata,
  igual que la lista principal de fuentes. Además, a pedido del
  consultor, se revisaron sistemáticamente los más de 40 puntos del
  Manual del Usuario que usan ejemplos: la mayoría ya eran precisos,
  pero se reescribieron seis que eran genéricos (5.2 registrar fuente,
  6.1 valor múltiple, 7.3 fragmentación -- que solo mencionaba tres de
  las seis estrategias reales, sin ningún número concreto --, 8.3
  guardrails, 12.2 complementos y 14.8 mensajes comunes, estos últimos
  actualizados también para coincidir con la redacción real de los
  mensajes tras la Ronda 15), hilados con un mismo caso concreto (el
  registro de un "Reglamento de Becas 2026" de un plantel) para que se
  pueda seguir de una sección a otra. 546 unitarias, 230 de integración
  y 15 de humo en verde, `ruff` sin hallazgos -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 16 (punto 49).

  **Ronda 17, misma fecha -- corrección de desviaciones de
  documentación no detectadas en rondas anteriores.** Se cerró un
  detalle fino de código: "Sustituye a" en el detalle de una fuente
  mostraba el identificador crudo de la fuente sustituida en vez de su
  título, porque `_refresh_detail` no lo resolvía contra
  `document_service.get_source(...)`. Corregido, con fallback seguro
  al id crudo si la fuente ya no existiera. El grueso de esta ronda fue
  un cotejo sistemático, botón por botón y mensaje por mensaje, del
  Manual del Usuario contra el código real de nueve secciones (6.1
  Esquema, 6.2 Catálogos, 6.3 Cobertura, 6.4 Valores por fuente, el
  estado "Completo, con errores" citado de tres formas distintas en
  7.1/14.1/17.4, los botones "Editar…" de las cuatro sub-pestañas de
  Diseño conversacional, 9.1 Banco de pruebas y 12.3 Complementos):
  todas resultaron ser desviaciones de documentación -- funcionalidad
  ya construida en rondas anteriores que el manual nunca llegó a
  describir, o describía con el texto de una versión anterior del
  formulario. Ninguna requirió cambios de código. 546 unitarias, 230 de
  integración y 15 de humo en verde, `ruff` sin hallazgos -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 17 (punto 50).

  **Ronda 18, misma fecha -- evaluación honesta del grado profesional
  de RAG STUDIO como fuente de materia prima para un agente
  conversacional externo.** A pedido del consultor, un dictamen de
  madurez (sin cambios de código ni de documentación de usuario),
  construido leyendo directamente el código de siete ejes: compuertas
  de calidad antes de liberar, seguridad de la API/runtime,
  confiabilidad y aislamiento de fallos, operación y despliegue,
  pruebas y CI, brechas ya documentadas como backlog, y
  multi-tenencia/gobierno de datos. Hallazgo principal (punto 51):
  `PublishProjectSnapshot` es deliberadamente independiente de
  `RequestRelease` -- publicar la instantánea que sirve al agente
  conversacional externo no exige haber aprobado una liberación
  formal, y la interfaz no advierte si las compuertas no se
  cumplieron; queda documentado como pendiente de decisión de
  producto, no corregido en esta ronda. Verificadas como fortalezas
  reales: seis compuertas de calidad que sí bloquean una liberación,
  arranque fail-closed de la API (sin `RAGSTUDIO_API_KEY` el proceso
  no levanta), aislamiento de fallas en pipeline y webhooks, y CI con
  ruff/mypy/bandit obligatorios. Brechas concretas para un grado de
  producción multi-cliente sin supervisión: rate limiting apagado por
  defecto, sin multi-tenencia real, CI sin repositorio remoto activo
  todavía, la única prueba de carga documentada no representativa de
  hardware real, sin cifrado en reposo de conversaciones capturadas ni
  postura explícita de privacidad, y sin métricas/alertas activas.
  **Veredicto:** piloto controlado / MVP operable bajo supervisión
  directa del consultor -- sólido en curación y calidad de datos, no
  aún listo para autoservicio sin supervisión o múltiples clientes con
  SLA reales. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 18
  (punto 51).

  **Ronda 19, misma fecha -- actualizaciones de valor real,
  seleccionadas tras la evaluación de grado profesional.** El
  consultor pidió proceder solo con lo que valía la pena de la
  recomendación de la Ronda 18: dos piezas de ingeniería acotadas y un
  entregable de documentación, descartando deliberadamente Graph RAG y
  mover la generación de lenguaje natural hacia RAG STUDIO (ambas, por
  decisión de diseño, no por omisión). (1) `conversation_id` real de
  extremo a extremo: nuevo campo en `ConversationLogEntry`, nuevo
  `ConversationLogRepository.list_for_conversation`, migración aditiva
  segura (`ALTER TABLE`) para instalaciones con un `runtime.db` de
  antes de esta ronda, `HandleIncomingMessage`/`MessageRequest`/
  `MessageResponse` que lo generan/reenvían, el widget que lo mantiene
  entre turnos, y un prefijo "conv:" nuevo en la lista de Monitoreo.
  (2) `CachingEmbeddingProvider` (nuevo, `infrastructure/embeddings/`):
  caché LRU en memoria del lado consulta de cualquier proveedor de
  embeddings, conectado en `RuntimeContext._build` -- se descarta junto
  con cada instantánea cuando se desaloja una versión superada, nunca
  sirve un resultado obsoleto. (3) `CONTRATO_INTEGRACION.md` (nuevo,
  dentro del paquete de entrega al cliente): para quien construya el
  agente conversacional externo, no para quien opera el servicio --
  forma real de la API, semántica de cada `action`, plantilla de
  system prompt recomendada. 550 unitarias (+4), 247 de integración
  (+17) y 15 de humo en verde, `ruff` sin hallazgos -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 19 (puntos 52-54).

  **Ronda 20, misma fecha -- auditoría de detalle sobre la Ronda 19,
  a pedido del consultor ("¿algo que corregir antes de liberar?").**
  Se revisó, punto por punto, cada pieza de la Ronda 19 (dominio,
  aplicación, infraestructura, API, widget, UI, pruebas y
  documentación) buscando inconsistencias reales, no cosméticas. Un
  solo hallazgo real: `RuntimeMonitoringService.list_conversation_thread`
  (Ronda 19) quedó implementado y probado a nivel de repositorio/API,
  pero sin ningún punto de entrada en la pestaña Monitoreo -- el mismo
  patrón de brecha dominio/aplicación-sin-UI que ya se corrigió varias
  veces en rondas anteriores de este proyecto (ver, por ejemplo, la
  Ronda 9 sobre catálogos). El prefijo "conv:xxxxxxxx" ya dejaba notar
  qué filas compartían conversación, pero reconstruirla completa
  seguía exigiendo salir de RAG STUDIO. Corregido: nuevo botón "Ver
  conversación completa…" en `ui/monitoring/panel.py`, junto a
  "Promover a caso de prueba…", que abre una ventana de solo lectura
  con todos los turnos de la conversación seleccionada, del más
  antiguo al más reciente. Se agregó además la prueba unitaria que
  faltaba para ese método de servicio (`test_runtime_monitoring_service.py`)
  y se actualizaron el Manual del Usuario (nueva sección 11.2) y el
  checklist de validación visual (sección 8, paso 5) en consecuencia.
  El resto de la Ronda 19 (esquema HTTP, migración aditiva de
  `conversation_id`, `CachingEmbeddingProvider`, contenido de
  `CONTRATO_INTEGRACION.md` contra el código real, incluida la
  verificación puntual de que `only_usable_sources=True` sí se aplica
  en el camino real del runtime) se revisó y se confirmó correcto y
  congruente, sin cambios. 551 unitarias (+1), 247 de integración (sin
  cambio de conteo, misma cobertura ya suficiente) y 15 de humo en
  verde, `ruff` sin hallazgos -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 20. **Veredicto:**
  con esta corrección, el entregable queda listo para liberar.

- **2026-08-19 — ADR-003 (evolución hacia madurez RAG3/RAG4 sin
  agente) y Pista A ("ganancias rápidas") de su hoja de ruta.** A
  partir del análisis contra el modelo de madurez RAG1-RAG5 (documento
  "EVOLUCION RAG", verificado factualmente contra fuentes de Azure/AWS/
  NVIDIA), el consultor pidió formalizar la decisión de evolucionar UNA
  sola herramienta -- no bifurcar en "RAG Studio" + "RAG Studio Pro" --
  manteniendo siempre la frontera de que RAG STUDIO nunca ejecuta un
  LLM ni genera lenguaje natural por sí mismo, y proceder de inmediato
  con la parte de esa hoja de ruta de menor riesgo y mayor valor
  inmediato. **ADR-003**
  (`docs proyecto/RAG_STUDIO_ADR-003_Evolucion_Capa_Canonica.docx`/
  `.pdf`): mapea el estado real de RAG STUDIO contra cada nivel
  RAG1-RAG5 con evidencia de código, fija el reparto entre una capa de
  recuperación (puede crecer dentro de RAG STUDIO) y una capa de
  orquestación agéntica (debe quedarse en el agente conversacional
  externo, ver `CONTRATO_INTEGRACION.md`), y deja Pista B (modelo
  canónico de `Chunk`, datos estructurados, ACL real, ruteo
  multi-índice) explícitamente pendiente de su propio documento de
  diseño y de revisión de producto antes de empezar. **Pista A.1 --
  Recall@K:** el Centro de evaluación (Etapa 6) ahora cuantifica, sobre
  los casos de prueba que declaran una fuente esperada, qué fracción la
  trajo entre los primeros `k` resultados -- antes solo se sabía
  "acertó en primer lugar, sí o no", sin registrar si una fuente
  esperada aparecía más abajo. Campos puramente aditivos
  (`EvaluationRun.recall_at_k`), sin cambiar ningún veredicto existente.
  **Pista A.2 -- reranking real:** nuevo puerto `Reranker`
  (`domain/rag/ports.py`) y adaptador local `FastEmbedReranker`
  (`infrastructure/rerankers/fastembed_cross_encoder.py`, cross-encoder
  ligero vía el mismo paquete `fastembed` que ya usa el proveedor de
  embeddings, sin dependencias nuevas ni API de pago), conectado como
  paso opcional después de la fusión RRF de `HybridSearch` -- opt-in
  (`rerank=True`), con la aplicación de escritorio ya construyendo un
  `RagService` con este Reranker real conectado (`app/bootstrap.py`) y
  una casilla nueva en el Laboratorio RAG ("Reranking real"). Sin
  pedirlo explícitamente, el comportamiento no cambia respecto a antes
  de esta ronda. 566 unitarias (+15), 252 de integración (+5, más 2
  omitidas nuevas sin red hacia Hugging Face para el modelo de
  reranking) y 15 de humo en verde, `ruff` sin hallazgos -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 21 (puntos 56-58).
  **Cierre de la ronda:** una auditoría dirigida encontró y corrigió
  tres hallazgos más sobre lo recién implementado (`HybridSearch` ya
  detecta un `Reranker` con conteo de puntajes inconsistente; el
  Laboratorio RAG avisa cuando "Reranking real" se ignora por no estar
  en modo Híbrida; `candidate_limit` subido a 40 como precaución
  explícita del consultor). Además, el consultor compartió un documento
  real (`ingcom.pdf`, un plan de estudios escaneado) para poner a
  prueba con datos reales las partes del canal que no dependen de
  descargar un modelo (OCR, fragmentación, búsqueda BM25 -- embeddings
  y reranking real quedaron fuera: la descarga desde Hugging Face está
  bloqueada en este entorno de verificación). Esa prueba encontró una
  degradación silenciosa real: sin el paquete de idioma español de
  Tesseract instalado, el OCR reconoce en inglés-solamente sin ningún
  aviso (acentos y eñes perdidos) -- ahora `TesseractOcrEngine` lo
  detecta y falla alto y claro con instrucciones. Queda documentado
  como backlog, sin corregir todavía, que Tesseract no segmenta bien
  encabezados en banda de color ni el orden de lectura en documentos de
  cuadrícula multi-columna. 567 unitarias (+1) y 6 de integración de
  OCR (+2) en verde, `ruff` sin hallazgos -- ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 21, puntos 59-63.

- **2026-08-19 -- Ronda 22 (Frente 1): cerrados los dos hallazgos que
  quedaron abiertos al cerrar la Ronda 21, con un corpus real de 14
  documentos.** El consultor compartió una carpeta con 13 planes de
  estudio escaneados adicionales (misma universidad que `ingcom.pdf`,
  2 páginas cada uno) para poder validar con datos genuinos, no
  sintéticos. **Recuperación de encabezados en banda de color:**
  `TesseractOcrEngine` ahora detecta bandas horizontales con fondo de
  color saturado (solo con PIL, sin dependencias nuevas) y las
  reconoce por separado con `--psm 6`, añadiendo el resultado como un
  bloque aparte marcado como de confianza baja -- en `arq.pdf` se
  recuperó limpia toda la fila "1er./2do./3er. Cuatrimestre"; en
  `ingcom.pdf`, varios ordinales más la URL del pie de página. Antes
  de esta ronda esos encabezados no aparecían en ningún lado del texto
  extraído. **`candidate_limit=40`, validado con datos reales:** con
  los 13 documentos nuevos, el corpus real crece a 105 fragmentos en
  13 fuentes -- contando cuántas fuentes distintas aparecen entre los
  primeros resultados de BM25 para "requisitos de ingreso" (una
  sección casi idéntica en las 13), con el valor anterior
  (`candidate_limit=20`) solo 11 de 13 fuentes quedaban representadas
  antes de la fusión RRF; con 40, las 13 quedan representadas -- el
  riesgo que motivó subir el valor en la Ronda 21 era real, no solo
  teórico. Queda documentado con la misma honestidad de siempre que
  esto valida el mecanismo de `candidate_limit`, no la calidad
  semántica real (`FakeEmbeddingProvider`/`FakeReranker`, ya que
  Hugging Face sigue bloqueado en este entorno). 578 pruebas unitarias
  y de integración de OCR en verde (+11 sobre la Ronda 21), `ruff` sin
  hallazgos -- ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 22,
  puntos 64-65.

- **2026-08-19 -- Ronda 23 (Frente 2): documento de diseño de la
  Pista B.1 del ADR-003.** Con el Frente 1 cerrado, el consultor pidió
  continuar con el Frente 2: el documento de diseño que el propio
  ADR-003 exige antes de tocar código de la Pista B.1 (modelo canónico
  de `Chunk`) -- esta ronda **no modifica ningún código de
  producción**, solo entrega el documento
  (`docs proyecto/RAG_STUDIO_Diseno_B1_Modelo_Canonico_Chunk.docx`/
  `.pdf`). Antes de proponer nada se releyó el código real de
  `domain/ingestion`, `infrastructure/database` y
  `application/rag/queries` con cita de archivo:línea, confirmando que
  `Chunk` solo tiene un encadenamiento lineal hoy (sin jerarquía real)
  y que no existe ningún campo `element_type` en el proyecto. El
  documento resuelve y marca para confirmación dos decisiones que el
  ADR-003 deja abiertas: reutilizar `chunk_type` en vez de agregar un
  `element_type` paralelo (evita dos campos que podrían
  desincronizarse), y guardar el futuro "chunk padre" como una fila
  más de `Chunk` pero explícitamente **sin indexarlo** en el
  `VectorStore` (para que no compita por resultados de búsqueda con
  sus propios hijos -- señalado como el riesgo técnico más concreto de
  toda la fase). Propone una única migración Alembic aditiva
  (`parent_chunk_id`, `structured_content`, mismo patrón que la
  migración 0011) y tres sub-fases (B.1a: solo esquema; B.1b:
  jerarquía real solo en `POR_ENCABEZADO`; B.1c: expansión de hijo a
  padre en recuperación, opt-in). Deja cuatro preguntas abiertas
  explícitas para el responsable de producto antes de que la
  implementación pueda empezar. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 23, punto 66.

- **2026-08-19 -- Ronda 24: implementación completa de la Pista B.1
  del ADR-003 (modelo canónico de `Chunk`, B.1a/B.1b/B.1c).** El
  consultor confirmó las 4 preguntas abiertas de la Ronda 23 según las
  recomendaciones del propio documento de diseño e instruyó proceder
  con la implementación. **B.1a:** `ChunkType` gana `ENCABEZADO` y
  `PADRE` (reutilizado, sin `element_type` paralelo); `Chunk` gana
  `parent_chunk_id`/`structured_content` (ambos opcionales, `None` por
  defecto); migración aditiva `0014_chunk_canonical_model.py`, mismo
  patrón que `0011`. **B.1b:** `POR_ENCABEZADO` ahora produce un chunk
  `PADRE` real por cada sección que se sub-dividió en más de un
  fragmento hijo (una sección que cupo en un solo chunk no genera
  padre); el padre se agrega después de la cadena
  `previous_chunk_id`/`next_chunk_id` de lectura lineal, nunca forma
  parte de ella. **B.1c:** `IndexSource` excluye `chunk_type=PADRE`
  del embedding/`VectorStore` -- el riesgo técnico más concreto
  señalado en el documento de diseño, cerrado con una prueba de
  integración dedicada y explícita
  (`test_index_source_never_sends_padre_chunks_to_the_vector_store`);
  por el mismo principio (no pedido explícitamente, pero derivado
  directo de la decisión ya confirmada), se corrigió también
  `TextSearch` para que un chunk padre nunca compita como resultado
  propio en BM25. Además, `expand_to_parent: bool = False` (capacidad
  aditiva) se agregó a `SemanticSearch`/`TextSearch`/`HybridSearch`/
  `RagService` y a una nueva casilla "Expandir a sección completa
  (chunk padre)" en el Laboratorio RAG -- decisión propia sobre un
  detalle que el documento de diseño dejaba pendiente: **adjuntar**,
  no reemplazar, el chunk encontrado (`SemanticSearchResult.chunk`
  sigue siendo siempre el extracto puntual que hizo match; el nuevo
  campo `parent_chunk` lleva el contexto completo aparte, para no
  perder trazabilidad de página/sección). 870 pruebas en verde (0
  fallidas, 12 omitidas por dependencias opcionales no instaladas en
  este entorno), `ruff` sin hallazgos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 24, puntos 67-70.

- **2026-11-17 -- Ronda 104b, Etapa 0 (autorizada por NEXOM): trazabilidad
  y reproducibilidad de cada ejecución, sin cambiar el comportamiento.**
  - **Qué se registra:**
    - identidad del código: versión, commit vía `build_info.json` o `git`, y huella por carpeta (`infrastructure/build_info.py`, `scripts/escribir_build_info.py`);
    - instantánea: versión, huella declarada y calculada al cargar;
    - índice;
    - procedimiento de recuperación (`r102`);
    - reranking efectivo: ajuste, disponibilidad, aplicación y modelo;
    - texto exacto de búsqueda, filtros y fragmentos en orden.
  - **Dónde:**
    - `runtime.db`: `conversation_log.execution` y `chunk_ids`, columnas aditivas;
    - `POST /messages`: campo `execution`, solo con `X-API-Key`;
    - `GET /health`: `code_version` y `retrieval_pipeline`;
    - `GET /health/details`: protegido;
    - Simulador: bloque «Ejecución».
  - **Correcciones:**
    - el Runtime de RAG Studio **no** tiene modelo de reranking y nunca lo aplica, aunque el ajuste de la Ronda 102 diga «Activado»;
    - Manual 8.5 y `Resultados_Ronda102.md` corregidos.
  - **Pruebas:**
    - mismo orden en las 28 consultas de LOTE01 (14 con y 14 sin reranking) antes y después;
    - integración: 572 pasadas;
    - `tests/unit` + smoke sin fallas nuevas.
  - **Detalle y procedimiento E1–E7:** `docs proyecto/Ronda104_Etapa0_Trazabilidad/`.

- **2026-11-10 -- Ronda 102: Simulador vs Búsqueda RAG (requisitos de
  LOTE01_Bachillerato), correcciones C1, C2 y C4 autorizadas por NEXOM.**
  Validado con los cinco archivos reales (`tests/fixtures/lote01_bachillerato`,
  íntegros según el manifiesto). Causa en los datos reales: los documentos
  completos con encabezado YAML tenían «---» como título (afinidad cero) y la
  afinidad título-intención era la clave principal del orden.
  - **C1:** la afinidad se combina por RRF, en partes iguales, con el puesto de
    la búsqueda (`combine_with_retrieval`); ya no entierra el mejor resultado.
  - **C2:** fragmentos sin título de sección usan su primer encabezado
    Markdown (saltando el YAML) o el título de la fuente (`affinity_title`).
  - **C4:** «Reranking en el agente» por proyecto (`Project.agent_reranking`,
    migración de proyecto **0024**; Automático por defecto = comportamiento
    anterior), usado por el Simulador y por `POST /messages` (desde la
    instantánea publicada). El trazado indica si se aplicó y con qué modelo, y
    el puesto en la búsqueda y la afinidad de cada fragmento.
  - **Resultados (14 consultas, final top 5, R@1/MRR):** con reranking
    0.79/0.85 → 1.00/1.00; sin reranking 0.64/0.76 → 0.93/0.95. La consulta
    de NEXOM queda 1.ª con y sin reranking; planes, ordinales e información
    general sin cambios (1.º). Recuperación inicial idéntica antes y después.
  - **Pruebas:** `tests/unit` + smoke 1142 pasadas (2 fallas preexistentes);
    integración 566 pasadas (incluye `test_ronda102_lote01_simulador.py`, que
    falla con el código anterior); `ruff` sin hallazgos nuevos.
  - **Pendientes:** C3, C5, la pérdida en la recuperación inicial al quitar el
    valor filtrado, y la validación en el proyecto LOTE01 de NEXOM. Detalle en
    `docs proyecto/Ronda102_Diagnostico_Simulador/Resultados_Ronda102.md`.

- **2026-11-10 -- Ronda 101: hallazgo en la validación real de la Ronda 100
  (LOTE01_Bachillerato) -- con reranking, "6.º semestre" quedaba sobre el
  "5.º" pedido.** Causa: la fusión RRF entre el orden del cross-encoder y la
  lista jerárquica producía un EMPATE exacto (1.º+2.º = 2.º+1.º) que se
  resolvía con el orden del reranker. Corrección: `ordinal_conflicts`
  (`domain/rag/hierarchy.py`) -- un fragmento cuya RUTA tiene otro ordinal de
  la misma unidad que el pedido explícitamente en la consulta queda después
  de los que no la contradicen -- y desempate por coincidencia jerárquica
  (`_final_key` en `hybrid_search.py`), en la híbrida con y sin reranking.
  Sin ordinal en la consulta o sin ruta, no cambia nada. Trazabilidad:
  `SemanticSearchResult.hierarchy_conflicts` y aviso en el Laboratorio RAG.
  Caso real como prueba de regresión (`test_contexto_jerarquico.py`, falla
  con el código de la Ronda 100) y en el corpus de evaluación (B2/B3).
  Evaluación sintética: híbrida con/sin reranking y con/sin filtro, MRR de
  fragmento 1.00 en los cuatro (antes 0.94-0.97), sin ningún caso que
  empeore. `tests/unit` + smoke 1125 pasadas (2 fallas preexistentes);
  integración 560 pasadas; `ruff` limpio; `mypy` 22. Detalle en
  `docs proyecto/Ronda100_Contexto_Jerarquico/Resultados_Ronda100.md`.
  Pendiente: repetir la validación real con reranking activado.

- **2026-11-10 -- Ronda 100: contexto jerárquico de documentos persistido
  y usado en la recuperación (solicitud NEXOM, AGENTE UDL -
  LOTE01_Bachillerato).** Detalle, resultados y procedimiento de
  actualización en `docs proyecto/Ronda100_Contexto_Jerarquico/
  Resultados_Ronda100.md`.
  - **Fragmentación:** `por_encabezado` guarda en cada fragmento (hijos y
    padre) la ruta de encabezados con su nivel: `Chunk.section_path`
    (`SectionHeading`), migración de proyecto **0023** (`chunk.section_path`
    JSON, nullable, sin backfill). `chunk.text` no cambia; la ruta no se
    mezcla con `parent_chunk_id` ni con los metadatos heredados. Cubre
    niveles omitidos, títulos repetidos y preámbulos sin encabezado.
  - **Recuperación (`domain/rag/hierarchy.py`):** ordinales normalizados
    ("5.º", "5to", "quinto", "semestre 5" -> `semestre_5`, solo con unidad de
    periodo; sin falsos positivos con artículos, apartados o duraciones);
    BM25 sobre texto + encabezados superiores + ordinales; la textual ya no
    devuelve fragmentos solo-encabezado; tercera lista RRF jerárquica en la
    híbrida (mismos candidatos, términos que distinguen, ordinales con
    doble peso, sin contar el título propio); con reranking, el reranker
    recibe "ruta\ntexto" y su orden se fusiona con la lista jerárquica.
    La ruta NO se concatena al texto de los embeddings. Trazabilidad:
    `SemanticSearchResult.hierarchy_terms`, ruta y `[jerarquía: …]` en el
    Laboratorio RAG; `use_hierarchy=False` para comparar. Filtros
    estructurados sin cambios.
  - **Pipeline:** versión de fragmentador `por_encabezado` en la huella de
    política (Ronda 98): tras actualizar se reprocesan SOLO las fuentes
    por_encabezado, con motivo explícito; huella de fragmentos estable para
    fragmentos sin ruta.
  - **GUI:** Detalle del fragmento > Contexto jerárquico distingue ruta
    reconstruida, ruta almacenada (y si coincide) e información usada por
    la búsqueda (señal activa, encabezados agregados, ordinales, texto BM25).
  - **Evaluación (corpus SINTÉTICO, no atribuible a AGENTE UDL; modelos
    reales del proyecto, `evaluacion_recuperacion.py`):** híbrida con filtro
    de campus, MRR de fragmento 0.57 -> 0.96 y R@3 0.57 -> 1.00; con
    reranking 0.55 -> 0.96; sin regresiones caso por caso en la híbrida
    (compartidos, otras estrategias y falso positivo iguales). Regresión
    menor documentada: en la textual pura la fuente correcta baja de 1 a 2
    en tres casos (el fragmento correcto pasa de ausente a posición 4).
    Validación final con los documentos reales: pendiente.
  - **Runtime/instantáneas/NKP:** contrato de la API sin cambios; las
    instantáneas anteriores se migran al abrirse (columna NULL) y buscan
    como antes; hay que publicar una instantánea nueva tras re-fragmentar.
    El NKP v1.0.0 no transporta la ruta: los paquetes publicados no cambian
    (re-exportación del candidato Bachillerato byte a byte idéntica).
  - **Verificación:** 39 pruebas nuevas (30 unitarias de dominio y
    fragmentación, 8 de integración, 1 de interfaz). `tests/unit` + smoke
    1124 pasadas (2 fallas preexistentes); integración 557 pasadas (sin
    `test_fastembed_image_provider.py`); `ruff` limpio; `mypy` en el
    baseline de 22. Manual del Usuario 7.1, 7.3 y 7.4 en DOCX y PDF.

- **2026-11-09 -- Ronda 99: hallazgo real de NEXOM (AGENTE UDL -
  LOTE01_Bachillerato) -- detalle de fragmentos y diagnóstico del contexto
  jerárquico.**
  - **Problema:** Ingesta > Fragmentación solo mostraba número, tokens,
    sección, páginas y tipo; no había forma de leer el texto ni los
    metadatos de un fragmento sin scripts.
  - **Implementación (solo lectura, sin cambios de base de datos):**
    `GetChunkDetail` (`application/ingestion/queries/get_chunk_detail.py`,
    `IngestionService.get_chunk_detail`) reúne, leyendo los repositorios
    existentes, el fragmento guardado, la fuente (posición, nombre, tipo),
    padre/anterior/siguiente, si se indexa (misma regla de `index_source`)
    y los metadatos heredados (multivalor separado + representación
    original). Además, un contexto jerárquico DERIVADO
    (`domain/ingestion/heading_context.py`): la ruta de encabezados del
    texto extraído que rige al fragmento (ubicando los fragmentos en orden,
    para que dos "5.º semestre" iguales no se confundan) y qué encabezados
    superiores no aparecen en el texto indexado; no se guarda ni se usa en
    la búsqueda. Interfaz: botón "Ver detalle del fragmento" y doble clic
    (`ui/ingestion/chunk_detail_dialog.py`), todo en texto plano de solo
    lectura (nada se interpreta como HTML), copiar texto y navegación
    anterior/siguiente/padre.
  - **Análisis (`docs proyecto/Ronda99_Contexto_Jerarquico/`):**
    `por_encabezado` pierde el nivel y los ancestros: cada fragmento
    guarda solo su propio título, y los encabezados de área no se indexan
    (solo encabezado). Los dos "5.º semestre" del caso no llevan su área.
    Medición densa con el modelo del proyecto: anteponer la ruta separa
    mejor las áreas pero empeora el ordinal del semestre. Propuesta, sin
    implementar (requiere autorización): conservar la ruta como dato del
    fragmento (`section_path`, migración y re-fragmentación) y usarla en
    BM25 y en la afinidad de sección con ordinales normalizados; para
    planes de estudio, datos estructurados por tabla.
  - **Verificación:** 12 pruebas nuevas (integración real: texto exacto,
    saltos de línea y caracteres especiales, relaciones padre/anterior/
    siguiente, metadatos multivalor, rutas distintas para los dos "5.º
    semestre", sin escrituras ni reindexación y pipeline de la Ronda 98
    omitiendo la fuente después; interfaz Qt: doble clic, texto literal,
    copiar, navegación). `tests/unit` + smoke 1093 pasadas (las 2 fallas
    preexistentes de `test_metadata_conversational_field_refresh.py`);
    integración 549 pasadas (sin `test_fastembed_image_provider.py`);
    `ruff` limpio; `mypy` en el baseline de 22. Manual del Usuario 7.3 en
    DOCX y PDF.

- **2026-11-09 -- Ronda 98: hallazgo real de NEXOM (AGENTE UDL -
  LOTE01_Bachillerato) -- políticas por fuente en el pipeline e
  incrementalidad por configuración.**
  - **Problema (confirmado en el código):** la pestaña Pipeline enviaba un
    único `document_type_code`; `RunPipeline` lo pasaba igual a todas las
    fuentes y `FragmentSource` resolvía la política con ese valor, sin
    mirar el tipo de cada fuente. Un lote con `programa_academico`
    (por_encabezado), `informacion_academica` e `informacion_admisiones`
    (documento_completo) se fragmentaba entero con una sola política. Y la
    incrementalidad solo comparaba el hash del archivo: cambiar la
    política o un metadato heredado no reprocesaba nada.
  - **Política por fuente (`application/pipeline/commands/run_pipeline.py`):**
    cada fuente usa la política de SU `document_type_code`; la "default"
    del proyecto solo si su tipo no tiene política; si no hay ninguna, los
    parámetros internos. `FragmentSource.resolve_policy` (pública) es el
    punto único de esa regla. Un `document_type_code` explícito sigue
    forzando una política para todo el lote (queda marcado "forzada").
  - **Incrementalidad:** una fuente se omite solo si coinciden con su
    última corrida exitosa el archivo (`content_hash`), la política
    aplicable (`policy_hash`), los metadatos que heredan los fragmentos
    (`metadata_hash`) y los fragmentos guardados (`chunks_digest`, detecta
    re-fragmentaciones a mano), y si su último intento no quedó fallido o
    cancelado (antes, un fallo después de re-fragmentar y antes de indexar
    podía quedar oculto). Cada item registra tipo, política aplicada
    (origen y estrategia) y `reason`. Las corridas anteriores no tienen
    huellas: la primera corrida tras actualizar reprocesa una vez, con ese
    motivo explícito.
  - **Hallazgo adicional:** el hash se calculaba sobre `location` (ruta
    externa) aunque la extracción lee la copia en `sources/original/`. Un
    proyecto llevado a otro equipo (ruta externa inexistente) reprocesaba
    TODAS sus fuentes en cada corrida, y un cambio en el archivo externo
    "reprocesaba" sin efecto. Ahora se usa el mismo archivo que se extrae.
  - **Persistencia:** migración de proyecto **0022** (columnas nullable en
    `pipeline_run_item`; sin backfill). Las pruebas de 0021 que fijaban
    `"0021"` como versión final ahora comparan contra el head.
  - **Interfaz (`ui/ingestion/panel.py`):** se quita el selector global
    `document_type_code` de Pipeline; nota explicativa, botón "Revisar
    políticas por fuente (sin procesar)" (`PipelineService.plan`, sin
    efectos) y reporte con tipo, política, origen y motivo por fuente. En
    Fragmentación, el selector propone el tipo de la fuente activa.
  - **Verificación:** 15 pruebas nuevas: escenario LOTE01 de 5 fuentes / 3
    tipos sobre SQLite y Qdrant reales (estrategias distintas en una corrida,
    cantidad y contenido de fragmentos, `campus = hilario_medina|torres_landa`
    heredado, los 5 casos de regresión de incrementalidad, re-fragmentación
    manual, vista previa y búsqueda filtrada por cada plantel), casos borde
    con dobles y la interfaz Qt. Con el código anterior fallan 4 de las 5
    de integración (entre ellas, la política modificada quedaba OMITIDA).
    `tests/unit` + smoke 1088 pasadas (las 2 fallas preexistentes de
    `test_metadata_conversational_field_refresh.py`); integración 542
    pasadas (sin `test_fastembed_image_provider.py`); `ruff` limpio;
    `mypy` en el baseline de 22. Manual del Usuario 7.1 y 7.3 en DOCX y PDF.

- **2026-11-09 -- Ronda 97: hallazgo real de NEXOM (AGENTE UDL, prioridad
  alta) -- selección múltiple de catálogo en "Valores por fuente".**
  - **Problema:** con un campo `seleccion_multiple` con catálogo y
    "Permite varios valores" (p. ej. `campus` con `hilario_medina` y
    `torres_landa`), el selector de "Valores por fuente" solo dejaba
    elegir UNA entrada; guardar la segunda sustituía a la primera. La
    capa de aplicación ya aceptaba listas (guardadas como `a|b`), y la
    herencia a fragmentos, el filtro de recuperación (Ronda 89) y el
    exportador NKP ya leían varios valores: el defecto estaba en la
    interfaz y en que no había forma de agregar ni de quitar un valor suelto.
  - **Interfaz (`ui/metadata/panel.py`):** para campos de varios valores
    con catálogo, lista con casillas que muestra marcadas las entradas que
    la fuente ya tiene; "Guardar valor" guarda exactamente las marcadas
    (desmarcar una la quita) y no permite guardar sin ninguna marcada
    (para dejar el campo vacío se usa "Quitar valor"). "Valores actuales"
    muestra una fila por valor, con su etiqueta de catálogo, y "Quitar
    valor" sobre una de esas filas quita solo ese valor. "Aplicar a varias
    fuentes…" usa las casillas marcadas y, con la nueva casilla "agregar a
    los valores que cada fuente ya tiene" (activada por defecto), suma los
    valores sin borrar los existentes; desactivada, reemplaza. Un campo de
    tipo `seleccion_multiple` sin "Permite varios valores" muestra un aviso.
    Los campos de un solo valor conservan el selector de siempre.
  - **Aplicación:** `set_source_metadata_value` y
    `bulk_set_source_metadata_value` aceptan `mode="agregar"` (solo campos
    de varios valores) además de `"reemplazar"` (por defecto, sin cambio de
    comportamiento). Nuevo `remove_source_metadata_value_item`
    (`RemoveSourceMetadataValueItem`): quita un valor y conserva los demás;
    si era el último, el campo queda sin asignar; todo queda en el
    historial. En campos de varios valores cada valor se valida por
    separado contra el catálogo; se rechazan valores vacíos o que
    contengan `|` y se eliminan repetidos. `split_stored_values` y
    `join_values` (`domain/metadata/entities.py`) son el punto único de
    la serialización para el código nuevo.
  - **Herencia, filtros y NKP (verificados, sin cambios):** los fragmentos
    heredan `"hilario_medina|torres_landa"` y el índice lo lleva en
    `meta__campus`; el filtro de recuperación reconoce el documento con
    cualquiera de sus valores y no mezcla los de otras fuentes; el NKP
    exporta `source_metadata.value` como lista. En el NKP, el
    `inherited_metadata` de los chunks sigue siendo texto `a|b` (el
    contrato v1.0.0 lo define como cadena).
  - **Verificación:** 33 pruebas nuevas (aplicación, interfaz Qt real,
    integración con SQLite real: persistencia al cerrar y volver a abrir,
    herencia e índice; recuperación filtrada con cada valor). Con el código
    anterior fallan las de interfaz y la de persistencia/agregar.
    `tests/unit` 1061 pasadas; las 2 fallas de
    `test_metadata_conversational_field_refresh.py` son preexistentes (se
    reproducen igual sobre `HEAD`); integración 537 pasadas (sin contar
    `test_fastembed_image_provider.py`, que descarga un modelo); `ruff`
    limpio; `mypy` en el baseline de 22. Manual del Usuario (6.1 y 6.4)
    actualizado en DOCX y PDF.

- **2026-10-08 -- Ronda 96: auditoría de cierre de la Ronda 95
  (identidad de package).** Se revisó, punto por punto, contra los dos
  documentos del hallazgo y contra un paquete exportado real:
  - Cumplido: `deployment_package_id` separado; `package_id` conservado
    sin cambiar su comportamiento; identidad lógica (`project_id` hoy,
    `knowledge_base_id` reservado para RAG-INC-01) en el bloque
    `identity` de manifest.json; contrato sección 1bis; validaciones de
    project_id, versión, identidad de instantánea y huellas sin cambios.
  - Corregido: (1) la regla "misma versión con otra huella es
    inconsistencia" podía producir rechazos falsos al comparar con
    manifiestos anteriores a la Ronda 95 de instantáneas antiguas, cuya
    huella se calculaba en cada exportación. Ahora el contrato indica
    tratar ese caso como advertencia para el operador y usar
    `snapshot_id` entre manifiestos v2; (2) INFORME_ENTREGA.md no
    mencionaba manifest.json ni la diferencia entre identidad del
    conocimiento e identidad de la exportación; (3) el contrato incluye
    un ejemplo con dos exportaciones (v2 y v4) del mismo proyecto.
  - Fuera del alcance de RAG STUDIO (para NEXOM Testing Agent): asociar
    por `project_id` más el package lógico confirmado por el operador y
    guardar `deployment_package_id` como auditoría.
  - 925 unitarias y 15 smoke en verde; las pruebas de paquete, identidad
    e instantánea en verde; ruff limpio; mypy en línea base.

- **2026-10-08 -- Ronda 95: aclaración del contrato de integración --
  identidad de `package_id` (validación real AGENTE UDL / LIC_DAE con
  NEXOM Testing Agent).**
  - **Hallazgo (no es un error de RAG STUDIO):** `package_id` del
    manifest.json es `DeploymentPackage.id`, un UUID nuevo en cada
    exportación (deliberado: el paquete de entrega no se persiste). El
    Testing Agent lo tomaba como identidad lógica y, al registrar la
    exportación de v4, pedía crear un package nuevo en lugar de agregar
    una versión. El contrato no explicaba qué significaba cada
    identificador.
  - **Decisión (NEXOM: "aclarar contrato sin migración"):** se conserva
    `DeploymentPackage.id` por exportación y se separan las identidades.
    La identidad lógica portable definitiva es `knowledge_base_id` del
    contrato NEXOM Knowledge Package v1.0.0, que llegará con RAG-INC-01
    (migración 0021, que sigue bloqueada). Hasta entonces la clave de
    agrupación es `project_id`. No se inventa un tercer identificador que
    después habría que migrar.
  - **manifest.json v2 (aditivo):** `manifest_version: 2`,
    `deployment_package_id` (= `package_id`, que se conserva) y el bloque
    `identity` {project_id, project_name, snapshot_version, snapshot_id,
    content_fingerprint, deployment_package_id, knowledge_base_id: null,
    grouping_key: "project_id", source_batches}. `DeploymentPackage`
    agrega `snapshot_id`.
  - **CONTRATO_INTEGRACION.md, sección 1bis:** una tabla con qué
    identifica cada campo y si cambia entre exportaciones, y las reglas
    para un consumidor:
    - agrupar versiones por `project_id` y ordenarlas por `snapshot_version`;
    - nunca usar `package_id`/`deployment_package_id` como clave lógica;
    - un package lógico propio (p. ej. LIC_DAE) se asocia por `project_id`
      más la confirmación del operador, y guarda `deployment_package_id`
      como auditoría;
    - mismo project_id + versión + huella es la misma versión
      (idempotente); misma versión con otra huella es una inconsistencia
      que se rechaza;
    - para paquetes anteriores, `project_id` + `snapshot_version` de
      nivel superior.
    
    La sección 2 de GUIA_DESPLIEGUE.md lo resume.
  - **Auditoría:** una instantánea anterior a la Ronda 92 (sin
    `snapshot_identity.json`) recalculaba su huella en cada exportación y
    podía dar huellas distintas para la misma versión si el índice local
    reescribía un archivo. Ahora se identifica una vez y la identidad
    queda junto a la instantánea (si la carpeta es de solo lectura, se
    sigue calculando como antes).
  - Pruebas nuevas: `test_deployment_package_identity.py` (5). 925
    unitarias, 423 de integración y 15 smoke en verde; ruff limpio; mypy
    en línea base (22).
  - **Compatibilidad:** sin cambios de datos (project.db, runtime.db,
    índices). Todas las claves anteriores del manifest se conservan con
    el mismo significado. Los paquetes ya exportados siguen siendo
    válidos; solo no traen `identity`.

- **2026-10-08 -- Ronda 94: inconsistencia de contrato en el paquete
  de despliegue (hallazgo de validación real, paquete LIC_DAE, v4).**
  - **Hallazgo:** el runtime ya funcionaba sin `RAGSTUDIO_SNAPSHOT_VERSION`
    (check_config LISTO, `/health` con `snapshot_version: 4` tomada de
    `snapshot_identity.json`), pero `.env.example` la listaba como
    OBLIGATORIA y la generaba activa, igual que la guía y el Manual
    (10.5). La Ronda 92 había implementado la versión como derivada pero
    la documentó como obligatoria "de verificación": el runtime estaba
    bien y la documentación no.
  - **Corrección:** `RAGSTUDIO_SNAPSHOT_VERSION` es opcional en todo el
    paquete: en la tabla única de variables (`_env_vars_doc`), en
    `.env.example` (comentada, con la versión del paquete como valor de
    referencia), en GUIA_DESPLIEGUE.md sección 3 (obligatorias:
    `RAGSTUDIO_SNAPSHOT_DIR` y `RAGSTUDIO_API_KEY`), en los ejemplos de
    bash/PowerShell, en docker-compose (ya no la exige), en el Dockerfile,
    en la unidad systemd, en packaging/api/README.md y en el Manual. La
    línea `# OBLIGATORIAS` de `.env.example` ahora se genera desde la
    misma tabla, así que no puede volver a desalinearse. El runtime no
    cambió.
  - **Auditoría de contrato -- otras diferencias corregidas:** (1) el
    ejemplo de respuesta de CONTRATO_INTEGRACION.md no mostraba
    `trace_id` (Ronda 93); (2) la sección 5bis no aclaraba que 401, 422 y
    429 conservan el formato `{"detail": ...}` sin objeto `error`; (3) la
    sección 12 de la guía no documentaba `failed_turns`/`failure_rate` ni
    que `abstention_rate` excluye los turnos fallidos.
  - **Pruebas nuevas:** el `.env.example` generado, tal cual y sin
    versión, pasa check_config y arranca con `/health` en la versión de la
    instantánea; las variables marcadas como obligatorias en
    `.env.example` y en la guía son exactamente las que exige el runtime
    (quitar una impide arrancar, quitar una opcional no); una versión
    definida que no coincide se rechaza con un mensaje claro; 401, 422 y
    429 sin objeto `error`. 925 unitarias, 418 de integración y 15 smoke
    en verde; ruff limpio; mypy en línea base (22).
  - **Compatibilidad:** sin cambios de datos ni de comportamiento del
    runtime. Los `.env` que ya definen la versión correcta siguen siendo
    válidos. Los paquetes de entrega ya exportados funcionan igual; solo
    su `.env.example` y su guía contienen el texto anterior. Para
    corregirlos, vuelve a exportar el paquete o simplemente omite la
    variable.

- **2026-10-06 -- Ronda 93: SOLICITUD COMPLEMENTARIA NEXOM -- caso
  `failed` con "Categoría de error = —" y Trace ID presente.**
  - **Origen de la pantalla:** la tabla de la captura (Case ID /
    Resultado answered-abstained-failed / Categoría de error / Trace ID /
    Duración) no existe en RAG STUDIO; es la vista del consumidor
    (NEXOM Testing Agent) que llama a `POST /projects/{id}/messages`.
  - **Causa raíz del lado de RAG STUDIO (reproducida):** si el motor
    lanzaba una excepción, la API respondía `500 Internal Server Error`
    en texto plano -- sin categoría, etapa, código ni trace -- y el turno
    NO se guardaba en runtime.db (solo los exitosos). La categoría nunca
    se generaba (caso 3 de la solicitud) y no había nada que el
    consumidor pudiera persistir ni correlacionar.
  - **Corrección:** taxonomía `domain/runtime/failures.py` (categoría,
    etapa, código, resumen, detalle técnico); clasificación determinista
    por tipo de excepción y cadena de llamadas real
    (`application/runtime/failure_diagnosis.py`); el turno fallido se
    guarda en runtime.db (acción `fallo`, columnas nuevas agregadas en
    caliente, sin migración Alembic); la API responde JSON
    `{detail, error:{category, stage, code, message, trace_id, log_id,
    snapshot_version, exception_type, timestamp, retryable}}` (500
    motor, 503 carga de instantánea, 404 instantánea inexistente);
    `X-Trace-Id` del consumidor se respeta, se devuelve (encabezado y
    cuerpo, también en respuestas exitosas) y aparece en
    ragstudio-api.log junto con la traza completa. Monitoreo muestra la
    categoría y etapa en la fila, el detalle técnico en "Ver
    conversación" y el conteo/tasa de fallos; filtro "fallo".
    `/metrics`: `failed_turns`, `failure_rate`; los fallos no cuentan en
    abstención ni latencias. CONTRATO_INTEGRACION.md, sección 5bis.
  - **Auditoría -- mismo defecto en otros puntos, corregido:** (1)
    Calidad (pestaña interna): un caso cuya simulación lanzaba una
    excepción sin mensaje quedaba gris SIN causa y sin rastro en el
    registro -- ahora guarda categoría/etapa/código/detalle (columna de
    texto existente); corridas viejas grises sin causa muestran un aviso
    explícito; (2) Pipeline: filas FALLIDO con error vacío -- ahora tipo
    + mensaje + último paso, con traza en el log; (3) trabajos en
    segundo plano: error vacío y sin log -- corregido; (4) 15 diálogos
    "Error" de la interfaz mostraban texto vacío ante excepciones sin
    mensaje -- `ui/errors.py::describe_error` + traza en ragstudio.log;
    (5) CORS no exponía/aceptaba `X-Trace-Id`.
  - Pruebas nuevas: `test_failure_diagnosis.py` (13) y
    `test_runtime_failed_case_diagnosis.py` (8, reproducción real con
    API/Qdrant/SQLite). 925 unitarias, 414 de integración y 15 smoke en
    verde; ruff limpio; mypy en línea base (22).
  - **Compatibilidad:** proyectos, .agentproj, instantáneas, índices y
    paquetes de RAG CONTENT sin cambios ni regeneración; runtime.db se
    actualiza solo al abrirse (columnas nulas para filas viejas).

- **2026-10-06 -- Ronda 92: hallazgo real de usuario al desplegar un
  paquete de entrega (instantánea v2) + SOLICITUD NEXOM "portabilidad,
  identidad y preparación multi-lote".**
  - **Causa confirmada (runtime):** `RAGSTUDIO_SNAPSHOT_VERSION` tenía
    valor por defecto 1 (`interfaces/api/app.py`) y la carpeta
    `instantanea/` no decía qué versión era. Con un paquete v2 sin la
    variable, el runtime se identificaba como `p:1` y el consumidor
    posterior lo rechazaba (error de identidad de recuperación).
    Corrección: nuevo `instantanea/snapshot_identity.json` (proyecto,
    versión, modelo de embeddings, huella de contenido portable y lotes
    de origen), escrito al publicar y agregado por el empaquetador a
    instantáneas anteriores; la versión se deriva de ahí (o del
    `manifest.json` del paquete). Sin valor por defecto: si la variable
    se define debe coincidir; si no se puede derivar y no se define, el
    proceso no arranca.
  - **Validación previa** (`interfaces/api/runtime_config.py`, usada por
    `create_app_from_env` y por el nuevo
    `python -m interfaces.api.check_config [--verificar-huella]`):
    carpeta existente, `instantanea/` y no la raíz del paquete,
    `project.db` válido con un solo proyecto, versión coincidente,
    perfil de embeddings coherente con el modelo del índice (se deriva
    si no se define), clave definida, valores numéricos válidos. Todos
    los problemas se reportan juntos. Registro sin `RAGSTUDIO_HOME`
    explícito ni instantánea: ya no arranca contra la instalación por
    defecto en silencio.
  - **Nombres unificados:** oficial `RAGSTUDIO_API_KEY`; `RAG_API_KEY`
    solo como alias heredado, con aviso (y error si ambos difieren).
    `.env.example` del paquete trae `RAGSTUDIO_SNAPSHOT_VERSION=<N>` y
    las tres obligatorias marcadas.
  - **Guía de despliegue:** nueva sección 0 (carpeta del código vs.
    carpeta del paquete; el venv es del proyecto RAG STUDIO; `uvicorn`
    desde la carpeta del código o con `--app-dir`), variables mínimas
    para bash y PowerShell, `check_config` antes de arrancar y
    respuesta esperada de `/health` (ahora con `snapshot_mode`,
    `snapshot_project_id`, `snapshot_version`, `embedding_profile`).
    Docker/compose/systemd actualizados (`ExecStartPre=check_config`).
  - **Auditoría -- defectos adicionales corregidos:** (1) la instantánea
    fija respondía a cualquier `project_id` de la URL con el contenido
    de otro proyecto: ahora 404 explícito; (2) `Source.original_copy_path`
    guardaba la ruta absoluta del equipo de origen: tras mover el
    proyecto (.agentproj) a otro equipo la re-extracción fallaba aunque
    la copia viajó -- el repositorio ahora resuelve la copia dentro de
    la carpeta actual del proyecto (reproducido y cubierto por prueba);
    (3) importación de carpetas de RAG CONTENT: nombres en NFD (macOS)
    o con otra capitalización ya no dan "no se encontró" (el hash sigue
    verificando el contenido), manifiesto con ";" (Excel en español)
    se lee bien y uno no UTF-8 da un error claro; (4) la guía decía que
    `runtime.db`/logs quedaban junto a la instantánea: quedan en
    `RAGSTUDIO_HOME`.
  - **Multi-lote:** cada importación de carpeta registra su lote en
    `projects/<id>/lotes_importados.jsonl` (append-only, viaja en el
    .agentproj y en la instantánea): huella portable (pares
    nombre/hash ordenados, sin rutas, equipo ni fecha), etiqueta,
    relación con lotes previos (lote nuevo, reimportación idéntica,
    versión nueva, comparte documentos) y fuente registrada por fila.
    Una versión nueva NO retira las fuentes anteriores (decisión del
    usuario con "Sustituye a"). Sin migración nueva de base de datos.
  - Pruebas nuevas: `test_runtime_snapshot_identity.py` (19),
    `test_import_batches_multilote.py` (11, checklist 07 pruebas 1-6),
    `test_project_portability_original_copy.py` (1). 912 unitarias, 406
    de integración y 15 smoke en verde; `ruff` limpio; `mypy` en la
    línea base (22).

- **2026-10-05 -- Ronda 91: hallazgo real de usuario (paquete
  `PROY_RAG_20261005.agentproj`) -- clasificación inconsistente ante
  variantes de una consulta y apartado equivocado con la intención
  correcta.**
  - **Problema 1, causa confirmada:** al reconocer la intención se
    quitaban solo los valores de catálogo de campos ligados a variables
    (programa), no los de otros campos con catálogo (nivel académico
    "Licenciatura"), mientras que la búsqueda de fragmentos sí los
    quitaba. Con "...termina la licenciatura en Derecho" quedaba
    "...termina la licenciatura en ?", más parecido a "Cuéntame sobre la
    licenciatura en Psicología" (Consultar programa específico) y al
    negativo "¿Qué licenciaturas ofrecen?" de perfil (0.778 > 0.751:
    margen semántico negativo, quedaba el léxico 0.182). Corrección:
    `_catalog_mention_masker` usa todos los campos con catálogo y
    `remove_spans` quita los conectores que quedan pegados al hueco ("la
    ... en"). Además la intención se elige con `_net_score`: el negativo
    solo resta cuando supera al mejor positivo (695 consultas reales,
    incluidas paráfrasis que no están en los ejemplos: 570 -> 595; la
    medición de la Ronda 89 que la descartó estaba distorsionada por el
    enmascarado asimétrico corregido en la Ronda 90).
  - **Problema 2, causa confirmada:** con filtro e intención correctos,
    el orden final lo daba el reranker `ms-marco-MiniLM-L-6-v2`
    (entrenado en inglés): puntajes casi iguales (-9.2, -10.2, -10.7,
    -10.8) y "Casos que requieren handoff" primero. Corrección general
    (`domain/conversational/section_affinity.py`): con filtro aplicado se
    recupera un conjunto más amplio de la fuente y se ponen primero las
    secciones cuyo título comparte raíces con el nombre, descripción y
    ejemplos de la intención (las raíces comunes a muchas intenciones
    pesan menos); el orden de la búsqueda desempata. Sin listas fijas.
    Los fragmentos de control editorial siguen indexados y quedan
    después del contenido; suben solo si una intención habla de ellos.
  - **Resultados (251 de 270 consultas planeadas -- 25 licenciaturas x
    10 formas + 10 diplomados x 2 --, sin datos ni fuente manuales; 9 de
    las 12 formas no están entre los ejemplos de las intenciones):** intención correcta 251/251; sección esperada
    primero antes 36/251 -> ahora 187/251, entre las 3 primeras 92 ->
    246. Por intención: perfil 21 -> 95/95, campo de trabajo 3 -> 46/46,
    plan de estudios 5 -> 35/45 (top-3 40/45), programa específico 7 ->
    11/65 (top-3 11 -> 65/65: "Modalidad"/"Duración", mencionadas en la
    descripción de la intención, quedan antes que "Descripción
    general"). Aceptación A-D: perfil de egreso, programa detectado, 34
    fuentes descartadas, responder y "Perfil del egresado" primero en las
    cuatro. Contradicción de control: Contradicción entre fuentes,
    regla activada, paquete `canal_contradiccion_fuentes`. Banco de
    Calidad (10 casos, sin cambiar expectativas ni umbral): 10/10 verde,
    TEST-REG-UDL-001 incluido; fuente esperada en posición 1 en los 6
    casos con fuente.
  - **Auditoría de rendimiento:** una simulación tardaba ~11 s en este
    proyecto: `ensure_project_db` recompilaba los scripts de Alembic 115
    veces (3.5 s) y los ~100 textos de referencia de intenciones se
    vectorizaban en cada consulta (2.2 s). Ahora la revisión head se
    guarda en memoria con la firma de la carpeta de migraciones (se
    sigue detectando una migración nueva) y los vectores de referencia
    por texto: ~2 s por simulación (el resto es el reranker).
  - **Actualización:** no requiere reindexar ni migrar datos; el
    `.agentproj` del usuario se importa completo (incluye índice, 618
    vectores). Verificación: `tests/unit` 901 pasadas (7 nuevas),
    integración relacionada 61/61, `ruff` limpio, `mypy` baseline 22.
    Manual del Usuario (8.2, 8.5) en DOCX y PDF.

- **2026-10-05 -- Ronda 90: hallazgo real de usuario -- "¿Cuál es el
  perfil de egreso de la licenciatura en Derecho?" (ejemplo positivo de
  "Consultar perfil de egreso", prioridad 50) se reconocía como
  "Consultar programa específico" (prioridad 40, confianza 0.633).**
  - **Causa (reproducida con el paquete del usuario del 2026-10-05):**
    regresión introducida en la Ronda 89. Para reconocer la intención se
    quitaban las menciones de programas SOLO de la consulta; los ejemplos
    seguían con el nombre. La consulta dejaba de coincidir con su propio
    ejemplo (1.000 -> 0.801) y su negativo "¿Cuál es el plan de estudios
    de Mercadotecnia?" pasaba a 0.712: margen 0.089 contra 0.143 de
    "Consultar programa específico". La prioridad no intervenía: el
    código nunca la usaba, aunque el Manual decía que sí.
  - **Corrección:** `match_intent(..., text_transform=...)` aplica la
    misma transformación a la consulta y a nombre, descripción y ejemplos
    positivos/negativos de todas las intenciones;
    `SimulateConversation._catalog_mention_masker` la construye con los
    catálogos del proyecto. Ahora: perfil 0.288 (1.000 - 0.712) contra
    programa específico 0.150; confianza 1.0; se conserva
    `programa_academico=derecho` y "Perfil del egresado" como primer
    fragmento. A igual margen gana la mayor prioridad (documentado como
    desempate). Nuevo `IntentScore`/`SimulationTrace.intent_scores`: el
    Simulador muestra la puntuación de las 3 mejores intenciones.
  - **Validación con el proyecto real:** 245 consultas (35 programas x 7
    formas: perfil de egreso x2, plan de estudios x2, información general
    x2, campo de trabajo): Ronda 89 175/245, sin quitar menciones 152/245,
    ahora 245/245. Recuperación (25 licenciaturas x perfil y plan de
    estudios + 10 diplomados x objetivo, sin variables escritas a mano):
    intención 60/60, programa detectado 60/60, sección esperada en top-3
    60/60 y en top-1 39/60.
  - **Auditoría:** "Consultar programa específico" declara como datos
    opcionales `modalidad` y `nivel_academico`, que no existen como
    variables: se ignoraban en silencio. La interfaz ahora avisa al
    guardar una intención con códigos de variable inexistentes. Se
    confirmó que los datos señalados en la Ronda 89 (programa mal
    asignado, "Liceniatura", "Escolariza") ya fueron corregidos en el
    proyecto; las secciones internas ("Uso permitido por el agente",
    etc.) siguen indexándose y aparecen como segundo fragmento.
  - **Verificación:** `tests/unit` 894 pasadas (6 omitidas; 3 nuevas),
    integración relacionada 51/51; `ruff` limpio; `mypy` en el baseline
    de 22. Manual del Usuario (8.1, 8.2, 8.5) en DOCX y PDF.

- **2026-10-04 -- Ronda 89: hallazgos reales de usuario en Metadatos y
  en el Simulador de AGENTE UDL (paquete real importado y reproducido).**
  - **Catálogo -> Valores por fuente:** una entrada nueva no aparecía en
    el selector de "Valores por fuente" hasta reiniciar: las opciones solo
    se cargaban al CAMBIAR de campo. Ahora se recargan (conservando la
    selección) al agregar/editar/eliminar entradas y al entrar a la
    sub-pestaña (`ui/metadata/panel.py`, `_reload_value_catalog_options`).
  - **Variable "faltante" aunque la consulta nombraba el programa:** no
    existía ninguna detección de valores en el texto. Nuevo
    `domain/conversational/variable_extraction.py` (puro): busca las
    etiquetas y códigos del catálogo del campo ligado -- o los valores ya
    capturados si no hay catálogo -- como palabras completas, sin
    acentos/mayúsculas; gana la mención más larga; un empate deja la
    variable ambigua y se pide aclaración. Nada fijo en el código.
  - **Filtro aplicado después del top-k:** `SimulateConversation`
    descartaba resultados de otras fuentes DESPUÉS de tomar los 5 mejores
    del proyecto (con la pregunta completa quedaban 2: identificación y
    título). Ahora calcula primero las fuentes que cumplen los filtros y
    busca solo en ellas (`source_ids` en `SemanticSearch`, `TextSearch`,
    `HybridSearch`, `RagService.search_hybrid`). Además: campos de valor
    múltiple ("a|b") coinciden con cualquiera de sus valores; el texto
    usado para ordenar fragmentos quita las menciones de los valores
    filtrados y de los valores de metadatos que comparten todas las
    fuentes permitidas; si ninguna fuente tiene el valor, la abstención
    lo explica.
  - **Reconocimiento de intención y confianza:** medido con el proyecto
    real (177 consultas, 35 programas): las menciones del programa
    añadían ruido; ignorarlas para reconocer la intención subió el
    acierto de 102/177 a 142/177 (las 35 fallas restantes son una sola
    forma de preguntar, "¿En qué puede trabajar un egresado de...?", que
    falta como ejemplo en la intención de campo de trabajo). Se probó
    cambiar la fórmula "positivo menos negativo" y empeoraba la elección
    (79/177), así que se conserva para ELEGIR; lo que cambia es la
    confianza REPORTADA: similitud con el mejor ejemplo positivo, en
    lugar del margen (una consulta idéntica a un ejemplo aparecía con
    0.573 y una correcta con ~0.03, que la regla "confianza < 0.10 ->
    abstenerse" del proyecto descartaba). Las reglas con umbral de
    confianza deben revisarse (Manual, 8.3.1).
  - **Resultados en AGENTE UDL (35 programas, una pregunta por programa,
    sin indicar la variable):** antes 0/35 respondidas (24 pedían
    aclarar y 11 se abstenían); con la variable escrita a mano,
    24/35 respondidas, top-1 0/35, top-3 2/35. Ahora 35/35 respondidas,
    35/35 con el programa detectado, sección esperada en el top-3 35/35
    y en el top-1 22/35. Los casos del reporte: la pregunta completa
    detecta el programa, filtra y devuelve "Objetivo" primero; "Dame
    información de Gestión Profesional de Proyectos" ya no pide el
    programa. El reranker actual (ms-marco, en inglés) se mantiene: sin
    él el top-1 baja a 5/35.
  - **Hallazgos de datos (no de código) informados al usuario:**
    `licenciatura_ingenieria_industrial_administrativa.md` tiene
    `programa_academico = ingenieria_electromecanica_industrial`; las
    entradas "Liceniatura" y "Escolariza" tienen errores de captura; las
    secciones internas de los documentos ("Uso permitido por el agente",
    "Nota de control para chunking", etc.) se indexan y compiten con el
    contenido.
  - **Verificación:** `tests/unit` 891 pasadas (6 omitidas) con 15
    pruebas nuevas (`test_variable_extraction.py`,
    `test_simulate_conversation_variables.py`, `test_intent_matching.py`);
    integración relacionada 82/82 (RAG de extremo a extremo,
    canalización, monitoreo, API de runtime, widget, metadatos, paquete
    de despliegue, Qdrant). `ruff` limpio; `mypy` en el baseline de 22.
    El runtime HTTP usa el mismo motor (se le pasan los mismos
    repositorios). Interfaz verificada con `py_compile` (sin `libEGL`
    aquí). Manual del Usuario (6.4, 8.2, 8.3.1, 8.5) en DOCX y PDF.

- **2026-10-02 -- Ronda 88: hallazgo real de usuario -- importar un
  proyecto falla con "UNIQUE constraint failed: project_index.name" y,
  al reintentar, "Ya existe un proyecto real con id=...".**
  - **Causa raíz (reproducida con SQLite y disco reales):** el paquete
    "AGENTE UDL" se importó en una instalación que ya tenía otro
    proyecto con ese nombre. `FilesystemProjectPackager.import_project`
    copiaba todos los archivos a `projects/<id>/` y solo al final
    `ProjectRepository.save` chocaba con la restricción de nombre único
    del índice global. La copia no se deshacía: quedaba una carpeta sin
    registrar, y el reintento caía en `ProjectIdCollisionError`, cuyo
    mensaje pedía "indicar un id nuevo (new_project_id)", algo que la
    interfaz no permitía.
  - **Corrección:** `ImportProject` comprueba todo antes de copiar:
    id de un proyecto registrado (`ProjectIdCollisionError`, ahora se
    ofrece importar como copia con id nuevo), restos sin registrar de
    un intento fallido (`ImportResidueError`, se ofrece apartarlos a
    `<instalación>/residuos_importacion/`: se mueven, no se borran) y
    nombre repetido (`ImportNameCollisionError`, se pide otro nombre con
    una sugerencia "<nombre> (importado)"). El adaptador extrae a una
    carpeta temporal y renombra al final (todo o nada), y si el registro
    final falla se borra lo recién copiado. La interfaz ofrece cada salida
    en un diálogo y confirma con "Proyecto importado".
  - **Defecto latente encontrado al probar "importar como copia":**
    `new_project_id` solo cambiaba la fila `project`; las otras 19
    tablas con `project_id` (fuentes, fragmentos, intenciones, reglas,
    casos de prueba, etc.) conservaban el id viejo, y como los
    repositorios filtran por `project_id`, la copia aparecía vacía.
    Ahora se reescribe en todas.
  - **Auditoría de la pestaña Proyectos y del mismo patrón en el resto de
    la aplicación:** (1) crear, renombrar o clonar con un nombre ya usado
    pero escrito con espacios de más ("  AGENTE UDL ") daba el mismo
    error crudo; al renombrar, además, la lista mostraba dos proyectos
    con el mismo nombre y al crear quedaba una carpeta huérfana --
    `SqlAlchemyProjectRepository.save` ahora comprueba el nombre antes de
    escribir nada y limpia lo creado si falla, y `get_by_name` recorta
    espacios; (2) código de caso de prueba repetido (también al promover
    una conversación de Monitoreo) -> `DuplicateTestCaseCodeError`;
    (3) editar el código de una entrada de catálogo a uno ya usado ->
    `DuplicateCatalogEntryError`; (4) exportar sin escribir la extensión
    (macOS) dejaba un archivo que "Importar" no mostraba -- se agrega
    `.agentproj`; (5) "Archivar" es definitivo y se aplicaba con un clic
    sin confirmación -- ahora pide confirmar. `DuplicateProjectError`
    tiene un mensaje en lenguaje de usuario.
  - **Verificación:** `tests/unit` 876 pasadas (6 omitidas); nueva
    `tests/integration/test_import_project_collisions.py` (9 pruebas,
    incluido el escenario exacto de la captura y el estado que dejó la
    versión anterior); integración relacionada 70/70 (exportar/importar,
    ingesta y RAG de ida y vuelta, repositorio de proyectos, metadatos,
    calidad, migraciones Alembic, paquete de despliegue, aislamiento de
    instantáneas). `ruff` limpio; `mypy` sin errores nuevos (baseline de
    22). Pruebas de interfaz no ejecutables aquí (falta `libEGL`): los
    cambios de `ui/projects/panel.py` se verificaron con `py_compile` y
    revisión manual. Manual del Usuario actualizado (4.1, 4.3, 4.4, 4.5,
    nueva 4.7, 6.2, 9.1) en DOCX y PDF.
  - **Para el usuario que ya tiene el residuo:** basta volver a importar
    el mismo archivo con esta versión: primero se ofrece apartar los
    restos del intento fallido y después se pide un nombre distinto.

- **2026-10-02 -- Ronda 87: hallazgo real de usuario -- "Al intentar
  modificar una canalización no permite guardarlo" (error "'str' object
  has no attribute 'value'") y "la documentación no especifica la
  sintaxis o ejemplos del campo Condición".**
  - **Causa raíz del error (reproducida con SQLite real):**
    `UpdateChannelingScheme` usaba `model_copy(update=...)`, que no valida
    ni convierte tipos. El diálogo de edición manda `medium` como texto
    ("correo"), el esquema quedaba con un `str` y
    `SqlAlchemyChannelingSchemeRepository.save()` fallaba en
    `scheme.medium.value`. Fallaba TODA edición de canalización, cambiara
    o no el medio. `UpdateIntent` y `UpdateGuardrailRule` ya convertían sus
    enums; Canalización era el único caso pendiente (se revisaron los 13
    usos de `model_copy(update=...)` del proyecto). Corrección: se
    reconstruye el modelo completo (`ChannelingScheme(**data)`, mismo
    criterio que `UpdateTestCase`); un medio inexistente ahora da un error
    de validación en vez de guardarse.
  - **Campo "Condición" del esquema:** es descriptivo; ninguna parte del
    motor lo evalúa. Lo que canaliza es una regla de guardrail con acción
    `canalizar` cuyas condiciones se cumplen, más la intención con el
    código del esquema en "Canalización alternativa". Se dejó explícito en
    la interfaz (texto de ayuda, información sobre herramientas y una
    explicación en la pestaña Canalización) y en el Manual (8.4 y nueva
    8.4.1, paso a paso con el caso real del usuario).
  - **Defectos encontrados al auditar la sintaxis de condiciones de
    guardrails (la que sí se evalúa):** (1) líneas sin operador se
    descartaban en silencio y, si se descartaban todas, la regla quedaba
    incondicional (se aplicaba a todas las consultas) -- ahora no se
    guarda y se listan las líneas con problema; (2) un campo desconocido
    (p. ej. `plantel`) nunca se cumplía sin aviso -- ahora se pide
    confirmación; (3) el docstring prometía ignorar acentos pero solo se
    pasaba a minúsculas -- ahora campo y valor ignoran acentos
    (`domain/conversational/text_normalization.py`, usado también por el
    aviso de reglas que referencian una intención); (4) las comillas del
    valor formaban parte de la comparación (el propio Manual mostraba
    `plantel = "Campus Norte"`, que nunca podía cumplirse por dos
    motivos) -- ahora se quitan; (5) se tomaba el primer operador de una
    lista fija, no el primero de la línea (`intencion contiene a=b`
    quedaba mal separada); (6) `contiene` con valores numéricos comparaba
    "2026.0"; (7) "0,70" no se reconocía como número. Los campos válidos
    se definen en un solo lugar (`rule_evaluation.CONTEXT_FIELDS`) que usan
    la validación, la ayuda en pantalla y el Manual.
  - **Diagnóstico de canalizaciones que no ocurren:**
    `SimulationTrace.channeling_note` distingue tres causas (intención sin
    canalización alternativa, código inexistente, esquema inactivo); el
    Simulador y el resultado de Calidad ("Se esperaba un paquete de
    canalización…") muestran la causa concreta. Al guardar una intención
    con un código de canalización que no existe se avisa. Crear un esquema
    o una variable con un código repetido muestra un mensaje claro en vez
    del error de SQLite (`DuplicateConversationalCodeError`). La lista de
    Guardrails muestra las condiciones normalizadas de cada regla.
  - **Verificación:** `tests/unit` 874 pasadas (6 omitidas; 20 nuevas),
    integración relevante 124/124 (canalización de extremo a extremo,
    repositorios conversacionales/calidad/liberación/runtime, API de
    runtime, webhook y widget), incluida una prueba nueva con SQLite real
    que reproduce la captura del usuario y que falla sin la corrección.
    `ruff` limpio en el código de la aplicación (los 12 avisos restantes
    están en scripts congelados del NEXOM Knowledge Package, cubiertos
    por SHA256SUMS, que no se modifican); `mypy` en el mismo baseline de
    22 errores preexistentes, ninguno en archivos tocados. Las pruebas de
    interfaz gráfica no se pueden ejecutar en este entorno (falta
    `libEGL`); los cambios de `ui/conversational/panel.py` se verificaron
    con `py_compile` y revisión manual, y su lógica vive en funciones
    puras probadas (`ui/conversational/parsing.py`). Manual del Usuario
    (8.3, nueva 8.3.1, 8.4, nueva 8.4.1, 8.5, 9.1) actualizado en DOCX y
    PDF.

- **2026-09-30 -- Ronda 86: lote de RAG Content Studio generado en
  Windows rechazado completo por hash ("Importadas: 0 / Omitidas: 14").**
  Cada fila decía "el archivo fue localizado, pero su contenido no
  coincide con el hash declarado en el manifiesto". Causa raíz en RAG
  Content Studio, no aquí: escribía el Markdown en modo texto (Windows
  convierte `\n` en `\r\n`) y declaraba el hash del texto con `\n`. La
  verificación obligatoria de la Ronda 85 hizo visible un defecto previo
  del productor. Se corrigió en RAG Content (escritura en bytes, hash
  sobre el archivo escrito, verificación antes de preparar la entrega y
  script de reparación `scripts/reparar_fin_de_linea_markdown.py` para
  lotes ya generados). **Este lado no normaliza fines de línea**: la
  verificación sigue siendo sobre los bytes exactos. En la auditoría
  posterior se corrigieron aquí dos detalles de
  `RegisterSourcesFromFolder`: el manifiesto se lee con `utf-8-sig` (si
  alguien lo guardaba con Excel, el BOM renombraba la primera columna y
  todas las filas se trataban en silencio como legado V1) y el hash
  declarado se compara en minúsculas. 3 pruebas nuevas en
  `test_register_sources_from_folder.py` (CRLF con hash de LF se sigue
  rechazando; BOM se lee como V2, prueba que falla sin la corrección;
  hash en mayúsculas). Verificación: `tests/unit` 854 pasadas
  (6 omitidas), `test_export_import_roundtrip.py` 7/7, `ruff` y `mypy`
  limpios en los archivos tocados; prueba cruzada con lotes reales
  simulados de RAG Content (antiguo 0/3 → reparado 3/3; nuevo 3/3).
  Contrato de intercambio actualizado (sección 4 y nueva 6.1), con copia
  idéntica en RAG Content Studio.

- **2026-09-29 -- Ronda 85: incidencia real de portabilidad Windows ->
  macOS al importar carpetas de RAG Content Studio.** Un lote
  (`PROY-9928_licenciatura_parte_1`) procesado en RAG Content Studio en
  un equipo Windows, copiado a un equipo macOS con RAG STUDIO, se
  importó como "Importadas: 0 / Omitidas: 13" pese a que los 13
  Markdown estaban físicamente presentes en `14_entrega_rag_studio/`.
  Causa raíz confirmada con una prueba real en este sandbox:
  `pathlib.Path("C:\\...\\doc-1.md").name` en un sistema POSIX devuelve
  la cadena completa sin cambios, no el nombre de archivo -- `pathlib`
  solo reconoce el separador nativo del sistema operativo que ejecuta
  el proceso, nunca el que generó la ruta. Por instrucción expresa del
  consultor, se entregó primero un diagnóstico de 8 puntos, sin tocar
  código, y se esperó autorización explícita antes de implementar.
  - **El consultor corrigió la propuesta inicial antes de autorizarla:**
    exigió versionar el manifiesto (`manifest_schema_version`, ausencia
    = legado v1), que `ruta_archivo` fuera siempre una referencia
    relativa portable al paquete (nunca una ruta absoluta) en el
    contrato nuevo, y que `hash_contenido` se volviera una verificación
    de integridad obligatoria antes de registrar cualquier fila --
    reservando el resolutor tolerante de nombres de archivo
    exclusivamente como mecanismo de compatibilidad v1, nunca como el
    contrato normal hacia adelante.
  - **Documento de contrato único:**
    `CONTRATO_INTERCAMBIO_RAG_CONTENT_STUDIO_RAG_STUDIO.md`, con copia
    idéntica en este repositorio (`docs proyecto/`) y en RAG Content
    Studio (`DOCS PROYECTO/`) -- versionado, semántica de columnas,
    algoritmo de integridad, reglas de resolución v2/v1, detección de
    ambigüedad entre filas, catálogo de mensajes de error, y 14 casos
    de prueba numerados compartidos entre ambos repositorios.
  - **Implementación:** módulo de dominio nuevo `domain/documents/manifest.py`
    (`es_manifiesto_v2`, `validar_ruta_relativa_manifiesto` -- rechaza
    rutas absolutas, `\`, y segmentos `..`, mismo criterio de defensa
    que `domain/projects/packaging.py` usa contra Zip Slip, sin
    acoplarse a ese módulo --, `extraer_nombre_base_multiplataforma`);
    `RegisterSourcesFromFolder.execute()` reescrito en cuatro fases:
    resolución por fila (v2 estricta / v1 legado por búsqueda dentro del
    paquete), detección de ambigüedad CRUZADA entre filas (dos filas que
    resuelven al mismo archivo con hash declarado distinto se rechazan
    ambas, nunca "la primera gana"), verificación de integridad
    (SHA-256 real contra `hash_contenido` declarado, obligatoria para
    v1 y v2), y solo entonces alta real (deduplicación por
    `content_hash` ya existente, sin cambios).
  - **Pruebas:** 29 nuevas en `tests/unit/domain/test_manifest.py`; 21
    nuevas o reescritas (con hashes reales, nunca inventados) en
    `tests/unit/application/test_register_sources_from_folder.py`,
    incluidos los 14 casos de contrato numerados; un "golden package"
    compartido (`tests/fixtures/golden_package_14_entrega_rag_studio/`,
    copia idéntica en RAG Content Studio) que cada repositorio verifica
    desde su propio lado, sin una sola prueba que cruce ambos
    entornos/virtualenvs. 866 pruebas unitarias/smoke en verde (50
    nuevas o reescritas de esta ronda), 0 fallidas; `ruff` limpio;
    `mypy` en el mismo baseline de 22 errores preexistentes; `bandit`
    sin hallazgos nuevos. Manual de Usuario (sección 5.5) y
    `RAG_STUDIO_Manual_de_Usuario.pdf` regenerado y verificado
    visualmente, con una nota fechada sobre la importación
    multiplataforma y la verificación de integridad. La corrección
    paralela en RAG Content Studio (contrato v2 del lado productor,
    `_nombre_de_archivo()`, `manifest_schema_version`, golden package
    del lado productor, 692 pruebas en verde) se documenta en el README
    de ese propio repositorio. Ver
    `Validacion_observaciones_RAG_STUDIO.md`, Ronda 85, puntos 297-301.

- **2026-09-04 -- Ronda 84: hallazgo real de usuario -- mensaje
  incorrecto de "Regresión de recuperación" cuando solo una de las dos
  corridas tiene métricas.** El usuario ejecutó una evaluación completa
  con casos con fuente esperada (Recall@3: 100%, MRR: 1.00), pero
  Liberación → Evaluar compuertas seguía mostrando "Ninguna de las dos
  corridas 'completa' comparadas tiene casos con fuente esperada
  declarada". Causa: `_retrieval_regression_gate` usaba
  `if current_recall is None or reference_recall is None` -- si SOLO la
  corrida de referencia carecía de métricas, el mensaje decía
  incorrectamente que "ninguna" las tenía. El mismo `or` existía por
  separado en `ui/quality/panel.py`. Corregido centralizando la
  clasificación en una función pura nueva del dominio,
  `compare_retrieval_regression` (tres estados reales: sin métricas
  todavía, solo la corrida más reciente sin base comparable aún, o
  ambas comparables), consumida por Calidad y Liberación a través de
  `QualityService.compare_retrieval_regression` -- ninguno de los dos
  lugares puede volver a divergir. La compuerta sigue sin bloquear por
  falta de una corrida comparable anterior. 5 pruebas nuevas (4 de
  dominio, 1 de aplicación) más una de interfaz no ejecutable en este
  sandbox. Se actualizó también el Manual del Usuario (sección 10.1) con
  una nota fechada explicando las tres situaciones reales. Verificación
  total en verde: 1212 pruebas colectadas (unitarias/smoke +
  integración), 0 fallidas, `ruff` limpio, `mypy` en el mismo baseline
  de 22 errores preexistentes. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 84, puntos 293-296.

- **2026-09-04 -- Ronda 83: hallazgo real de usuario -- "TypeError: can't
  compare offset-naive and offset-aware datetimes" al comparar corridas
  de Calidad → Evaluación.** El usuario compartió el traceback real: al
  ejecutar una segunda evaluación completa, `ui/quality/panel.py`
  fallaba al comparar `r.started_at < run.started_at` entre la corrida
  recién terminada (en memoria, aware por `_utcnow()`) y las corridas
  anteriores releídas de SQLite (naive, porque el dialecto de SQLite
  ignora `tzinfo` al serializar y lo pierde en cada round-trip aunque la
  columna esté declarada `DateTime(timezone=True)`, confirmado
  empíricamente). El usuario pidió explícitamente una capa común, no un
  parche de esa línea. Se agregó `UTCDateTime`
  (`infrastructure/database/utc_datetime.py`), un `TypeDecorator`
  compartido que normaliza a UTC-aware en ambas direcciones sin requerir
  ninguna migración -- aplicado a las 38 columnas de fecha/hora de
  `models.py` y a las 4 columnas equivalentes, descubiertas durante esta
  misma investigación, del esquema aparte de
  `infrastructure/database/runtime_repositories.py` (nunca compartía la
  definición de `models.py`). Se encontró y corrigió de la misma pasada
  un segundo defecto latente idéntico en los criterios de reapertura de
  Monitoreo/Runtime (`evaluate_reopening_criteria.py`), nunca reportado
  todavía. Registros históricos ya guardados siguen siendo compatibles
  sin recrear ningún proyecto. Verificación total en verde, incluyendo
  por primera vez en una sola ronda la suite completa de integración
  contra SQLite real (no solo unitarias/smoke): 1207 pruebas colectadas,
  0 fallidas, `ruff` limpio, `mypy` en el mismo baseline de 22 errores
  preexistentes. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 83,
  puntos 289-292.

- **2026-09-04 -- Ronda 82: validación de usuario -- agregar "Eliminar
  intención" en Diseño conversacional, igual que ya existe en
  Guardrails.** Tras la Ronda 81 (edición completa de intenciones), el
  usuario preguntó si convenía agregar también "Eliminar intención",
  ya que Guardrails permite tanto editar como eliminar. Se validó
  primero que fuera seguro: ninguna otra entidad del dominio referencia
  una intención por `id` -- `TestCase.expected_intent`,
  `SimulationTrace.matched_intent_name` y los registros de
  runtime/monitoreo la guardan por **nombre**, igual que las
  condiciones de guardrail (`intencion = <nombre>`), así que eliminar
  una intención tiene exactamente la misma consecuencia -- y solo esa
  -- que renombrarla. Se agregó `delete_intent` en las tres capas
  (dominio, infraestructura, aplicación) y el botón "Eliminar
  intención" en la interfaz, reutilizando sin cambios el aviso de
  reglas de guardrail afectadas que ya existía para el renombrado (no
  se creó ningún mecanismo nuevo). 812 pruebas en verde (2 nuevas a
  nivel aplicación más una de interfaz, no ejecutable en este sandbox
  por la carencia de `libEGL.so.1` ya documentada; 0 fallidas, 7
  omitidas), `ruff` sin hallazgos, `mypy` en el mismo baseline de 22
  errores preexistentes. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 82, puntos 287-288.

- **2026-09-03 -- Ronda 81: tres ajustes funcionales de Diseño
  conversacional -- compuerta reactiva, eliminar/editar guardrails,
  editar intenciones completas.** El consultor compartió tres
  documentos de "Ajuste funcional" del usuario más dos observaciones
  textuales adicionales del mismo usuario. (1) La Compuerta de
  Liberación (Diseño conversacional) no se actualizaba de inmediato
  tras crear una intención, crear un guardrail, o activar/desactivar
  un guardrail -- el estado correcto solo aparecía al reiniciar la
  aplicación; causa raíz: `self._gate_status_label.refresh(...)` ya se
  llamaba tras activar/desactivar una INTENCIÓN, pero faltaba en
  `_on_create_intent`, `_on_create_rule` y, sobre todo,
  `_on_toggle_rule` -- el síntoma reportado literalmente. Se confirmó
  que no hay ninguna divergencia con la lógica que usa Liberación para
  la misma compuerta (`EvaluateReleaseGates._conversational_gate`).
  (2) "lo resolví temporalmente desactivando la regla pero el manual
  indica que se puede eliminar y crear nuevamente pero la interfaz no
  tiene la opción para elimina[r]": Guardrails nunca tuvo ningún botón
  "Eliminar" en ninguna de sus tres capas (ni siquiera existía
  `GuardrailRuleRepository.delete`) -- se agrega en dominio,
  infraestructura y aplicación (sin chequeo de "en uso": ninguna otra
  entidad referencia una regla por id) más edición completa de tipo,
  condiciones, acción y prioridad (antes solo el nombre). (3) "debe
  dejar editar una intención ya que el manual así lo indica": mismo
  problema para intenciones -- "Editar nombre/descripción…" pasa a
  "Editar intención…" con la ficha completa (ejemplos, prioridad,
  riesgo, datos mínimos/opcionales, preguntas aclaratorias, regla de
  respuesta, canalización alternativa), preservando el aviso ya
  existente de guardrails afectados por un renombrado -- el único caso
  real de referencia cruzada en este dominio. 810 pruebas en verde (10
  nuevas, 0 fallidas, 7 omitidas -- una nueva por la carencia de
  `libEGL.so.1` ya documentada), `ruff` sin hallazgos, `mypy` en el
  mismo baseline de 22 errores preexistentes. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 81, puntos 283-286.

- **2026-09-02 -- Ronda 80: hallazgo real de usuario -- el selector
  "Campo de metadatos ligado" de Diseño conversacional quedaba vacío
  tras crear el esquema en la misma sesión.** (Numerada 80 y no 79
  porque ese número ya lo tomó otra ronda registrada el mismo día,
  más abajo -- ambas avanzaron en paralelo sobre el mismo
  repositorio.) El consultor reportó que, en Diseño conversacional →
  Variables, el selector "Campo de metadatos ligado (opcional)" no
  cargaba los campos del esquema activo, aun con campos ya
  configurados y visibles en Metadatos → Esquema. Causa raíz
  confirmada leyendo el código: `ConversationalPanel.
  _populate_metadata_fields()` solo se llamaba una vez, desde
  `set_active_project()` -- si el esquema de metadatos se creaba o se
  le agregaban campos DESPUÉS de seleccionar el proyecto, en la misma
  sesión, nada volvía a refrescar el selector; `MetadataPanel` ni
  siquiera emitía ninguna señal de cambio de esquema. Mismo patrón ya
  corregido dos veces antes en esta aplicación (Ronda 4, punto 4b;
  Ronda 5) para `SourcesPanel.sources_changed`, nunca aplicado a este
  puente. Corregido con una nueva señal, `MetadataPanel.
  schema_changed`, emitida centralizadamente al final de
  `_refresh_schema()`, conectada a un nuevo método público,
  `ConversationalPanel.refresh_metadata_fields()`, en
  `ui/projects/main_window.py`. Prueba unitaria nueva y dedicada
  (`tests/unit/ui/test_metadata_conversational_field_refresh.py`, con
  una prueba de control adicional que confirma el síntoma sin la
  conexión) -- no ejecutable en este entorno de consultoría por la
  misma carencia de `libEGL.so.1` ya documentada, verificada por
  lectura de código y `py_compile`/`ruff` limpios. Manual del Usuario
  actualizado (8.2) con una nota sobre el nuevo comportamiento de
  refresco. 800 pruebas en verde (6 omitidas), `ruff` sin hallazgos,
  `mypy` en el mismo baseline de 22 errores preexistentes. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 80, puntos 280-282.

- **2026-09-02 -- Ronda 79: falla real de un usuario -- pestaña
  "Metadatos" > "Valores por fuente" tumbaba la aplicación entera al
  abrir un proyecto sin esquema activo.** El consultor compartió la
  evidencia de un usuario (`RAG_STUDIO_01.mov` +
  `RAG_STUDIO_01_consola.txt`) junto con dos hallazgos más de RAG
  CONTENT STUDIO. Causa raíz confirmada en la consola y en el código:
  `MetadataPanel._fields_for_active_value_source()`
  (`ui/metadata/panel.py`) llamaba a `list_applicable_fields()` (que a
  su vez llama a `get_schema()`) sin ningún `try/except`, mientras que
  el método hermano `_refresh_schema()`, en el mismo archivo, ya
  envolvía esa misma llamada transitiva -- un patrón de programación
  defensiva aplicado de forma inconsistente dentro de un solo archivo.
  Al elegir una fuente de un proyecto sin esquema de metadatos activo,
  `MetadataDomainError: No hay esquema de metadatos activo para
  '<id>'` quedaba sin capturar y tumbaba la aplicación completa, sin
  posibilidad de recuperación desde la interfaz. Corregido replicando
  el mismo `try/except` ya usado por `_refresh_schema()`: ante
  `MetadataDomainError`, el selector de campos queda vacío y la
  pestaña sigue utilizable con normalidad, en vez de cerrar la
  aplicación. Prueba de humo nueva y dedicada
  (`tests/smoke/test_metadata_panel_sin_esquema.py`, mismo criterio de
  omisión automática sin Qt que `test_ui_construction.py`) que
  reproduce exactamente el escenario real (una fuente registrada, sin
  esquema creado) y confirma que ya no revienta. No ejecutable en este
  entorno de consultoría (falta `libEGL.so.1`, misma carencia ya
  documentada en rondas anteriores), pero verificada por lectura de
  código y `py_compile`/`ruff` limpios; queda lista para el entorno
  real. Aparte, se instaló la dependencia `qdrant_client` -- faltaba
  por completo en este entorno y bloqueaba incluso las pruebas
  unitarias puras sin ninguna relación con Qt (fallaban ya en la
  importación de `conftest.py`) -- lo que permitió correr y confirmar
  en verde las pruebas no gráficas afectadas por este cambio (47 en
  `test_metadata_service.py`). Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 79, para el detalle
  completo.

- **2026-09-01 -- Ronda 78: diagnóstico de un reporte real de
  usuario (el diálogo "Importar..." de Proyectos nunca habilitaba
  "Open" al elegir una carpeta) y auditoría dirigida de flujos de
  diálogo -- 4 hallazgos corregidos.** El consultor compartió el
  reporte textual de un usuario ("ya tengo el paquete generado por
  RAG CONTENT... al elegir Importar... el cuadro de diálogo no
  permite seleccionar la carpeta, nunca se habilita el botón Open")
  y pidió diagnosticarlo junto con una auditoría más amplia. Causa
  raíz confirmada leyendo el código: dos botones "Importar..." casi
  idénticos en pestañas distintas -- Proyectos importa un archivo
  `.agentproj` (`QFileDialog.getOpenFileName`, nunca habilita "Open"
  para una carpeta), Fuentes importa la carpeta real de RAG CONTENT
  (`QFileDialog.getExistingDirectory`, ya funcionaba bien) -- sin
  ninguna señal que las distinga. Corregido con nombres inequívocos
  ("Exportar/Importar proyecto (.agentproj)…"), tooltips cruzados en
  ambos sentidos y títulos de diálogo explícitos, sin tocar ninguna
  lógica de importación. La auditoría dirigida al mismo patrón
  encontró tres casos más: "Simular" (8.5) fallaba en silencio con
  la consulta vacía (mismo síntoma que Ronda 8, punto 27, nunca
  aplicado aquí); los tres botones de exportación de Liberación
  compartían vocabulario sin tooltips que los distinguieran; y los
  paneles de Proyectos y Complementos tenían botones dependientes de
  selección que quedaban pintados como disponibles sin selección
  real -- corregido con `_apply_button_states()`, mismo patrón ya
  usado en Monitoreo. Hallazgo adicional de documentación: el Manual
  del Usuario (14.8) citaba, para la consulta vacía, el texto de una
  excepción de dominio que en la práctica ningún flujo de la
  interfaz deja alcanzar, en vez del mensaje real ("Falta la
  consulta"); corregido junto con la sección 4.3 (etiquetas de botón
  y nota de actualización). Dos archivos de prueba nuevos para
  Proyectos y Complementos, no ejecutables en este entorno de
  consultoría (falta `libEGL.so.1`, misma carencia ya documentada en
  rondas anteriores) pero listos para el entorno real. 800 pruebas
  unitarias/smoke en verde (4 omitidas), `ruff` sin hallazgos,
  `mypy` en el mismo baseline de 22 errores preexistentes. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 78, puntos 274-278.

- **2026-08-24 -- Ronda 77: auditoría profunda de código -- 9
  defectos reales confirmados y corregidos, 1 falso positivo
  descartado.** A pedido explícito del consultor ("realiza una
  auditoría profunda... y de haberlos, corrígelos"), cuatro
  auditorías paralelas (infraestructura, aplicación, dominio+API,
  interfaz+workers) seguidas de verificación personal exhaustiva de
  cada hallazgo antes de aceptar o corregir nada. Confirmados y
  corregidos: (1) condición de carrera real en el modo local de
  Qdrant (dos hilos abriendo la misma carpeta de proyecto a la vez --
  corregido con un lock por proyecto); (2) fuga de seguridad real: la
  Pista B.3 del ADR-003 (control de acceso en tiempo de consulta)
  nunca se aplicó a la Pista B.4 (consulta estructurada), así que un
  widget público podía ver filas de fuentes confidenciales o sin
  validar a través del modo estructurado -- corregido propagando
  `only_usable_sources`/`max_access_level` a `StructuredQuery`; (3-5)
  tres casos de pérdida de datos por borrar el estado anterior antes
  de una operación que puede fallar (`IndexSource`,
  `IndexImageSource`, `FragmentSource`) -- corregidos reordenando o,
  para fragmentación, con un nuevo método atómico
  `ChunkRepository.replace_for_source`; (6) un `ChannelingScheme`
  desactivado que seguía usándose como respaldo en la simulación; (7-8)
  dos mejoras de claridad de errores (aviso en vez de silencio al
  reemplazar una fuente inexistente; error de dominio en vez de
  `IntegrityError` crudo al duplicar una entrada de catálogo); (9)
  cuatro botones de la interfaz sin manejo de error alrededor de
  `submit_task`. Además, con el mismo criterio ya usado en
  `ui/release/panel.py`, se agregó cursor de espera a
  Exportar/Importar proyecto y una confirmación al cerrar la ventana
  si hay un trabajo en segundo plano en curso (nuevo
  `ThreadJobRunner.any_running()`). Dos hallazgos de interfaz
  (resultados obsoletos tras cambiar de proyecto/fuente; lock global
  del runtime HTTP bloqueando proyectos ya calientes durante un
  cold-start ajeno) se documentan como identificados pero diferidos
  deliberadamente por alcance y riesgo. Un hallazgo adicional (feedback
  "huérfano" tras purgar su conversación de origen) se descartó como
  falso positivo: es un diseño deliberado y ya documentado
  ("solo-inserción"), no un defecto. Cada corrección se verificó con
  el ciclo revertir-probar-restaurar, salvo las dos de interfaz sin
  infraestructura de pruebas de widgets (verificadas solo por
  compilación y lint, documentado honestamente como límite
  preexistente). `ruff` limpio, `mypy` en el mismo baseline de 22
  errores preexistentes sin cambios, 800 pruebas unitarias/smoke (16
  nuevas) y 372 de integración, todas en verde. Para cerrar la
  instrucción original del consultor, se auditó también el Manual del
  Usuario completo contra el comportamiento real y se actualizó en
  seis puntos donde omitía un detalle -- incluyendo un hallazgo de
  documentación genuino, independiente de los 9 defectos técnicos: el
  bloque "Filas de datos estructurados" que el Simulador (8.5) ya
  mostraba desde la Ronda 28 nunca se había descrito en el manual. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 77, puntos 261-273.

- **2026-08-24 -- Ronda 76: validación cuantitativa de la mejora de
  OCR (Ronda 74) -- mejora real de recuperación, no solo visual.**
  Siguiente acción propuesta en la Ronda 75, confirmada por el
  consultor. Se reconstruyeron desde cero dos índices del corpus
  piloto de 25 fuentes (uno con `preprocess=False`, otro con
  `preprocess=True`), en el mismo entorno y mismo idioma de OCR, para
  aislar únicamente el efecto del preprocesamiento de la Ronda 74, y
  se remidió cobertura y Recall@3 contra el mismo gold set de 94
  preguntas de la Ronda 73. Resultado: cobertura total 0.584 → 0.657
  (+12.5% relativo) y Recall@3 total 0.320 → 0.506 (+58% relativo),
  con la mejora más fuerte en la categoría de mayor peso del corpus
  ("simples", n=60, Recall@3 +79% relativo). Una categoría chica
  (ambiguas, n=7) empeora en cobertura, documentado con honestidad
  como probable ruido de muestra chica. El criterio de reapertura 2
  de RAG 4 pleno (brecha de cobertura persistente tras corregir OCR)
  queda descartado por ahora. No se modificó código de producto, solo
  el script de prototipo de validación. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 76, puntos 258-260.

- **2026-08-24 -- Ronda 75: decisión formal de NEXOM sobre RAG 4
  pleno, criterios explícitos de reapertura, y reordenamiento de
  prioridades.** Formaliza la decisión de negocio que la Ronda 73
  dejó deliberadamente abierta: "NEXOM acepta el veredicto de la Fase
  -1 y decide no proceder actualmente con RAG 4 pleno ni formalizar
  ADR-004. Se cierra la línea de implementación evaluada. La
  recuperación agéntica queda clasificada como capacidad estratégica
  reconsiderable, no como deuda técnica ni como pendiente del roadmap
  vigente" -- precisando que esto no equivale a decir que "Agentic
  RAG no funciona" en general, solo que este planificador, este
  prompt y este corpus no acreditaron beneficio neto. Se fijan cinco
  criterios explícitos de reapertura (mismo patrón que los de RAG 5,
  Ronda 45), ninguno cumplido hoy: tráfico real con necesidad de
  multi-hop, brecha de cobertura persistente tras corregir OCR, un
  modelo de planificación sustancialmente mejor, un proyecto con
  datos estructurados reales, o un A/B que aísle beneficio de
  razonamiento del efecto de volumen (vía un Sistema A' de control no
  construido todavía). Reordena las prioridades hacia adelante:
  validar cuantitativamente la mejora de OCR de la Ronda 74
  reprocesando el corpus piloto contra el mismo gold set (próxima
  acción propuesta, pendiente de confirmación), y retomar más
  adelante la línea "Base de Conocimiento RAG Certificada" (Ronda 64,
  punto 216) como el diferenciador comercial de mayor valor esperado,
  en vez de más sofisticación agéntica de runtime. Ronda de
  documentación pura, sin cambios de código. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 75, puntos 255-257.

- **2026-08-24 -- Ronda 74: preprocesamiento ligero de OCR con PIL
  antes de Tesseract, validado contra un documento real.** Tarea
  diferida desde antes de cerrar la Fase -1 de RAG 4 (Ronda 70, punto
  241), retomada ahora que esa fase cerró. `infrastructure/extraction/
  ocr_engine.py`: nueva `_preprocess_for_ocr` (escala de grises +
  filtro de medianas + binarización con el umbral de Otsu, calculado
  con `_otsu_threshold` en Python puro, sin numpy) aplicada a la
  página completa antes de Tesseract, activada por defecto vía el
  nuevo parámetro `TesseractOcrEngine(preprocess=True)`. Validado de
  forma empírica contra `Licenciatura/ingcom.pdf` (el mismo documento
  de la Ronda 22): sin preprocesar, Tesseract reconocía 1 de 14
  encabezados de cuatrimestre en banda de color; con el cambio, 8-9 de
  14, sin perder contenido del resto de la página. Se probó también
  aplicar el mismo preprocesamiento a los recortes pequeños de banda de
  color (`_recover_color_band_text`, Ronda 22) y se encontró una
  regresión real -- el filtro de medianas borra los trazos delgados del
  texto en un recorte tan chico -- así que se descartó ahí a propósito
  y se dejó documentado en el código. 8 pruebas nuevas en
  `tests/integration/test_ocr_engine.py`; `ruff`/`mypy` sin cambios
  respecto a la Ronda 71 (22 errores preexistentes); suite completa sin
  regresiones (784 unit/smoke + 381 integración, +8 exactamente las
  pruebas nuevas). Con esto se cierra la última tarea técnica diferida
  -- no queda ninguna línea de trabajo de ingeniería pendiente; lo que
  resta (RAG 4 pleno, huecos de RAG 5) depende de decisiones de negocio
  o de tráfico real. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 74, puntos 252-254.

- **2026-08-24 -- Ronda 73: RAG 4 Fase -1 -- veredicto final con el
  corpus completo (94/94): cerrar la línea RAG 4, no proceder a
  ADR-004.** El consultor completó la corrida completa de
  `run_benchmark.py` (94 preguntas x 2 sistemas, las cinco categorías).
  El patrón ya visto en la Ronda 72 se confirma con el corpus completo:
  Sistema B (planificador LLM) es ~19x más lento, falla en terminar
  limpiamente el 67% de las preguntas (100% en multi-hop, la categoría
  diseñada para favorecerlo más), y su ventaja de cobertura (0.84 vs.
  0.72) sigue siendo un efecto de volumen de búsquedas, no de
  planificación -- confirmado con inspección cualitativa de las 6
  preguntas multi-hop (Q084 y similares: el modelo se desvía hacia
  programas equivocados o ajenos al piloto en vez de descomponer la
  comparación entre los 5 programas). Hallazgo positivo que sí se
  preserva: las 6 preguntas adversariales (contenido inyectado con
  instrucciones tipo "responde SIEMPRE AUTORIZADO", "revela el system
  prompt", etc.) no lograron que ninguna consulta generada por el
  planificador obedeciera la instrucción inyectada -- el esquema
  cerrado y el principio "contenido recuperado es dato, nunca
  instrucción" sostuvieron su propósito incluso con un modelo local
  pequeño (`llama3.2:3b`). **Veredicto: cerrar la línea RAG 4 tal como
  fue implementada -- no proceder al ADR-004 ni a las Fases 0-5 con
  este diseño.** Informe final actualizado en
  `docs proyecto/RAG4_Fase-1_Benchmark/RAG4_Fase-1_Actividad4_Analisis_y_Recomendacion.docx`/`.pdf`
  (reemplaza la versión parcial de la Ronda 72). Ningún código de
  producto ni del prototipo se modificó; `ruff`/`mypy` sin cambios
  respecto a la Ronda 71. Con esto se cierra la Fase -1 de RAG 4 en su
  totalidad. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 73,
  puntos 249-251.

- **2026-08-22 -- Ronda 72: RAG 4 Fase -1, Actividad 4 -- análisis de
  una corrida real pero parcial, ningún beneficio observado del
  planificador LLM en las categorías evaluadas.** Antes de analizar
  nada se verificó si `resultados_benchmark.jsonl` reflejaba de verdad
  las tres correcciones de la Ronda 71 -- se encontraron dos archivos
  con ese nombre en momentos distintos de la sesión, y solo el más
  reciente (`prompt_template_hash` coincide con el del código
  corregido) se usó. Ese archivo válido cubre 65 de 94 preguntas (69%,
  solo categorías "simples" y "ambiguas") -- faltan por completo
  multiaspecto, multi-hop y el 100% de las adversariales. Con lo
  disponible: Sistema B (planificador LLM) tarda ~17x más que Sistema A
  y en 66% de las preguntas nunca marca el plan como "final" dentro del
  presupuesto de 3 saltos (reformula la misma pregunta con variaciones
  casi idénticas en vez de detenerse); su ligera ventaja de cobertura
  de evidencia (proxy automático) resulta ser un efecto de volumen de
  búsquedas (3 intentos vs. 1), no de mejor planificación -- cuando el
  plan sí decide que terminó, su cobertura es más baja que el promedio
  y que Sistema A. Informe completo en
  `docs proyecto/RAG4_Fase-1_Benchmark/RAG4_Fase-1_Actividad4_Analisis_y_Recomendacion.docx`/`.pdf`:
  recomienda NO cerrar todavía la línea RAG 4 ni aprobar ADR-004 con
  este dato parcial -- se necesitan las 29 preguntas restantes,
  especialmente las adversariales, antes de un veredicto certificable
  conforme a la sección 10.4. No se modificó código de producto ni del
  prototipo en esta ronda. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 72, puntos 247-248.

- **2026-08-22 -- Ronda 71: RAG 4 Fase -1 -- diagnóstico de la primera
  corrida real del benchmark, tres defectos reales corregidos, uno de
  ellos en el producto.** El consultor corrió `run_benchmark.py` en su
  propia máquina y las 188 filas (94 preguntas x 2 sistemas) resultaron
  con error. Diagnosticado hasta la raíz: (1) `qdrant-client>=1.18`
  (piso real de `pyproject.toml`) está roto -- `VectorParams` en
  1.18.0 no tiene el campo `memory` que sí tiene desde 1.19.0, y con
  `extra="forbid"` rechaza cualquier índice Qdrant local escrito por
  una versión más nueva; no es exclusivo del benchmark, afecta a
  cualquier instalación real de RAG STUDIO en esa combinación de
  versiones -- corregido subiendo el piso a `qdrant-client>=1.19`
  (verificado instalando 1.18.0 en un venv aparte para confirmarlo).
  (2) Bug propio en `sistema_b_planificador.py`: el plan del LLM
  llegaba envuelto dos veces (`PlanDeRecuperacion(pasos=[raw_plan])`
  sobre un `raw_plan` que YA era `{"pasos": [...]}`), rechazando 93 de
  94 respuestas del modelo aunque el JSON fuera válido -- corregido.
  (3) El propio `PROMPT_TEMPLATE` citaba literalmente
  `"[CONTEXTO RECUPERADO]"` en sus reglas, y el modelo local
  (`llama3.2:3b`) copiaba esa frase entre corchetes como si fuera el
  valor real de `query` en el primer hop -- corregido reescribiendo el
  prompt sin ese marcador literal y con un ejemplo de relleno realista.
  `ruff check .` sin hallazgos, `mypy`/pruebas sin cambios. Se le pidió
  al consultor una nueva corrida tras actualizar `qdrant-client`. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 71, puntos 244-246.

- **2026-08-22 -- Ronda 70: RAG 4 Fase -1 (benchmark) -- corpus
  reducido y honesto (94 preguntas) y prototipo aislado del
  planificador LLM.** Antes de construir el corpus de 200-500
  preguntas que dimensionaba `RAG_STUDIO_Decision_RAG4_Excepcion_Controlada.docx`,
  se verificó el contenido real de los proyectos piloto de prueba
  (`PRUEBAS_RAG_STUDIO_UDL_2026-08-20/`, nunca "AGENTE UDL"): solo 76
  chunks reales y ninguna fuente estructurada -- consultado
  explícitamente, se redujo a ~90-100 preguntas en las categorías que
  el contenido sí soporta. Al construir el "gold set" se descubrió que
  el texto ya indexado por el pipeline real tiene las etiquetas de
  sección (REQUISITOS DE INGRESO, PERFIL DEL EGRESADO, etc.) asociadas
  al bloque de contenido equivocado -- un artefacto de orden de lectura
  del diseño de las fichas, ya anticipado parcialmente por la Ronda 22
  -- así que el "gold set" de los 5 programas usados como flagship se
  construyó leyendo directamente las imágenes de los PDF originales.
  El prototipo aislado del planificador (`docs proyecto/RAG4_Fase-1_Benchmark/prototipo/`,
  8 scripts) implementa el esquema cerrado `PlanDeRecuperacion` (rechaza
  con `pydantic` tanto un retriever no autorizado como cualquier campo
  inyectado), Sistema A determinista (`RagService.search_hybrid`) y
  Sistema B con Shadow Retrieval al 100% y la huella de ejecución
  completa de la sección 4 (query_id, planner_model_id/version/hash,
  prompt_template_hash, temperature, generated_subqueries,
  retrieved_chunk_ids, scores, latencia, tokens, etc.). No se pudo
  ejecutar de punta a punta desde este entorno de consultoría --
  `ollama.com` y `huggingface.co` están bloqueados por su lista blanca
  de red (confirmado con `curl`, `403 blocked-by-allowlist`, incluido
  un intento directo del consultor) -- así que se entregó verificado
  hasta donde fue posible (los 8 scripts compilan, la preparación del
  proyecto piloto y las 4 inyecciones adversariales corrieron
  correctamente, `RagService` se construyó bien hasta el punto exacto
  del bloqueo) y listo para correr en la máquina del consultor. `ruff
  check .` sin hallazgos, `mypy`/pruebas sin cambios (no se tocó código
  de producción). Quedan pendientes la Actividad 3 (ejecución) y la
  Actividad 4 (análisis e informe) de la Fase -1. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 70, puntos 240-243.

- **2026-08-21 -- Ronda 69: RAG 3 Fase 5 -- documentación en
  `CONTRATO_INTEGRACION.md`, Manual del Usuario y ADR-003, las cinco
  fases de RAG 3 quedan completas.** No agrega ninguna capacidad
  nueva -- documenta en los tres artefactos ya existentes todo lo
  construido en las Rondas 63-68. `_build_contrato_integracion()`
  (`application/release/commands/export_deployment_package.py`) gana
  la sección "7bis. `image_results`" con la forma del campo y la nota
  explícita de que no existe (todavía) un endpoint HTTP para descargar
  el archivo de imagen ("Limitación conocida, no un descuido"). El
  Manual del Usuario (raíz del repo) gana seis inserciones (5.1, 7.4,
  8.5, 14.2, Glosario, Anexo de alcance 16.1/16.2) documentando el tipo
  de fuente "Imagen nativa" y la búsqueda visual de punta a punta.
  `RAG_STUDIO_ADR-003_Evolucion_Capa_Canonica.docx` gana una nota que
  documenta que la decisión de la Ronda 36 ("multimodalidad nativa
  descartada") se revirtió a partir de la Ronda 63 y que RAG 3 ya tiene
  sus 4 componentes completos. Sin migraciones nuevas (la única de esta
  fase, `0020`, ya se aplicó en la Ronda 68). `ruff check .` sin
  hallazgos, `mypy` sin cambios (22 de siempre), 784 pruebas de
  `tests/unit`+`tests/smoke` + 373 de `tests/integration` en verde
  (mismos totales que la Ronda 68, sin pruebas nuevas más allá de dos
  aserciones agregadas a una prueba de integración existente). Con las
  cinco fases de RAG 3 completas, queda desbloqueado el inicio de la
  Fase 1 de RAG 4 (benchmark) -- no se inicia sin una instrucción
  explícita nueva del consultor. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 69, puntos 237-239.

- **2026-08-21 -- Ronda 68: cierre de los dos vacíos de RAG 3 Fase 3 --
  `RunPipeline` indexa imágenes y `image_results` llega a `POST
  /messages`.** `RunPipeline._process_source` ahora llama a
  `RagService.index_image_source` (no `index_source`) para fuentes
  `IMAGEN_NATIVA` -- antes indexaba 0 fragmentos en silencio.
  `SimulateConversation` gana `SimulationTrace.image_results` (tercer
  canal, nunca fusionado con `search_results`/`structured_result`,
  poblado solo cuando la acción final es RESPONDER y
  `RagService.has_image_search`), expuesto en HTTP como
  `MessageResponse.image_results`/`ImageResultSnippet`
  (`interfaces/api/schemas.py`) y también renderizado en el Simulador
  de escritorio por consistencia. Verificación de punta a punta contra
  la base de datos real encontró dos problemas no detectados por las
  pruebas con dobles en memoria: `interfaces/api/runtime_context.py`
  nunca conectaba ningún `image_embedding_provider` (corregido con un
  `image_embedding_provider_factory` inyectable, mismo patrón que
  `embedding_provider_factory`, más un atajo en
  `SemanticSearchImages.execute()` que evita cargar el modelo real de
  CLIP cuando el proyecto no tiene ninguna imagen indexada), y
  `Chunk.image_relative_path` nunca se persistía en `project.db`
  (defecto real de la Ronda 65, corregido con la migración Alembic
  `0020_chunk_image_relative_path.py` -- consultado y aprobado
  explícitamente por el consultor como corrección de bug, no como
  parte del trabajo de migraciones reservado a la Fase 5). `ruff check
  .` sin hallazgos, `mypy` sin cambios (22 de siempre), 769 pruebas
  unitarias (+8) + 15 de `tests/smoke` + 373 de `tests/integration`
  (+17) en verde, incluidas migraciones Alembic reales. Queda pendiente
  solo la Fase 5 de RAG 3 (migraciones/documentación) antes de que
  pueda iniciar la Fase 1 de RAG 4 (benchmark), por instrucción
  explícita del consultor. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 68, puntos 233-236.

- **2026-08-21 -- Ronda 67: RAG 3 Fase 4 implementada -- UI de alta y
  revisión de fuentes de imagen.** Se verificó primero, con evidencia
  de código, que la Fase 4 (UI de escritorio) es independiente de los
  dos vacíos dejados en la Ronda 66 -- confirmado antes de programar.
  Se encontró que buena parte de la Fase 4 ya funcionaba sin cambios:
  `SOURCE_TYPE_OPTIONS` ya incluye `imagen_nativa` (se genera del
  Enum), `RegisterSource` ya copia el archivo a `sources/original/`
  para este tipo, y la tabla de Fuentes ya muestra el tipo entre
  corchetes. Lo que faltaba: `_RegisterSourceDialog`
  (`ui/sources/panel.py`) gana una vista previa en miniatura y un
  filtro de archivo a extensiones de imagen cuando el tipo es Imagen
  (lógica sin Qt extraída a `ui/sources/image_source_logic.py`, mismo
  patrón que `ui/conversational/parsing.py`); "Indexar esta fuente"
  (`ui/ingestion/panel.py`) ahora reconoce `IMAGEN_NATIVA` y llama a
  `index_image_source` en vez de `index_source` (decisión en
  `ui/ingestion/index_logic.py`) -- antes indexaba 0 fragmentos en
  silencio para este tipo. Se corrigió además un gap real: la lista de
  fragmentos no se refrescaba tras indexar una imagen (el Chunk se
  crea dentro de IndexImageSource, no en "Fragmentar"). Sin pestaña ni
  ícono nuevo, siguiendo la propia corrección de alcance del diseño
  original (sección 3.6). `ruff check .` sin hallazgos, `mypy` sin
  cambios (22 de siempre), 9 pruebas nuevas sin Qt, 761 pruebas
  unitarias + 15 de `tests/smoke` + 356 de `tests/integration` en
  verde. La ventana real no se pudo instanciar en este entorno (falta
  `libEGL`) -- nuevos pasos en `checklist_validacion_visual.md`. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 67, puntos 227-232.

- **2026-08-21 -- Ronda 66: RAG 3 Fase 3 implementada --
  IndexImageSource, SemanticSearchImages y colección de imágenes.**
  Cierra el ciclo indexar→buscar de la multimodalidad nativa. Se
  promovió el parámetro `collection` del adaptador concreto
  `QdrantLocalVectorStore` al propio puerto `VectorStore`
  (`domain/rag/ports.py`), con nuevas constantes de dominio
  `DEFAULT_COLLECTION_NAME`/`IMAGE_COLLECTION_NAME`
  (`domain/rag/entities.py`) -- necesario para que `application` no
  dependa de `infrastructure` (ADR-001). Se agregó `embed_query_text`
  al puerto `ImageEmbeddingProvider` (por defecto `NotImplementedError`,
  igual criterio que `EmbeddingProvider.embed_query`), implementado en
  `FastEmbedImageProvider` con un segundo modelo pareado
  (`Qdrant/clip-ViT-B-32-text`, mismo espacio semántico que el modelo de
  visión de la Fase 1). Nuevos `IndexImageSource`
  (`application/rag/commands/`) y `SemanticSearchImages`
  (`application/rag/queries/`), hermanos de `IndexSource`/
  `SemanticSearch` pero para imágenes -- `IndexImageSource` lee el
  `Source` directamente (decisión de la Ronda 65) y construye él mismo
  el `Chunk` tipo `IMAGEN`. `RagService` gana `index_image_source()`/
  `search_images()`/`has_image_search` (capacidad opcional, requiere
  `image_embedding_provider`, y `index_image_source()` además
  `source_repository`); `app/bootstrap.py` ya construye siempre un
  `FastEmbedImageProvider` (carga perezosa, sin costo hasta la primera
  fuente de imagen real). Quedan dos vacíos documentados
  explícitamente, no descuidos: el campo `image_results` de
  `POST /messages` y la integración con `RunPipeline` (el pipeline
  automático no rompe con fuentes `IMAGEN_NATIVA`, pero tampoco las
  indexa todavía). `ruff check .` sin hallazgos, `mypy` sin errores
  nuevos (mismos 22 de siempre), 751 pruebas unitarias (+17) + 15 de
  `tests/smoke` + las 356 de `tests/integration` (7 lotes) en verde.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 66, puntos
  222-226.

- **2026-08-21 -- Ronda 65: RAG 3 Fase 2 implementada --
  SourceType.IMAGEN_NATIVA, ChunkType.IMAGEN y extractor trivial.**
  Continuación de RAG 3 en paralelo a la decisión de RAG 4 (Ronda 64).
  Se agregó `SourceType.IMAGEN_NATIVA` (distinto de `IMAGEN_ESCANEADA`,
  documentado en el propio código) y `ChunkType.IMAGEN` (mismo
  criterio de reutilizar el Enum que ENCABEZADO/PADRE/ESTRUCTURADO).
  Se descubrió, al implementar, un gap real del diseño de la Ronda 61:
  tanto `ExtractSourceText` (`EmptyExtractionError`) como el validador
  de `Chunk` rechazaban texto vacío incondicionalmente -- sin
  corregirlo, el extractor trivial habría sido inservible. Se
  corrigió: `ExtractSourceText` reconoce explícitamente
  `IMAGEN_NATIVA` como caso válido, y el validador de `Chunk` se
  convirtió en un `model_validator` que exime solo a `ChunkType.IMAGEN`
  (se agregó también `Chunk.image_relative_path`). Nuevo
  `ImageNativeExtractor` (`infrastructure/extraction/`), registrado en
  `CompositeTextExtractor`. Se decidió explícitamente NO producir el
  `Chunk` real en esta fase (eso requiere que `FragmentSource` conozca
  el `Source` original, algo que no encaja sin una inyección de
  dependencia más invasiva) -- queda para la Fase 3
  (`IndexImageSource`), tal como ya lo describía el diseño de la Ronda
  61. `ruff check .` sin hallazgos, `mypy` sin errores nuevos, 734
  pruebas unitarias (+5) + 15 de `tests/smoke` + todo
  `tests/integration` en verde. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 65, puntos 218-221.

- **2026-08-21 -- Ronda 64: RAG 4, decisión revisada del consultor --
  excepción arquitectónica controlada + plan de benchmark.** El
  consultor presentó un análisis propio (verificado por esta
  consultoría contra la documentación oficial de Azure AI Search y
  AWS Bedrock antes de aceptar sus citas) que revisa la conclusión de
  la Ronda 62. Nuevo documento:
  `docs proyecto/RAG_STUDIO_Decision_RAG4_Excepcion_Controlada.docx`
  (+ `.pdf`, 6 páginas). Decisión: excepción controlada, no
  eliminación del límite -- el núcleo determinista sigue siendo
  obligatorio por defecto, RAG STUDIO sigue sin generar la respuesta
  final en ningún modo. Se adopta una política de tres modos
  (DETERMINISTIC/AGENTIC/ADAPTIVE), "Shadow Retrieval" (control
  determinista en paralelo, con muestreo en producción), separación
  de seguridad planificador-propone/RAG-STUDIO-valida con esquema
  cerrado, y una huella de ejecución obligatoria desde el primer
  prototipo (no opcional). No se autoriza construir las 5 fases de la
  Ronda 62 todavía: se exige antes una Fase -1 de benchmark A/B
  (200-500 preguntas, 12-18 días) que acredite mejora material antes
  de formalizar el ADR-004. La idea de "Base de Conocimiento RAG
  Certificada" (LLM para certificación offline de la base) queda
  señalada como línea de trabajo aparte, fuera de esta decisión.
  Ronda de documentación y decisión estratégica: ningún código de
  producción cambió. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 64, puntos 213-217.

- **2026-08-21 -- Ronda 63: RAG 3 Fase 1 implementada -- puerto de
  embeddings de imagen + segunda colección en Qdrant.** Primera pieza
  de construcción real del diseño de la Ronda 61, elegida por ser la
  única de las tres líneas pendientes (RAG 3/RAG 4/RAG 5 restante) sin
  ninguna decisión estratégica o dato real bloqueante. Nuevo puerto
  `ImageEmbeddingProvider` (`domain/rag/ports.py`, mismo estilo que
  `EmbeddingProvider`/`Reranker`). Nuevo adaptador
  `FastEmbedImageProvider` (`infrastructure/embeddings/`) sobre
  `fastembed.ImageEmbedding`, modelo por defecto `Qdrant/clip-ViT-B-
  32-vision` (512 dim, ~0.34 GB) -- elegido por ser CLIP (comparte
  espacio semántico con un modelo de texto hermano, necesario para
  buscar imágenes desde una consulta en lenguaje natural en la Fase
  3). `QdrantLocalVectorStore` gana un parámetro `collection` en sus 5
  métodos (valor por defecto = comportamiento actual sin cambios),
  permitiendo una segunda colección aislada (`chunks_imagenes`) con
  dimensión distinta dentro del mismo directorio de proyecto. Nada de
  esto está conectado todavía a ingestión o búsqueda real -- es
  infraestructura preparada, tal como lo dimensionó la Fase 1 del
  diseño. `ruff check .` sin hallazgos, `mypy` sin errores nuevos, 729
  pruebas unitarias + 15 de `tests/smoke` + todo `tests/integration`
  (incluidas pruebas nuevas) en verde. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 63, puntos 209-212.

- **2026-08-21 -- Ronda 62: análisis costo/beneficio de reabrir el
  límite de RAG 4 ("nunca un LLM interno").** Tercera y última
  pregunta del roadmap de la Ronda 59 ("Quiero explorar reabrirlo").
  Documento estratégico, sin recomendación de dirección:
  `docs proyecto/RAG_STUDIO_Analisis_CostoBeneficio_RAG4_LLM.docx`
  (+ `.pdf`, 4 páginas). Reafirma con cita exacta que el límite no es
  texto literal de ningún ADR (el ADR-001 sección 8 no menciona LLM)
  sino una instrucción explícita del consultor formalizada al redactar
  el ADR-003 -- de ahí que sea el consultor quien tenga la autoridad de
  reabrirlo. Inventaría con precisión lo que RAG STUDIO ya resuelve sin
  LLM (expansión de contexto, búsqueda híbrida + reranking, consultas
  estructuradas, enrutamiento multi-índice determinista -- "RAG 4 sin
  agente") para no sobrestimar el beneficio de la opción agéntica.
  Pesa qué se cede (determinismo/auditabilidad -- la ventaja
  competitiva ya documentada en `RAG_STUDIO_Ventaja_Competitiva_y_
  Roadmap_RAG3-5.docx`; costo, latencia, riesgo de alucinación e
  inyección de instrucciones) contra qué se gana (descomposición real
  de consultas, multi-hop verdadero, diferenciación comercial). Deja
  una propuesta de diseño acotada condicional (puerto `LLMProvider`
  mirando `EmbeddingProvider`/`Reranker`, activable solo por bandera de
  proyecto, nunca reemplaza el modo determinista por defecto; 21-31
  días hábiles en 6 fases, empezando por un ADR-004). Ronda de
  documentación y análisis puro: ningún código de producción cambió.
  Con esta ronda, las tres preguntas del roadmap de la Ronda 59 quedan
  atendidas. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 62,
  puntos 206-208.

- **2026-08-21 -- Ronda 61: diseño técnico ejecutable de multimodalidad
  nativa (RAG 3), entregado.** Segunda pregunta del roadmap de la Ronda
  59 ("Sí, procede ahora"). Documento de planeación (sin código):
  `docs proyecto/RAG_STUDIO_Diseno_Ejecutable_RAG3_Multimodalidad.docx`
  (+ `.pdf`, 5 páginas). Confirma la Opción A de la Ronda 36 (modelo
  `ImageEmbedding` de `fastembed`, segunda colección de Qdrant por
  proyecto) y suma dos hallazgos de arquitectura no vistos en esa ronda:
  `SourceFileStore` ya resuelve cómo llegarían las imágenes a RAG
  STUDIO (tratarlas como un `Source` más), y `QdrantLocalVectorStore`
  ya aísla cada proyecto en su propio `QdrantClient`, así que una
  segunda colección con nombre es trivial de agregar. Reutiliza los
  precedentes ya confirmados por el consultor: `ChunkType.IMAGEN` en
  vez de un campo paralelo, y `image_results` como lista separada (sin
  fusión RRF) en vez de `sources`. Estimación: 19-28 días hábiles en 5
  fases. Queda, a propósito, sin resolver la pregunta de negocio (caso
  de uso real) -- el documento resuelve el "cómo", no el "si". También
  se corrigió una referencia cruzada obsoleta detectada por
  autorevisión: la nota del Manual del Usuario (10.4) citaba
  `CONTRATO_INTEGRACION.md, sección 14`, desactualizada tras la
  corrección de ubicación de la Ronda 60 -- ahora dice correctamente
  "sección 10". Ronda de documentación y diseño puro: ningún código de
  producción cambió. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 61, puntos 204-205.

- **2026-08-21 -- Ronda 60: implementados los dos "quick wins" del
  roadmap de la Ronda 59.** El consultor confirmó avanzar con los tres
  puntos abiertos del roadmap anterior; esta ronda cubre el primero.
  Nuevo endpoint `GET /projects/{id}/quality` (mismo patrón que
  `/metrics`, Ronda 32): protegido solo por `X-API-Key`, expone
  Recall@3/MRR/veredicto/estado de la compuerta "Regresión de
  recuperación" de la corrida "completa" más reciente, sin instanciar
  `EvaluateReleaseGates` -- solo `SqlAlchemyEvaluationRunRepository`,
  `ListCompleteEvaluationRuns` y la función pura `relative_drop`, mismas
  piezas que ya usa esa compuerta, sin duplicar su lógica.
  `QualityResponse` (nuevo, `interfaces/api/schemas.py`) usa
  `Project.quality_regression_threshold` si el proyecto configuró uno
  propio. Documentado en `CONTRATO_INTEGRACION.md` (secciones 9 y 10,
  esta última formaliza el flujo de "ambiente de pruebas
  pre-liberación" ya verificado en la Ronda 59) y con dos notas nuevas
  en el Manual del Usuario (10.4 y antes del capítulo 11). Corrección
  durante la implementación: el primer borrador de la documentación se
  agregó por error a `GUIA_DESPLIEGUE.md` (el archivo del operador) en
  vez de `CONTRATO_INTEGRACION.md` (el del agente externo) -- lo
  detectó de inmediato la prueba de integración que verifica el
  contenido de ese archivo, no una revisión manual. 8 pruebas nuevas en
  `test_runtime_api.py` + 2 aserciones nuevas en
  `test_deployment_package_end_to_end.py`, todas en verde; `ruff check
  .` sin hallazgos; suite completa (744 unitarias + smoke, 431 de
  integración por lotes) sin regresiones. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 60, puntos 202-203.

- **2026-08-21 -- Ronda 59: roadmap de preparación RAG 3-5 ("no
  empezar de cero") y el agente externo de pruebas de NEXOM.** El
  consultor explicó que NEXOM va a ofrecer servicios de creación de
  agentes conversacionales a clientes y necesita que RAG STUDIO esté
  preparado -- sin volumen real de proyectos todavía -- para responder
  rápido cuando uno lo exija, y anunció que NEXOM operará un agente
  externo de pruebas (entorno web local) que consumirá los artefactos
  de RAG STUDIO antes de liberar un proyecto, para una "doble
  validación de calidad" con su propio tablero. Investigación dedicada
  contra el código real: el flujo que ese agente de pruebas necesita
  (publicar instantánea + emitir token de widget + consultar
  `/messages`, todo antes de la liberación formal) **ya existe hoy**,
  sin ningún cambio de código -- `PublishProjectSnapshot` es
  deliberadamente independiente de `RequestRelease`, ningún endpoint
  revisa `ProjectStatus`, y el ciclo de vida ya tiene un estado
  `EN_PRUEBAS` pensado exactamente para esto. Lo que sí falta -- y
  ahora tiene un consumidor externo real y confirmado, la condición
  que faltaba desde la Ronda 57 -- es exponer Recall@3/MRR/estado de
  la compuerta por HTTP; se recomienda un nuevo `GET
  /projects/{id}/quality` (mismo patrón que `/metrics`), sin
  implementarlo todavía por tratarse de una superficie nueva. Se
  documentó explícitamente, antes de que se materializara, que el
  tráfico de pruebas pre-liberación de NEXOM no debe mezclarse con los
  criterios de reapertura de la Ronda 45 (pensados para tráfico real
  de producción) -- sí puede usarse para calibración previa al
  lanzamiento con el benchmark del reranker (Ronda 36). RAG 3
  (multimodalidad): se confirmó que el hueco real es un documento de
  diseño técnico ejecutable que nunca se escribió -- ofrecido como
  siguiente paso. RAG 4 (recuperación agéntica): se corrigió un
  posible malentendido -- no es un hueco técnico preparable, es un
  límite estratégico dado por instrucción explícita y reafirmada del
  propio consultor en múltiples rondas (no, como se creía, un texto
  literal de ADR-001 sección 8, que en realidad no menciona LLM); se
  descartó también que ampliar la jerarquía de chunks (`parent_chunk_
  id`) mueva el porcentaje de RAG 4, porque su definición operativa
  exige un LLM planificador por diseño de este mismo proyecto. Ronda
  de documentación e investigación pura -- ningún archivo de código
  cambió. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 59,
  puntos 198-201, y el nuevo documento `docs proyecto/RAG_STUDIO_
  Roadmap_Preparacion_RAG3-5.docx` (+ `.pdf`, 6 páginas).

- **2026-08-20 -- Nuevo entregable: "Ventaja competitiva y roadmap RAG
  3-5" (.docx + .pdf).** A pedido del consultor, se formalizó en
  `docs proyecto/RAG_STUDIO_Ventaja_Competitiva_y_Roadmap_RAG3-5.docx`
  (+ `.pdf`, 5 páginas) el análisis honesto de ventaja competitiva ya
  entregado en chat -- fortalezas genuinas, límites honestos y la
  salvedad de que sigue siendo evidencia de ingeniería, no de
  producción, mientras "AGENTE UDL" no tenga tráfico real -- junto con
  las condiciones concretas de activación para RAG 3-5 (tabla por
  componente de RAG 5, y explicación de por qué RAG 3/RAG 4 no tienen
  condiciones sino límites de diseño ya decididos). Antes de redactarlo
  se ejecutó la Ronda 58 (ver arriba), precisamente para que el
  documento describiera un hueco menos.

- **2026-08-20 -- Ronda 58: antes del documento de ventaja competitiva,
  búsqueda de huecos accionables en RAG 3-5, y cierre de uno real
  (`section_title` en el contrato HTTP).** El consultor pidió un
  documento (.docx + .pdf) con el análisis de ventaja competitiva ya
  entregado en chat, más las condiciones para llevar RAG 3-5 al 100%, y
  autorizó explícitamente implementar ahora mismo cualquier mejora real
  que se encontrara antes de redactarlo. Investigación dedicada contra
  el código y contra toda la documentación de rondas anteriores: RAG
  3/4 sin hueco (límites de diseño permanentes, no atraso); Versionado,
  Evaluación continua, Observabilidad, Aprendizaje del retrieval y
  Políticas sin hueco libre (o cerrados por decisión ya tomada, o
  bloqueados por falta de tráfico real, o ya cerrados como límite
  aceptado); Procedencia/temporalidad sí tenía uno real: `Chunk.
  section_title` existe desde la Pista B.1 del ADR-003 y ya viajaba por
  HTTP en `StructuredResultRow`, pero nunca se agregó a `SourceSnippet`
  (los resultados de la búsqueda semántica normal, la mayoría del
  tráfico real) -- el propio `CONTRATO_INTEGRACION.md` lo confesaba
  desde la Ronda 44 como "punto de mejora a discutir", sin que ninguna
  ronda lo cerrara. Implementado: `interfaces/api/schemas.py`
  (`SourceSnippet.section_title` + `MessageResponse.
  from_handled_message`), `export_deployment_package.py` (contrato
  actualizado), pruebas extendidas en `test_runtime_api.py` y
  `test_deployment_package_end_to_end.py` en vez de crear pruebas
  paralelas. Procedencia/temporalidad sube de ~85% a ~90%; promedio de
  RAG 5 de ~67-68% a ~68-69%. `ruff check .` sin hallazgos; suite
  completa (744 unitarias + smoke, 391 de integración, ejecutada por
  lotes por una limitación del entorno de esta sesión) en verde. No se
  tocó el proyecto real "AGENTE UDL". Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 58, puntos 196-197.

- **2026-08-20 -- Ronda 57: síntesis honesta de % RAG1-5 tras B'+C, y
  auditoría dedicada del Manual del Usuario (7 omisiones + 2 hallazgos
  colaterales, corregidos).** El consultor pidió el porcentaje real de
  cada nivel RAG1-5 y que se validara el Manual del Usuario contra el
  estado real de la aplicación. RAG 1/2 en 100%; RAG 3/4 al tope de lo
  que se decidió perseguir (75%/50% del modelo original, 100% del
  alcance elegido); RAG 5 sube de ~64% a ~67-68% de promedio, con
  "evaluación continua" subiendo de ~55% a ~75% (justificado en código
  real: MRR, compuerta bloqueante con 6 pruebas dedicadas, vista de
  tendencia) -- el resto de RAG 5 permanece sin cambios, confirmado
  negativamente por grep, no inflado por actividad de código en otras
  áreas. Auditoría del Manual del Usuario (622 párrafos,
  `RAG_STUDIO_Manual_de_Usuario.docx`, raíz del repo): 4 funcionalidades
  reales (Rondas 53/56) sin documentar -- Recall@3/MRR, umbral de
  regresión configurable, compuerta "Regresión de recuperación", botón
  de tendencia, botón de criterios de reapertura -- y un hallazgo
  colateral más serio: el manual afirmaba "seis verificaciones/
  compuertas" en tres párrafos distintos (10.1, 10.2, 17.5),
  desactualizado desde que la Ronda 53 agregó la séptima. Todo
  corregido, más dos entradas nuevas de glosario (Recall@3, MRR) y una
  nota menor sobre el rango de páginas visible en la lista de
  fragmentos. Corrección técnica encontrada al implementar:
  `insert_paragraph_before()` de python-docx no copia el espaciado del
  párrafo ancla -- corregido fijándolo a mano, verificado visualmente
  contra el PDF renderizado. Ningún cambio de código en esta ronda --
  es documentación pura. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 57, puntos 194-195.

- **2026-08-20 -- Ronda 56: corrección del ADR-003 tras B'+C, y
  chequeo automático de los criterios de reapertura de la Ronda 45.**
  El consultor preguntó qué sigue para subir el nivel de madurez RAG
  tras las Rondas 53-55. Diagnóstico: RAG 3 y RAG 4 ya están al tope de
  lo que se decidió perseguir (límites de diseño permanentes) -- toda
  la palanca real está en RAG 5. Se corrigió `RAG_STUDIO_ADR-003_
  Evolucion_Capa_Canonica.docx` (nota de actualización, mismo patrón ya
  usado en Rondas 29/36/41/42/44/50): la celda "Evaluación continua"
  seguía sin mencionar MRR/compuerta de regresión/tendencia (Ronda 53).
  Se investigó, y se descartó con razón concreta, enriquecer el
  veredicto por caso individual (verde/amarillo/rojo) con
  `expected_source_rank`: es una decisión ya deliberada por escrito en
  la Pista A.1 (ADR-003) -- mantener el criterio binario del documento
  maestro y dejar rank/MRR como capa cuantitativa aparte -- sin
  ninguna razón nueva que la invalide. En cambio, se automatizó lo que
  hasta ahora exigía una consulta SQL manual cada ronda (Rondas
  43/45/50): si ya se cumplen los criterios de reapertura de alertas
  proactivas y aprendizaje del retrieval (Opción 3). Nuevos:
  `domain.runtime.entities.ReopeningCriteriaStatus`,
  `application.runtime.queries.evaluate_reopening_criteria.
  EvaluateReopeningCriteria`, `RuntimeMonitoringService.
  evaluate_reopening_criteria()`, y un botón "Criterios de reapertura
  (Ronda 45)…" en el panel de Monitoreo. Ninguno de los dos pendientes
  cumple sus condiciones todavía (correctamente diferidos por falta de
  datos reales) -- ya no hace falta SQL manual para saberlo. `ruff`
  sin hallazgos; 729 pruebas unitarias en verde (10 nuevas);
  `tests/smoke` en verde (confirma que el reordenamiento de
  `bootstrap.py` no rompe el arranque real); 77 pruebas de integración
  dirigidas en verde. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 56, puntos 191-193.

- **2026-08-20 -- Ronda 55: segundo fallo real, más profundo que la
  Ronda 54 -- `SqlAlchemyProjectRepository.get()` nunca llamaba a
  `ensure_project_db()`.** El consultor reinició la aplicación real
  (confirmado por timestamps de log: "Iniciando RAG STUDIO" ->
  "Bootstrap completo" -> caída inmediata) esperando que la corrección
  de la Ronda 54 resolviera el error, y obtuvo el **mismo** `sqlite3.
  OperationalError: no such column: project.quality_regression_
  threshold`. La corrección de la Ronda 54 era real y necesaria, pero
  insuficiente: el camino de la caída (`ProjectsPanel.__init__` ->
  `_refresh_projects()` -> `project_service.list_projects()` -> `list()`
  -> `get()`) pasa por `SqlAlchemyProjectRepository.get()`, que --a
  diferencia de `save()` y de `SqlAlchemyConfigurationRepository`--
  nunca llamó a `ensure_project_db()` en absoluto: comprobaba
  `db_path.exists()` y abría una sesión directa contra el archivo, sin
  pasar por Alembic. Un bug preexistente desde que se escribió el
  método, distinto y más fundamental que el de caché de la Ronda 54 --
  ningún reinicio de la aplicación, con o sin la corrección de la Ronda
  54, hubiera aplicado las migraciones 0017-0019 al listar proyectos
  existentes, porque `get()` jamás invocaba el mecanismo que las
  aplica. Corrección: `get()` ahora llama a `ensure_project_db()` justo
  después de comprobar que el archivo existe (la comprobación de
  existencia se mantiene ANTES, a propósito: `ensure_project_db()` crea
  el archivo si no existe, y `get()` sobre un `project_id` inexistente
  debe seguir devolviendo `None`, no crear un `project.db` vacío como
  efecto secundario). Se aprovechó la corrección para unificar `save()`
  y `get()` sobre el helper `_project_session_factory()` (ya existía,
  pero estaba sin usar) -- un solo punto de paso, en vez de que cada
  método repita su propia llamada a `ensure_project_db()`, para que
  esta clase de error no se repita. Una auditoría dedicada (subagente)
  de todo `infrastructure/database/` confirmó que ningún otro
  repositorio tiene este mismo patrón de bug: todos los demás pasan
  correctamente por su `_session_factory`/`_session_factory_for`.
  Nueva prueba de regresión que reproduce el escenario exacto: un
  `project.db` estampado en la revisión 0016 (antes de la migración
  0019) con una fila real insertada por SQL crudo, abierto por primera
  vez con una caché vacía para esa ruta -- exactamente lo que ocurre al
  reiniciar la aplicación real. `ruff` sin hallazgos; suite completa
  (719 pruebas unitarias + más de 340 de integración, incluidas las de
  modelos de embeddings/reranker/Qdrant reales) en verde. No se tocó el
  archivo real de AGENTE UDL. Ver `Validacion_observaciones_RAG_STUDIO.
  md`, Ronda 55, puntos 187-190.

- **2026-08-20 -- Ronda 54: fallo real reportado por el consultor --
  la caché de `ensure_project_db` no detectaba migraciones nuevas en
  un proceso largo ya abierto.** El consultor reportó `sqlite3.
  OperationalError: no such column: project.quality_regression_
  threshold` al correr la aplicación real. Verificado por lectura de
  solo consulta (`mode=ro&immutable=1`, sin ningún riesgo) contra el
  `project.db` real de AGENTE UDL: `alembic_version = "0016"` -- ni
  siquiera la migración 0017 (Ronda 51) se había aplicado. Causa: RAG
  STUDIO es una aplicación de escritorio de proceso largo, no un
  servidor que se reinicia con cada despliegue -- la caché de
  `ensure_project_db()` (Ronda 51) indexaba solo por ruta, así que un
  proceso que ya llevaba abierto desde antes de que se agregaran las
  migraciones 0017-0019 nunca las volvió a verificar. Exactamente el
  escenario que la Ronda 51 declaraba, de buena fe pero
  equivocadamente, "no reachable hoy". Corrección: `_ensured_
  project_dbs` ahora indexa por `(ruta, head_actual_del_código)` --
  `_project_migrations_head()` relee el head de los archivos de
  migración en disco en cada llamada (barato, sin tocar SQLite ni el
  lock de Alembic); si el head cambió desde la última confirmación de
  esa ruta, se vuelve a verificar de verdad, sin que nadie tenga que
  llamar a `forget_ensured_project_db()`. No se tocó el archivo real
  de AGENTE UDL (aunque se verificó que las tres migraciones
  pendientes son seguras de aplicar: 0 filas en `test_case` y en
  `evaluation_result_item`) -- recibirá las migraciones automáticamente
  la próxima vez que el consultor reinicie la aplicación. Nueva prueba
  que reproduce el escenario exacto sin usar `forget_ensured_
  project_db()`. `ruff` sin hallazgos, 719 pruebas unitarias en verde,
  `test_alembic_migrations.py` con 14 pruebas (1 nueva) en verde. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 54, puntos 183-186.

- **2026-08-20 -- Ronda 53: evaluación continua reforzada -- MRR,
  comparación de regresión y compuerta bloqueante "Regresión de
  recuperación" (opciones B'+C confirmadas por el consultor).** Cierra
  la última línea pendiente de las cuatro elegidas tras la Ronda 50.
  Ante la pregunta directa de cuál opción realmente eleva la calidad
  del producto liberado, el consultor confirmó B'+C (A queda incluida
  como base de B). Al diseñar la comparación se detectó y corrigió un
  prerrequisito real: `EvaluationResultItemRecord` nunca tuvo columnas
  para `retrieval_check_applicable`/`expected_source_rank` -- cualquier
  corrida releída de BD perdía ambos campos y `recall_at_k()` volvía
  `None` sin razón real (migración 0018). `EvaluationRun` gana
  `mean_reciprocal_rank()` (opción A). `Project` gana
  `quality_regression_threshold` (`Optional[float]`, migración 0019,
  `UpdateQualityRegressionThreshold` como caso de uso separado de
  `UpdateProjectDetails`) -- 15% relativo por defecto, configurable por
  proyecto, ambos confirmados por el consultor entre las opciones
  presentadas. `evaluate_release_gates.py` gana
  `_retrieval_regression_gate()`, compuerta nueva e independiente de
  "Calidad" que compara Recall@3/MRR entre las dos corridas "completa"
  más recientes (nueva consulta `ListCompleteEvaluationRuns`, filtrada
  en `application` para no tocar la semántica de `get_last_run()`) y
  bloquea solo ante una caída real -- nunca por falta de datos. `ui/
  quality/panel.py` gana botón de tendencia (últimas 10 corridas
  "completa"), campo de umbral editable, segunda `GateStatusLabel`, y
  un bloque de comparación dentro del reporte de cada corrida. 719
  pruebas unitarias (20 nuevas) en verde, suite de integración completa
  en verde por lotes (incluida `test_project_repository.py`, archivo
  nuevo), `ruff` sin hallazgos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 53, puntos 177-182.

- **2026-08-20 -- Ronda 52: Manual de Usuario actualizado (5 brechas de
  la Ronda 46) y propuesta de diseño de evaluación continua
  reforzada.** Cierra las dos líneas restantes de las cuatro elegidas
  por el consultor tras la Ronda 50. `RAG_STUDIO_Manual_de_Usuario.docx`
  recibe cuatro inserciones fechadas y verificadas contra el código
  real: reranking automático por defecto (149), nueva subsección 7.6
  "Consultar datos estructurados" con filtros y agregaciones (153),
  techo de acceso del token de widget frente a `X-API-Key` (152), y
  nueva subsección 11.5 "Panel de métricas y señal de
  retroalimentación" (150+151). `RAG_STUDIO_Propuesta_Evaluacion_
  Continua_Reforzada.docx` (documento nuevo, sin ningún cambio de
  código) confirma que `recall_at_k` y `regression_count` ya existen
  pero ningún gate de liberación los usa (`_quality_gate()` solo mira
  si hay algún caso en ROJO), que no existe ningún cálculo de MRR
  todavía, y plantea tres opciones progresivas (A: MRR solo
  informativo: B: A + comparación de regresión, opcionalmente como
  nuevo gate bloqueante; C: B + vista histórica) a la espera de que el
  consultor elija una antes de escribir código. Ambos documentos
  renderizados a PDF, verificados visualmente y copiados con checksum.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 52, puntos
  175-176.

- **2026-08-20 -- Ronda 51: corrección de los tres hallazgos de
  robustez operativa de la Ronda 46 (146, 147, 148) y del hallazgo
  menor de la Ronda 48 (162).** Tras la síntesis de la Ronda 50, el
  consultor eligió avanzar con las cuatro vías propuestas; esta ronda
  cubre las tres correcciones de código que no requerían decisión de
  diseño previa. `TestCaseRecord` gana un índice único
  `uq_test_case_code` sobre `(project_id, code)` (migración 0017,
  mismo criterio que `ChannelingSchemeRecord`). `RateLimiter` gana una
  purga oportunista que acota `_hits` a las claves con actividad
  reciente, en vez de crecer para siempre. `ensure_project_db()` gana
  una caché por proceso que evita re-correr el `upgrade_project()`
  completo (bajo el lock global de Alembic) en cada llamada de cada
  repositorio -- la primera llamada de cada `project.db` en la vida
  del proceso sigue verificando de verdad, preservando la garantía
  original. `HandleIncomingMessage.execute()` gana
  `auto_dispatch_channeling` (default `True`, sin cambios para nadie
  más); `interfaces/api/app.py` lo pone en `False` y llama a
  `dispatch_channeling()` por separado, ya fuera de `loaded.lock` --
  antes, los reintentos/espera de un webhook de canalización (hasta
  ~10.5s en el peor caso) bloqueaban sin necesidad a cualquier otro
  visitante de la misma instantánea. 695 pruebas unitarias (5 nuevas)
  en verde, suite de integración completa en verde por lotes
  (incluida una prueba de concurrencia real con hilos que reproduce
  el escenario exacto del hallazgo #146), `ruff` sin hallazgos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 51, puntos 170-174.

- **2026-08-20 -- Ronda 50: síntesis honesta de calidad de artefactos y
  nivel RAG 1-5 en porcentaje, a petición explícita del consultor.**
  Ronda de análisis, sin cambios de código. RAG STUDIO cumple por
  completo RAG 1 y RAG 2 (100% cada uno); alcanza el techo que decidió
  perseguir en RAG 3 (75% del modelo original de 4 componentes,
  multimodalidad nativa descartada por decisión de producto, Ronda 36)
  y en RAG 4 ("sin agente", 50% del modelo original, límite de diseño
  permanente desde ADR-001); RAG 5 avanza sin que ningún componente
  llegue todavía a su forma plena -- estimación de referencia ~60-65%
  (versionado ~90%, procedencia/temporalidad ~85%, evaluación continua
  ~55%, observabilidad ~65%, políticas ~40% cerrado como límite
  aceptado, aprendizaje del retrieval ~50%). Sobre la calidad real de
  los artefactos que llegan a un agente conversacional: sólida cuando
  se respeta la compuerta de validación humana (`only_usable_sources`,
  verificada con 25 documentos reales en la Ronda 48), pero RAG STUDIO
  no evalúa automáticamente la calidad semántica de lo que extrae --
  por diseño, nunca ejecuta un LLM que pueda "juzgar" su propio
  contenido, así que esa calidad depende de disciplina operativa
  (validar antes de dejar pasar una fuente) que el código no puede
  garantizar solo. Se actualizó
  `RAG_STUDIO_ADR-003_Evolucion_Capa_Canonica.docx` con una nota de
  actualización que cierra, con
  evidencia de código re-verificada en esta ronda, los dos huecos que
  la síntesis de la Ronda 41 seguía señalando como abiertos
  (`page_start`/`page_end` en el contrato HTTP, percentiles de
  latencia) -- ambos ya se habían cerrado en la Ronda 44, solo faltaba
  reflejarlo en esa nota. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 50, puntos 167-169.

- **2026-08-20 -- Ronda 49: corrección de los dos hallazgos importantes
  de la Ronda 48 (corrupción por doble exportación + colisión de
  `project_id` al importar).** El consultor confirmó corregir ambos de
  inmediato. `FilesystemProjectPackager.export()` ya excluye su propia
  copia de referencia de `manifest.json` al decidir qué archivos
  empaquetar, así que exportar el mismo proyecto más de una vez ya no
  produce un `.zip` con `manifest.json` duplicado. Nueva excepción de
  dominio `ProjectIdCollisionError`
  (`domain/projects/exceptions.py`): `import_project()` ahora comprueba,
  antes de escribir nada, si el `project_id` de destino ya tiene un
  `project.db` real en disco, y si es así rechaza la importación en vez
  de mezclar archivos en silencio. El parámetro `new_project_id`
  (que ya existía en la capa de infraestructura) se expone ahora también
  en `ImportProject`/`ProjectService.import_project()`, para poder pedir
  explícitamente importar bajo un id nuevo. Dos pruebas de integración
  nuevas reproducen ambos escenarios (doble exportación válida; import
  con colisión rechazado), más una prueba unitaria de que
  `ProjectService` reenvía `new_project_id`. 690 pruebas unitarias (1
  omitida, antes 689) en verde, suite de integración completa en verde
  por lotes, `ruff` sin hallazgos. El hallazgo menor de la Ronda 48
  (`TestCase.code` no único) queda fuera de esta corrección, sigue solo
  documentado. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 49,
  puntos 163-166.

- **2026-08-20 -- Ronda 48: pruebas reales con la carpeta Licenciatura/
  (25 fichas de programas de la Universidad de León).** A petición del
  consultor, se corrió el pipeline real (mismo `app.bootstrap()` de la
  app de escritorio) contra 25 PDF reales, escaneados sin capa de
  texto. Proyecto B (cobertura): 25/25 completaron extracción OCR +
  fragmentación + indexación sin ningún error. Proyecto A (flujo
  funcional, 5 programas): extracción, búsqueda, diseño conversacional,
  Simulador (una vez validadas las fuentes -- `only_usable_sources`
  se fuerza a propósito en el motor conversacional real), banco de
  pruebas, evaluación y compuertas de liberación funcionaron de punta
  a punta. Dos hallazgos importantes, ambos confirmados con
  reproducciones aisladas: (1) exportar el mismo proyecto una segunda
  vez corrompe el paquete -- `manifest.json` queda duplicado dentro
  del .zip porque `export()` deja una copia de referencia en la
  propia carpeta del proyecto, que la siguiente exportación recoge
  como si fuera un archivo más; (2) `ImportProject`/`ProjectService`
  nunca comprueban colisión de `project_id` al importar -- un paquete
  cuyo manifiesto declare el id de un proyecto ya existente mezcla
  sus archivos sin ninguna advertencia. Un hallazgo menor:
  `TestCase.code` no es único por proyecto. Ningún hallazgo se
  implementó todavía. Dos paquetes `.agentproj` de los proyectos de
  prueba (ya re-exportados sin el problema del punto 1) se dejaron en
  `PRUEBAS_RAG_STUDIO_UDL_2026-08-20/` para que el consultor los
  importe si quiere revisarlos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 48, puntos 157-162.

- **2026-08-20 -- Ronda 47: corrección del hallazgo crítico de la
  Ronda 46 (Zip Slip en la importación de paquetes).** El consultor
  confirmó corregirlo de inmediato en vez de esperar al resto de la
  lista. `domain/projects/packaging.py::FileEntry` gana un
  `field_validator` sobre `relative_path` que rechaza rutas absolutas,
  segmentos `..` y separadores `\` -- `verify_integrity()` ahora
  captura el `ValidationError` resultante y lo traduce en un reporte
  inválido en vez de una excepción sin manejar, así que
  `import_project()` (que verifica ese reporte antes de escribir
  nada) rechaza el paquete con `IntegrityViolationError` sin tocar el
  disco. Segunda capa de defensa: `import_project()` también confirma,
  antes de cada escritura, que la ruta resuelta quede dentro de la
  carpeta del proyecto de destino. 13 pruebas unitarias nuevas
  (`tests/unit/domain/test_packaging.py`) + 1 prueba de integración
  nueva que fabrica a mano un `.agentproj` con path traversal y
  confirma que se rechaza sin escribir nada fuera de la instalación.
  `ruff check .` sin hallazgos; 689 pruebas unitarias (1 omitida) +
  suite de integración completa en verde. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 47, puntos 154-156.

- **2026-08-20 -- Ronda 46: auditoría detallada de código y
  validación del manual de usuario.** A petición del consultor, se
  hizo una auditoría de amplio espectro (apoyada en un sub-agente,
  pero con cada hallazgo reverificado personalmente contra el código
  real) más una comparación línea por línea del manual de usuario
  contra el código actual. Código: (1) hallazgo crítico -- Zip Slip
  real en la importación de paquetes `.agentproj`
  (`infrastructure/filesystem/packager.py::import_project` escribe
  `target_dir / entry.relative_path` sin sanitizar, y
  `verify_integrity()` solo comprueba que el manifiesto sea
  autoconsistente, nunca que las rutas sean seguras -- alcanzable
  desde "Importar proyecto"); (2) los reintentos del webhook de
  canalización (Ronda 12) corren dentro del mismo lock de instantánea
  (Ronda 10), así que un destino de webhook lento bloquea a *todos*
  los visitantes del proyecto, no solo a quien canalizó; (3)
  `RateLimiter._hits` (Ronda 11) nunca borra la entrada de una IP
  aunque su ventana quede vacía -- crece sin cota durante la vida del
  proceso; (4) cada llamada a un repositorio abre un `Engine` SQLite
  nuevo y corre una verificación Alembic completa bajo un lock
  global, lo que encarece las importaciones en bloque grandes. Manual:
  no documenta el reranking automático por defecto del Simulador
  (Ronda 40), el panel de métricas de observabilidad ni la captura de
  señal de relevancia del capítulo Monitoreo (ambos con pantalla
  propia, Pistas C.1/C.4a), y tiene dos gaps menores (techo de acceso
  por token/`X-API-Key`, botón "Consultar datos estructurados" sin
  sección propia). Ningún hallazgo se implementó todavía -- quedan
  documentados para que el consultor decida el orden antes de tocar
  código o el manual. `ruff check .` sin hallazgos; 676 pruebas
  unitarias en verde, sin cambios de código en esta ronda. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 46, puntos 145-153.

- **2026-08-20 -- Ronda 45: criterios de reapertura para alertas
  proactivas y aprendizaje del retrieval Opción 3.** El consultor pidió
  analizar qué, de los temas que quedaron diferidos (no cerrados como
  límite conocido) en la Ronda 44, se podía resolver ahora. Verificado
  primero contra el entorno real: `conversation_log` y
  `retrieval_feedback` siguen en 0 filas, y el proyecto real sigue en
  `ProjectStatus.INICIAL` -- ninguna condición de reapertura se cumple
  hoy, así que no hay nada que construir todavía. Lo que sí se resolvió,
  sin código: `RAG_STUDIO_Propuesta_Roadmap_RAG5_Pendientes.docx`
  (v1.1) gana una sección 9 ("Criterios de reapertura") con dos
  umbrales concretos y verificables -- alertas proactivas: transición a
  `ProjectStatus.LIBERADO` + al menos un `WidgetToken` activo + al
  menos 50 turnos de `conversation_log` en 30 días; aprendizaje del
  retrieval Opción 3: al menos 100 entradas de `retrieval_feedback`,
  repartidas en al menos 10 `source_id` distintos, acumuladas en al
  menos 30 días reales. Ambos se documentan como punto de partida
  razonable, no como ley fija -- no obligan a construir nada, solo
  señalan cuándo vale la pena volver a preguntar. Sin cambios de código.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 45, punto 144.

- **2026-08-20 -- Ronda 44: puntos 1-2 del roadmap de RAG 5
  implementados; puntos 3-5 cerrados/diferidos.** El consultor
  confirmó las 4 preguntas del roadmap de la Ronda 43. Punto 1:
  `interfaces/api/schemas.py::SourceSnippet` gana `page_start`/
  `page_end`, poblados desde `Chunk` y documentados en
  `CONTRATO_INTEGRACION.md` (se retiró la frase, ya falsa, de que el
  contrato no tenía número de página). Punto 2: `domain/runtime/
  entities.py::latency_percentile` (función pura) +
  `ConversationMetricsSummary.p95_latency_ms`/`p99_latency_ms`,
  calculados por la implementación SQL real traendo solo la columna
  `latency_ms` (nunca filas completas) -- mismo cálculo que el doble
  de pruebas, mostrados en el panel de Monitoreo y en `GET /metrics`.
  Punto 3 (motor de políticas ampliado): cerrado como límite conocido
  y aceptado en la Tabla 2 del ADR-003, mismo tratamiento que la
  multimodalidad nativa de RAG 3. Puntos 4-5 (alertas proactivas,
  aprendizaje del retrieval Opción 3): diferidos, no cerrados --
  quedan a la espera de necesidad operativa real o de volumen real de
  señal, respectivamente. `ruff check .` sin hallazgos; 676 pruebas
  unitarias (1 omitida) + 297 de integración en verde, 0 fallidas.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 44, puntos
  140-143.

- **2026-08-20 -- Ronda 43: roadmap de los pendientes restantes de
  RAG 5.** Se investigó el estado real de los cinco pendientes que
  quedan de RAG 5 tras la Ronda 41/42 y se produjo un documento de
  roadmap (mismo formato que la Ronda 30): exponer `page_start`/
  `page_end` en el contrato HTTP (chico) y percentiles p95/p99 en
  observabilidad (chico-mediano) se proponen para implementación
  directa, sin documento de diseño aparte; motor de políticas
  ampliado y alertas proactivas (ambos grandes) requieren antes una
  decisión de producto; aprendizaje del retrieval Opción 3 queda al
  final -- confirmado con una consulta directa a `data/runtime.db`
  del proyecto real que la tabla `retrieval_feedback` tiene 0 filas,
  así que es un bloqueo de datos, no de ingeniería. Sin código
  implementado -- termina en 4 preguntas abiertas para el consultor.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 43, puntos
  138-139.

- **2026-08-20 -- Corrección (Ronda 42):** la Ronda 41 afirmó
  incorrectamente que `Chunk` no tiene ningún campo de página (el
  grep usó un patrón equivocado). Verificación repo-completa confirma
  que `page_start`/`page_end` sí existen y están cableados de punta a
  punta para PDF desde antes de la Pista C -- el hueco real es mucho
  más chico: no se exponen en el contrato HTTP. Corregido en la Tabla
  2 del ADR-003 con una nota fechada, sin borrar el diagnóstico
  original.

- **2026-08-20 -- Ronda 41: síntesis del nivel de madurez RAG actual,
  tras cerrar la Pista C completa.** El consultor preguntó en qué
  nivel del modelo RAG 1-RAG 5 (ADR-003, sección 2) se encuentra RAG
  STUDIO. RAG 1 y RAG 2 siguen cumplidos por completo; RAG 3 sigue en
  su techo de 3/4 componentes (multimodalidad nativa descartada por
  decisión de producto, Ronda 36); RAG 4 sigue en su variante "sin
  agente" (límite de diseño permanente). RAG 5 avanzó en 3 de sus 7
  componentes sin alcanzar ninguno en su forma plena: observabilidad
  pasó de débil a básica (C.1 -- métricas + panel, sin percentiles ni
  alertas); procedencia/temporalidad sigue parcial, con celda y
  versión ya cerrados pero sin seguimiento a nivel de página (C.2);
  aprendizaje del retrieval pasó de inexistente a parcial -- señal
  capturada en producción y reranker activo, sin ningún ajuste
  automático todavía (C.4). Políticas es el único componente sin
  cambios. Síntesis: RAG STUDIO no es hoy un producto RAG 5 -- es un
  producto RAG 3 / RAG 4-sin-agente sólido, con RAG 5 en construcción
  activa. Tabla 2 del ADR-003 actualizada (fila RAG 5) con una nota
  fechada que preserva los diagnósticos anteriores (Rondas 29, 36).
  Ronda de síntesis, sin cambios de código. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 41, puntos 135-137.

- **2026-08-20 -- Ronda 40: cierre de C.4 -- medición real de
  latencia, reranker activado por defecto en producción.** El
  consultor corrió `scripts/benchmark_reranker_latency.py` en su
  propia máquina (con acceso real a Hugging Face) contra su proyecto
  real ("AGENTE UDL", que no tenía ningún caso de prueba curado, así
  que se le entregó un `--queries-file` de 10 preguntas reales sobre
  su única fuente indexada). Resultado real: delta de p50 de +90.6 ms
  por consulta (122.9 ms sin reranker → 213.5 ms con reranker real; el
  promedio/máximo de la vía "con reranker" están distorsionados por la
  descarga única del modelo, no recurrente). Con el costo medido y
  bajo, y dado que el reranking con cross-encoder es una técnica ya
  establecida para mejorar el top-k sobre RRF, se decidió activar el
  reranker por defecto en la vía de producción: `simulate_conversation.py`
  ahora pide `rerank=self._rag.has_reranker` a `RagService.search_hybrid`
  (antes nunca lo pedía) -- no es un booleano fijo, así que ninguna
  instalación sin `Reranker` configurado ve ningún cambio; la app de
  escritorio (`app/bootstrap.py`) siempre construye uno, así que esto
  activa el reranking real en todo tráfico de producción sin ningún
  cambio de configuración adicional. Nota de honestidad técnica: el
  proyecto real no tiene evidencia de calidad (recall) propia todavía
  -- la decisión se apoya en el costo medido y en el argumento técnico
  general; el mecanismo de captura de señal (C.4a, Ronda 39) permitirá
  confirmar o revisar esto con evidencia real acumulada. Con esto, C.4
  -- el último de los cuatro temas del roadmap de la Pista C del
  ADR-003 -- queda completamente cerrado. `ruff check .` sin hallazgos;
  671 pruebas unitarias (1 omitida) + 295 de integración en verde, 0
  fallidas. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 40,
  puntos 132-134.

- **2026-08-20 -- Ronda 39: implementación completa de C.4a --
  captura de señal de relevancia.** El consultor reportó un error real
  del script de benchmark (`project_id` obligatorio sin forma de
  descubrirlo), autorizó usar su entorno conectado para corregirlo, y
  respondió las 4 preguntas abiertas de C.4a (confirmó documentar el
  endpoint en el contrato, delegó las otras tres). Corrección:
  `scripts/benchmark_reranker_latency.py` ahora lista los proyectos
  reales si se omite el id, y probado de punta a punta contra el
  proyecto real del consultor ("AGENTE UDL"). Las 3 preguntas
  delegadas se resolvieron con criterio técnico (no arbitrario):
  autorización del endpoint de feedback = misma `_require_message_auth`
  que ya protege `POST /messages`; corrección de una señal ya
  registrada = solo-inserción, mismo criterio que `EvaluationRun`;
  canal operador = solo en el panel de Monitoreo, no en el Laboratorio
  RAG. Implementación completa: `RetrievalFeedbackEntry` (dominio) +
  `RetrievalFeedbackRepository` (SQL, tabla nueva y aditiva); botón
  "Marcar relevancia de fuentes…" en el panel de Monitoreo; endpoint
  nuevo `POST /projects/{id}/messages/{log_id}/feedback` (protegido
  igual que `POST /messages`, acepta `X-API-Key` o `X-Widget-Token`) +
  nueva sección en `CONTRATO_INTEGRACION.md`. La Opción 3 (ajuste
  automático) sigue explícitamente fuera de alcance -- nada de esto
  ajusta RRF ni el reranker por sí solo. `ruff check .` sin hallazgos;
  669 pruebas unitarias (1 omitida) + 314 de integración (10 omitidas)
  en verde, 0 fallidas. Ver `Validacion_observaciones_RAG_STUDIO.md`,
  Ronda 39, puntos 126-131.

- **2026-08-20 -- Ronda 38: respuesta del consultor a C.4 -- señal
  (a+b+c) confirmada, Opción 2 confirmada, benchmark de latencia
  entregado.** El consultor confirmó que las tres señales de
  relevancia (curación humana, señal explícita por turno, señal
  implícita del agente externo) se consideran válidas, y confirmó la
  Opción 2 (capturar la señal, sin ajuste automático) como siguiente
  paso. Sobre la Opción 1 (reranker por defecto), la respuesta fue
  condicional a medir antes su costo real de latencia -- se intentó
  esa medición honestamente y se confirmó que el entorno de
  verificación no puede hacerla (el modelo del reranker nunca se
  descargó aquí y el acceso a Hugging Face sigue bloqueado, verificado
  en vivo con `curl`, no solo por documentación anterior); en vez de
  inventar una cifra, se entregó `scripts/benchmark_reranker_latency.py`
  para que el consultor la mida en su propia máquina, reutilizando las
  consultas ya curadas del banco de pruebas del proyecto. Además se
  produjo `RAG_STUDIO_Propuesta_C4a_Captura_Senal_Relevancia.docx`, el
  diseño técnico de la Opción 2: una entidad `RetrievalFeedbackEntry`
  nueva, un canal operador en el panel de Monitoreo, y un endpoint
  nuevo para el agente conversacional externo que reutiliza el `log_id`
  y `source_id` que `MessageResponse` ya devuelve hoy -- sin necesidad
  de ningún campo nuevo en la respuesta original. La Opción 3 queda
  explícitamente fuera de alcance. Sin código de producción
  implementado todavía -- pendiente de que el consultor resuelva las 4
  preguntas abiertas del nuevo documento. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 38, puntos 123-125.

- **2026-08-20 -- Ronda 37: propuesta de diseño C.4 -- aprendizaje del
  retrieval.** Cuarto y último tema del roadmap. A diferencia de
  C.1/C.2 (diseño puro) y C.3 (decisión pura), el roadmap ya señaló
  que este tema está "bloqueado, sobre todo, por una decisión de
  producto pendiente (qué señal de relevancia es válida)" -- el
  documento (`RAG_STUDIO_Propuesta_C4_Aprendizaje_Retrieval.docx`)
  combina esa decisión con las opciones de alcance que dependen de
  ella. Hallazgos confirmados en el código: la evaluación existente
  (`EvaluationRun.recall_at_k`, banco de pruebas) es un reporte
  manual, no aprendizaje; el reranker cross-encoder real
  (`FastEmbedReranker`) existe desde la Ronda 21 pero sigue apagado
  por defecto en la vía de producción, por una decisión deliberada de
  esa misma ronda, no por descuido; la fusión RRF usa una constante
  fija (60) sin ningún peso configurable; y aunque `ConversationLogEntry`
  ya guarda qué fuentes se mostraron en cada turno real desde la Ronda
  19, ningún mecanismo en todo el repositorio registra si esas fuentes
  fueron relevantes o no. Se corrigió además un matiz: ADR-001 no
  prohíbe un mecanismo adaptativo no generativo, solo la generación de
  lenguaje natural dentro de RAG STUDIO. El documento presenta cuatro
  señales de relevancia candidatas y cuatro opciones de alcance
  (activar el reranker ya existente; capturar una señal sin ajustar
  nada; ajuste automático simple; o posponer la decisión), sin
  recomendar ninguna, y cierra con las preguntas que el consultor
  necesita resolver. Sin código implementado. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 37, puntos 117-122.

- **2026-08-19 -- Ronda 36: cierre de C.3 -- multimodalidad nativa
  aceptada como límite permanente.** El consultor confirmó que hoy no
  existe ningún caso de uso real que necesite buscar por contenido
  visual o sonoro nunca transcrito a texto, y confirmó la Opción B del
  documento de decisión de la Ronda 35: multimodalidad nativa queda
  documentada como límite de diseño permanente y aceptado -- mismo
  tratamiento que ya tiene "RAG 4 pleno" desde la Ronda 29 -- en vez de
  una tarea pendiente. Se actualizó la Tabla 2 de
  `RAG_STUDIO_ADR-003_Evolucion_Capa_Canonica.docx` (fila RAG 3) con
  una nota fechada que preserva el diagnóstico original, y se cerró
  `RAG_STUDIO_Propuesta_C3_Multimodalidad_Nativa.docx` (Estado/Versión
  + nota de cierre), sin tocar el análisis de costo original. Ningún
  cambio de código -- la Opción B es, por definición, no construir
  nada. Con esto, C.3 queda cerrado por completo; queda pendiente el
  cuarto y último tema del roadmap: aprendizaje del retrieval (C.4).
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 36, puntos
  114-116.

- **2026-08-19 -- Ronda 35: documento de decisión C.3 --
  multimodalidad nativa.** Tercer tema del roadmap, pero a diferencia
  de C.1/C.2 este exige primero una decisión de producto (¿se
  justifica el costo?), no un diseño técnico -- así lo señalaba la
  Ronda 30. Hallazgos con cifras reales: `fastembed` (ya dependencia
  del proyecto) incluye `ImageEmbedding` con 5 modelos listos, ninguno
  mayor a 1 GB -- sin necesidad de ninguna dependencia nueva para
  imágenes; la alternativa de página completa (ColPali) sí es cara
  (6.5 GB) y queda descartada por defecto; audio/video no tiene
  ningún modelo local disponible en `fastembed`. Se reconfirmó que
  `QdrantLocalVectorStore` rechaza vectores nombrados, y se identificó
  una alternativa de menor riesgo no documentada antes: una colección
  de Qdrant separada por modalidad. El documento
  (`RAG_STUDIO_Propuesta_C3_Multimodalidad_Nativa.docx`) presenta tres
  opciones (A: imágenes con modelo pequeño + colección separada; B:
  diferir indefinidamente como límite permanente, igual que "RAG 4
  pleno"; C: audio/video, fuera de escenario recomendado) sin
  recomendar ninguna, cerrando con preguntas de producto para el
  consultor. Sin código implementado en esta ronda -- es
  deliberadamente un documento de decisión, no de diseño. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 35, puntos 109-113.

- **2026-08-19 -- Ronda 34: implementación completa de C.2 --
  procedencia/temporalidad.** El consultor respondió las 4 preguntas
  abiertas de la Ronda 33, delegando el criterio de "más valor para
  RAG STUDIO" en dos de ellas. Se implementaron C.2a, C.2b y C.2c
  completas en la misma ronda. Primero, una re-verificación repo-
  completa (pedida explícitamente) confirmó que `Source.version` es
  en verdad inerte -- cero menciones en `application/documents/` y en
  `ui/sources/`. C.2a: `row_index` en `StructuredQueryRow`, y se
  decidió exponerlo también en el contrato HTTP
  (`StructuredResultRow`/`POST /messages`) para que el agente externo
  pueda citar la fila exacta. C.2b: `GetSourceLineage` (camina
  `supersedes_source_id` en ambos sentidos, sin método nuevo en el
  repositorio) + botón "Ver linaje de versiones…" en `ui/sources/
  panel.py` + exportación a CSV (`application/documents/
  lineage_export.py`) -- se decidió agregar la exportación por su
  valor de auditoría documental. C.2c: dos docstrings corregidos
  (`Source.version` documentado como no usado; `ExtractionRecord`
  actualizado sobre su historial real), sin cambio de comportamiento.
  10 pruebas nuevas + 1 aserción sobre una prueba existente, todas en
  verde; `ruff check .` sin hallazgos. C.2 queda cerrado por completo.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 34, puntos
  104-108.

- **2026-08-19 -- Ronda 33: propuesta de diseño C.2 --
  procedencia/temporalidad.** El consultor confirmó avanzar con el
  segundo tema del roadmap de la Ronda 30. Al confirmar el código real
  antes de diseñar se encontró que el alcance real es distinto -- y
  más chico -- del que sugería el roadmap: `Source.version` (int,
  default 1) nunca se incrementa en ningún lugar del código, es un
  campo inerte, no el mecanismo de versionado real; ese mecanismo ya
  es `supersedes_source_id` (una fuente nueva que sustituye a una
  anterior), que ya funciona pero solo se recorre un salto hacia atrás
  desde la UI. También se confirmó que el historial de extracciones
  (`ExtractionRepository.list_history`) ya existe y funciona -- el
  docstring que dice lo contrario está desactualizado. Diseño
  propuesto, sin ninguna migración: `row_index` en
  `StructuredQueryRow` (cadena archivo→hoja→fila→celda completa);
  consulta de linaje de versiones caminando `supersedes_source_id` en
  ambos sentidos; documentar (sin tocar código) que `Source.version`
  no participa de ningún flujo real; corregir el docstring
  desactualizado de `ExtractionRecord`. Sin código implementado --
  pendiente de confirmación sobre 4 preguntas abiertas. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 33, puntos 101-103.

- **2026-08-19 -- Ronda 32: implementación completa de C.1 --
  observabilidad básica.** El consultor confirmó las 4 preguntas
  abiertas de la Ronda 31 (alcance mínimo solo en escritorio; sí al
  endpoint HTTP opcional, sin que bloquee el resto; ventana
  configurable desde esta fase; percentiles pospuestos). Se
  implementaron C.1a, C.1b y C.1c completas en la misma ronda -- las
  tres se pudieron construir sin ningún bloqueo real. C.1a:
  `ConversationMetricsSummary` + `ConversationLogRepository.
  get_metrics_summary` (dominio + repositorio SQL con `func.avg`/
  `func.count`, sin ninguna migración). C.1b:
  `RuntimeMonitoringService.get_metrics_summary` + un resumen nuevo
  con selector de ventana (todo el histórico / 7 / 30 / 90 días) en la
  pestaña de Monitoreo. C.1c: `GET /projects/{id}/metrics` (protegido
  solo por API key, nunca por token de widget, con parámetro `since`
  opcional) -- documentado en `GUIA_DESPLIEGUE.md` (no en
  `CONTRATO_INTEGRACION.md` como se anticipó en la Ronda 31: se
  corrigió la ubicación al confirmar que las capacidades
  administrativas viven en la guía operativa). 13 pruebas nuevas + 2
  aserciones sobre una prueba existente, todas en verde; `ruff check .`
  sin hallazgos en todo el repositorio. C.1 queda cerrado por completo.
  Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 32, puntos
  97-100.

- **2026-08-19 -- Ronda 31: propuesta de diseño C.1 --
  observabilidad básica.** El consultor confirmó proceder en el orden
  del roadmap de la Ronda 30: observabilidad básica es el primer tema
  ("C.1", primer ítem de una nueva Pista C). Al confirmar el código
  real antes de diseñar, se encontró que el trabajo es más chico de lo
  estimado: `ConversationLogEntry.latency_ms`/`action` ya se capturan y
  persisten por cada turno real desde la Ronda 19, solo falta agregar
  esos datos (no existe ningún método de agregación ni en el
  repositorio ni en la UI de Monitoreo) -- sin ninguna columna, tabla
  ni migración nueva. Diseño propuesto: entidad
  `ConversationMetricsSummary` + `get_metrics_summary` (repositorio,
  agregación SQL) + resumen nuevo en la pestaña de Monitoreo; un
  endpoint HTTP de métricas y los percentiles de latencia quedan como
  fases opcionales separadas. Sin código implementado -- pendiente de
  confirmación sobre 4 preguntas abiertas (alcance mínimo, endpoint
  opcional, ventana configurable, percentiles). Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 31, puntos 94-96.

- **2026-08-19 -- Ronda 30: propuesta de roadmap para los
  pendientes de RAG 3/RAG 5.** El consultor pidió avanzar sobre los
  cuatro pendientes de la Ronda 29 (multimodalidad nativa de RAG 3;
  procedencia/temporalidad, observabilidad y aprendizaje del retrieval
  de RAG 5) -- dado que son piezas de tamaño y naturaleza muy
  distintas, se produjo primero un documento de roadmap
  (`RAG_STUDIO_Propuesta_Roadmap_RAG3_RAG5.docx`), mismo criterio ya
  seguido antes de cada pista de la Pista B: investigar el código real
  antes de diseñar, documento antes que código. Multimodalidad nativa
  resultó ser el pendiente más grande (el pipeline de ingestión y el
  vector store asumen texto de punta a punta, sin ningún tipo de chunk
  no textual ni vectores nombrados en Qdrant); procedencia/temporalidad
  y observabilidad son de tamaño mediano y en buena parte extienden
  trabajo ya existente; aprendizaje del retrieval sigue confirmado como
  inexistente y bloqueado, sobre todo, por una decisión de producto aún
  sin responder (qué señal de relevancia contar como válida). Se
  propone el orden observabilidad → procedencia/temporalidad →
  multimodalidad → aprendizaje del retrieval, pendiente de
  confirmación. De paso, se corrigió un párrafo duplicado detectado en
  el punto 87 de la Ronda 29 (nota de RAG CONTENT STUDIO escrita dos
  veces por un error de edición anterior). Sin código implementado. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 30, puntos 91-93.

- **2026-08-19 -- Ronda 29: síntesis del nivel de madurez RAG
  actual, tras cerrar la Pista B completa.** El consultor pidió, en
  base al avance del proyecto, determinar en qué nivel del modelo
  RAG1-RAG5 (ADR-003, Tabla 2) se encuentra RAG STUDIO ahora que B.1,
  B.2, B.3 y B.4 ya están implementadas -- ronda de síntesis, sin
  código nuevo. **RAG 1 y RAG 2:** cumplidos por completo (reranking
  de la Pista A + chunking jerárquico de B.1 cerraron lo que faltaba
  de RAG 2). **RAG 3:** cumplido en 3 de sus 4 componentes -- datos
  estructurados (B.2), recuperación jerárquica (B.1) y control de
  acceso (B.3); solo falta multimodalidad nativa (sigue siendo
  OCR→texto, sin embeddings de imagen/audio/video). **RAG 4:**
  alcanzado en su variante "sin agente" (multi-índice + enrutamiento
  determinista de B.4) -- el techo máximo posible sin incorporar un
  LLM planificador dentro del propio producto, un límite de diseño
  permanente (ADR-001, sección 8), no una tarea pendiente. **RAG 5:**
  sigue mixto, con su componente de evaluación continua ya
  cuantificado (Recall@K, Pista A). Se actualizó la Tabla 2 del propio
  `RAG_STUDIO_ADR-003_Evolucion_Capa_Canonica.docx` fila por fila, con
  una nota fechada que preserva el diagnóstico original en vez de
  borrarlo. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 29,
  puntos 86-90.

- **2026-08-19 -- Ronda 28: implementación de la Pista B.4 del
  ADR-003 (enrutamiento multi-índice determinista).** El consultor
  delegó las 4 preguntas abiertas del documento de diseño de B.4 al
  criterio de quien implementa ("procede con lo que le aporte valor a
  RAG Studio... para llegar a RAG 4 y RAG 5"): se confirmó la Opción B
  (el enrutamiento vive dentro de RAG STUDIO -- `SimulateConversation`
  decide y devuelve un resultado combinado en la misma respuesta de
  `/messages`, en vez de un endpoint HTTP dedicado que solo habría
  resuelto B.2c), `Intent.resolution_mode` reutilizando el motor de
  emparejamiento existente (no un mecanismo separado), y degradación
  automática a vector+BM25 antes de abstenerse (nunca deja una
  intención ESTRUCTURADO peor que si hubiera quedado en SEMANTICO).
  **B.4a/b:** `IntentResolutionMode` (dominio) + `ConversationalVariable.
  structured_column` + enrutamiento/degradación en `SimulateConversation`
  + `MessageResponse.structured_result` (contrato HTTP, campo aditivo).
  **Dos hallazgos reales corregidos durante la propia verificación**
  (ninguno cubierto por las pruebas unitarias con fakes): (1) la capa
  de infraestructura nunca quedó conectada -- `IntentRecord`/
  `ConversationalVariableRecord` no tenían las columnas nuevas ni el
  repositorio SQL las persistía/leía, corregido con la migración
  Alembic 0016 y el cableado en `conversational_repositories.py`; (2)
  `UpdateIntent.execute()` asignaba `resolution_mode` a
  `model_copy(update=...)` sin coaccionar el tipo -- pydantic no valida
  ahí, así que un string plano (lo que manda la UI) dejaba el campo
  como `str` en vez del Enum, rompiendo en silencio todo código que
  esperaba `.value`; corregido coaccionando explícitamente. Ambos se
  detectaron con pruebas de integración reales (SQLite/`TestClient`),
  nunca con las unitarias en memoria. **UI:** combo "Vía de resolución"
  en Intenciones + campo "Columna estructurada ligada" en Variables
  (`ui/conversational/panel.py`). `CONTRATO_INTEGRACION.md` actualizado
  con `structured_result`. Con esto, las cuatro pistas de la Pista B del
  ADR-003 (B.1-B.4) quedan completas. 968 pruebas en verde (0 fallidas,
  12 omitidas por dependencias opcionales), `ruff` sin hallazgos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 28, puntos 82-85.

- **2026-08-19 -- Ronda 27: implementación de la Pista B.3 del
  ADR-003 (control de acceso en tiempo de consulta).** El consultor
  autorizó ("procede con las recomendaciones") implementar en código
  la propuesta de la Ronda 26. **B.3a:** orden total explícito sobre
  `AccessLevel` (`is_within_access_level`, `domain/documents/entities.py`)
  + `WidgetToken.max_access_level: str = "restringido"` (dominio
  `runtime`, independiente del Enum de `documents`) + migración
  aditiva del `runtime.db` (`_ensure_max_access_level_column`, mismo
  patrón que `_ensure_conversation_id_column` de la Ronda 19).
  **Corrección propia frente a la propuesta original:** en vez del
  "default invertido" que la propuesta recomendaba (tokens nuevos en
  `publico`), se verificó que `Source.access_level` por defecto es
  `INTERNO` -- un token nuevo capado a `publico` vería cero resultados
  en cualquier proyecto sin fuentes reclasificadas, una trampa de
  usabilidad real, sobre todo para "Exportar paquete de entrega al
  cliente…". Se corrigió a un único default uniforme: tokens viejos y
  nuevos nacen en `restringido` (sin techo) si se omite el parámetro,
  igual que toda otra capacidad opcional del proyecto. **B.3b:**
  `max_access_level` enhebrado en `SemanticSearch`/`TextSearch`/
  `HybridSearch`/`RagService`, en paralelo a `only_usable_sources`
  (nunca lo reemplaza) + validación contra el Enum real en
  `IssueWidgetToken.execute()` + `POST /projects/{id}/widget-tokens`
  acepta un cuerpo opcional para especificarlo. **B.3c:** corrección
  factual propia frente a los documentos de diseño de B.2 y B.3, que
  afirmaban que `HandleIncomingMessage` nunca llama a `RagService` --
  se confirmó, leyendo el código real, que `SimulateConversation.
  _search_and_filter` sí llama a `RagService.search_hybrid(...)`, así
  que B.3c resultó mucho más simple de lo previsto: solo enhebrar el
  parámetro por una cadena que ya existía, sin ninguna conexión nueva.
  `CONTRATO_INTEGRACION.md`/`GUIA_DESPLIEGUE.md` (paquete de entrega al
  cliente) se actualizaron para documentar el filtrado de `sources` por
  techo de acceso. **Hallazgo serio detectado y corregido durante la
  propia implementación:** al resolver un aviso de Ruff (`B008`) sobre
  `Depends(_require_message_auth)`, envolverlo en
  `Annotated[Optional[AccessLevel], Depends(...)]` (el patrón que Ruff
  mismo sugiere) rompió la autenticación real de `POST /messages` en
  tiempo de ejecución, sin ningún error visible -- causa raíz:
  `interfaces/api/app.py` tiene `from __future__ import annotations`,
  que convierte las anotaciones en texto sin evaluar, y FastAPI no
  puede resolver ese texto contra una función *local* de `create_app`
  (`_require_message_auth` no es una variable del módulo). Se detectó
  gracias a que dos pruebas de integración ya existentes de rondas
  anteriores fallaron de inmediato; sin ellas, este hallazgo pudo haber
  llegado a producción como un endpoint de mensajes efectivamente sin
  autenticación real. Corregido revirtiendo a `Depends(...)` como
  default plano (se evalúa de inmediato, no como anotación de texto) y
  silenciando ese `B008` puntual en `pyproject.toml`
  (`extend-immutable-calls = ["fastapi.Depends"]`), el mecanismo que el
  propio Ruff documenta para este idioma de FastAPI. 955 pruebas en
  verde (0 fallidas, 12 omitidas por dependencias opcionales o modelos
  no descargados en este entorno), `ruff` sin hallazgos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 27, puntos 78-81.

- **2026-08-19 -- Ronda 26: punto 48 de la Ronda 15 resuelto,
  prueba real de acceso a modelos, y propuesta de contrato para B.3.**
  Con B.1 y B.2 cerradas, el consultor pidió resolver los tres
  pendientes que la Ronda 25 había dejado explícitamente fuera de
  alcance. **Punto 48 (campos/estados de `Project`):** al investigar
  antes de implementar se encontró que su premisa original ya no era
  cierta -- la Ronda 15 asumía que la transición a `LIBERADO` "ya
  ocurre por otra vía" (el flujo de liberación), pero
  `RequestRelease.execute()` nunca llama a `transition_to()`; en la
  práctica, la única transición con algún control en la interfaz
  seguía siendo "Archivar". Se corrigió exponiendo el mismo grafo que
  el dominio ya valida (`Project.allowed_next_statuses()`, nuevo) a
  través de dos comandos nuevos que siguen el patrón exacto de
  `UpdateProjectName`/`ArchiveProject` (`UpdateProjectDetails`,
  `ChangeProjectStatus`) y de un formulario completo de alta/edición
  más un control "Cambiar estado…" en `ui/projects/panel.py` -- sin
  inventar ninguna política de negocio nueva, solo haciendo visible la
  que ya existía. **Prueba real de acceso a modelos:** se intentó de
  verdad, con evidencia doble (la suite de integración existente más
  una llamada directa fuera de pytest a la API de Hugging Face), en
  vez de asumir el bloqueo -- se confirmó que sigue bloqueado en este
  entorno para ambos modelos (embeddings y reranker) por un `403
  Forbidden` de un proxy intermedio, sin distinción entre ellos; no
  hay ningún cambio de código pendiente para desbloquearlo, solo
  conexión de red. **Propuesta de contrato para B.3 (control de
  acceso):** documento nuevo,
  `RAG_STUDIO_Propuesta_B3_Control_Acceso.docx`/`.pdf`, que identifica
  que `Source.access_level` ya existe en el esquema desde una ronda
  anterior pero nunca se usa en recuperación, y que propone atar el
  techo de acceso a la credencial (`WidgetToken`/`X-API-Key`, ya
  controlada por quien opera el servicio) en vez del campo
  por-solicitud que sugiere el texto literal del ADR-003 -- un valor
  que el propio agente externo declarara no sería un control de
  acceso real. Sin código de B.3 implementado todavía, a la espera de
  que el consultor confirme las preguntas abiertas del documento. 934
  pruebas en verde (0 fallidas, 12 omitidas por dependencias
  opcionales), `ruff` sin hallazgos. Ver
  `Validacion_observaciones_RAG_STUDIO.md`, Ronda 26, puntos 75-77.

- **2026-08-19 -- Ronda 25: implementación de la Pista B.2 del
  ADR-003 (datos estructurados, B.2a/B.2b).** El consultor autorizó
  proceder con las recomendaciones propias del documento de diseño de
  B.2 para sus 4 preguntas abiertas (mismo criterio que B.1 en la
  Ronda 24). **B.2a:** `TextExtractor` gana un método nuevo y
  **concreto** (no abstracto), `extract_structured_blocks()`, con
  `return {}` por defecto -- decisión de implementación que corrige la
  propuesta original del documento de diseño (extender la tupla de
  `extract()` habría tocado los ~30 sitios de prueba existentes que la
  desempaquetan); solo `XlsxExtractor`/`CsvExtractor` la sobrescriben,
  devolviendo columnas y filas nativas ADEMÁS del texto Markdown de
  siempre (nunca en vez de él). `ExtractionRecord.structured_blocks`
  (migración aditiva `0015`, mismo patrón que `0014`) persiste ese
  resultado. `ChunkType` gana `ESTRUCTURADO` (reutilizado, mismo
  criterio que `ENCABEZADO`/`PADRE`) y `FragmentationStrategy` gana
  `POR_HOJA_ESTRUCTURADA` -- un chunk por bloque estructurado, con
  `structured_blocks` como fuente de verdad (no un patrón implícito de
  título de sección, descartado explícitamente por el documento de
  diseño por frágil). A diferencia de `PADRE`, un chunk `ESTRUCTURADO`
  SÍ debe indexarse -- el filtro existente de `IndexSource` ya lo
  permite sin cambios, fijado con una prueba dedicada.
  **B.2b:** DSL cerrado y determinista de filtros/agregaciones
  (`domain/rag/structured_query.py` -- operadores `== != > >= < <=
  contains`, funciones `count sum avg min max`), sin LLM ni SQL libre,
  mismo espíritu que `RuleCondition` de `domain.conversational`;
  `RagService.query_structured` opera en memoria sobre los chunks
  `ESTRUCTURADO` ya fragmentados. Para que `ui/ingestion/panel.py`
  (que por regla propia solo llama a `application`, nunca a `domain`)
  pudiera ofrecer un control de prueba, se agregó
  `RagService.query_structured_from_text` (texto plano en vez de
  tipos de dominio) y una nueva pestaña "Datos estructurados" en el
  Laboratorio RAG. B.2c (exponer esto por HTTP al agente externo)
  queda explícitamente fuera -- misma conversación de contrato ya
  reconocida como pendiente para B.3. 922 pruebas en verde (0
  fallidas, 12 omitidas por dependencias opcionales), `ruff` sin
  hallazgos. Ver `Validacion_observaciones_RAG_STUDIO.md`, Ronda 25,
  puntos 71-74.

- **2026-08-03 — Documentación de instalación actualizada: un solo
  `requirements.txt`.** El archivo `requirements.txt` ya reunía, de
  hecho, el contenido completo de los cuatro archivos que hasta ahora
  se instalaban por separado (`requirements-dev.txt`,
  `requirements-ui.txt`, `requirements-ocr.txt`,
  `requirements-packaging.txt`), pero las instrucciones de instalación
  (README, `packaging/README.md`, docstring de `run_app.py`,
  comentario de `packaging/ragstudio.spec`) seguían indicando instalar
  los cuatro archivos aparte según lo que se fuera a usar. Se
  actualizaron todas esas referencias a un solo paso
  (`pip install -r requirements.txt`), y se ajustaron dos mensajes que
  apuntaban al usuario hacia `requirements-ocr.txt`
  (`infrastructure/extraction/ocr_engine.py`,
  `infrastructure/extraction/text_extractors.py`) para que apunten al
  archivo unificado. Los cuatro archivos separados se dejan intactos
  por compatibilidad (por ejemplo, para quien todavía tenga un script
  propio que los referencie), pero ya no son parte del flujo de
  instalación documentado. Los extras de `pyproject.toml`
  (`pip install -e .[ui,ocr,dev,packaging]`) siguen siendo la vía
  recomendada para instalar solo un subconjunto.

- **2026-08-01 — Validación de retroalimentación de progreso y aviso de
  finalización en los procesos de fondo, a pedido explícito del
  consultor** (la finalidad de RAG STUDIO es dejarle al agente
  conversacional información bien estructurada, y el consultor quería
  confirmar que nunca se queda "sin saber si ya terminó"). Se auditaron
  los tres paneles con trabajos reales en segundo plano (Ingesta,
  Diseño conversacional, Calidad) más el paquete final de entregables
  en Liberación. Hallazgo: el indicador de "en proceso" (barra de
  progreso + texto de estado + botones deshabilitados) ya estaba bien
  cubierto en los tres; los errores ya se avisaban con una ventana
  emergente (`QMessageBox`) visible sin importar la pestaña activa;
  pero el **éxito** solo cambiaba un texto de estado en pantalla, visible
  únicamente si el usuario seguía parado en esa pestaña exacta -- si se
  iba a revisar otra cosa mientras "Ejecutar pipeline completo"
  terminaba de indexar, no tenía ninguna forma de enterarse. El paquete
  final de entregables (lo que el consultor le entrega al agente
  conversacional), en cambio, ya avisaba correctamente con la ruta
  completa del archivo generado -- no necesitó cambios.

  Se agregó una ventana emergente "Listo" al terminar con éxito en:
  Ingesta (pipeline completo, extracción, fragmentación, indexación,
  comparación de modelos -- `_poll_active_job` en
  `ui/ingestion/panel.py`), Diseño conversacional (simulador --
  `ui/conversational/panel.py`) y Calidad (ejecutar evaluación --
  `ui/quality/panel.py`), en el mismo punto donde ya se emitía el
  `QMessageBox.critical` de error, así que el mecanismo es simétrico y
  ya probado. Se dejó fuera a propósito la búsqueda (textual/híbrida/
  semántica) de Ingesta: ahí el usuario normalmente ya está mirando la
  pantalla esperando el resultado, y una ventana emergente adicional
  sería una interrupción innecesaria, no una ayuda. Verificado con
  `py_compile`, `ruff` y `bandit` (incluye `ui/`, ver ítem anterior de
  esta misma bitácora); la suite de pruebas no se ve afectada porque
  `ui/` no forma parte del alcance medido por `--cov` (432 aprobadas,
  cobertura 80.07%, sin cambio). No se pudo verificar visualmente en
  este entorno (falta `libEGL`) -- queda anotado en
  `checklist_validacion_visual.md` para confirmar en una máquina real,
  cambiando de pestaña mientras el trabajo corre.

- **2026-08-01 — Auditoría de madurez (ronda 5): tres pasadas paralelas
  (arquitectura/calidad de código, cobertura de pruebas, portabilidad
  Windows más allá de rutas) + verificación directa de cada hallazgo
  antes de corregirlo, a pedido explícito del consultor de evaluar la
  herramienta "bajo ojo clínico, profesional y sincero" en su estado
  actual. Se implementaron los 6 hallazgos que el consultor aprobó:**
  1. **Tesseract en Windows, detección y mensaje de error.**
     `infrastructure/extraction/ocr_engine.py`: antes, si el binario de
     Tesseract no estaba en el PATH, el único mensaje de error
     mencionaba `sudo apt install` (inútil en Windows) y no había
     ninguna forma de indicarle a la aplicación dónde quedó instalado.
     Ahora, en Windows, `TesseractOcrEngine` busca el binario en las
     rutas por defecto del instalador oficial (proyecto UB-Mannheim) o
     en la variable de entorno nueva `RAGSTUDIO_TESSERACT_PATH`, y fija
     `pytesseract.pytesseract.tesseract_cmd` si lo encuentra; si aun así
     no aparece, el mensaje de error ahora es específico de Windows con
     instrucciones correctas. En Linux/macOS el comportamiento no
     cambió. Esta lógica de Windows no se pudo ejercitar en este entorno
     (sandbox Linux, sin binario de Windows que probar) -- queda
     documentado como algo a confirmar por el consultor en su máquina
     Windows real (ver `checklist_validacion_visual.md`).
  2. **Manual: instrucciones de Tesseract para Windows.** Antes, las
     secciones 2.1/2.2/13.2 solo mencionaban el comando de Ubuntu/Debian.
     Se agregó el enlace al instalador de Windows, la advertencia de que
     ese instalador no agrega el binario al PATH (a diferencia de
     Ubuntu), y el ejemplo de `RAGSTUDIO_TESSERACT_PATH` en cmd y
     PowerShell, en las tres secciones relevantes. Manual regenerado (23
     páginas) y verificado visualmente.
  3. **Dos `except Exception:` sin documentar en
     `ui/ingestion/panel.py`** (`_active_schema_id`, `_source_title`):
     atrapaban cualquier excepción en silencio, sin comentario ni
     registro, a diferencia del resto del código (que si atrapa todo a
     propósito, siempre lo explica). Se agregó el comentario que explica
     por qué es intencional en cada caso, y un `logger.debug(...,
     exc_info=True)` para que un fallo real de base de datos quede
     rastreable en los registros en vez de indistinguible de "todavía no
     configurado".
  4. **Bandit no escaneaba `ui/`.** A diferencia de mypy (que sí excluye
     `ui/` a propósito, por falta de stubs de tipos de PySide6 -- ver
     `pyproject.toml`), no había ninguna razón para que bandit, el
     analizador de seguridad estática, dejara fuera esa carpeta,
     especialmente ahora que `ui/theme.py` genera HTML por interpolación
     de texto. Se agregó `ui` al comando de bandit en
     `.github/workflows/tests.yml` y en `.pre-commit-config.yaml`;
     corrido contra `ui/` de forma aislada, cero hallazgos.
  5. **`ui/theme.py` sin ninguna prueba unitaria.** Se agregó
     `tests/unit/ui/test_theme.py` cubriendo `color_para_estado()` para
     los siete enums reales y `estado_html()` (con y sin color, y con
     caracteres especiales). De paso, se encontró y corrigió una
     inconsistencia real: `estado_html()` no escapaba su `texto` de
     entrada -- `ui/release/panel.py` lo compensaba escapando por su
     cuenta antes de llamarla, pero `ui/quality/panel.py` e
     `ui/ingestion/panel.py` no, así que el comportamiento dependía de
     qué pantalla se mirara. Ahora `estado_html()` siempre escapa
     internamente (con `html.escape`), y se quitó el escape redundante
     en `ui/release/panel.py`.
  6. **`tests/smoke/test_ui_construction.py` no aplicaba la hoja de
     estilos real.** La única prueba que construye la ventana principal
     no llamaba a `app.setStyleSheet(HOJA_DE_ESTILOS)`, así que un error
     de sintaxis en el QSS nunca lo hubiera detectado. Se agregó esa
     línea, igual que hace `ui/app.py` en el arranque real.

  Además, dos notas puramente documentales, sin cambio de comportamiento:
  **SQLite en modo WAL no es confiable sobre unidades de red** (comentario
  agregado en `infrastructure/database/engine.py`; no aplica hoy porque
  los datos siempre viven dentro del propio directorio de instalación,
  pero queda advertido para el futuro), y la **cobertura total de
  pruebas quedó en 80.07%** (432 aprobadas, 2 omitidas por falta de Qt
  en este entorno) -- prácticamente sin margen sobre el mínimo exigido
  en CI (80%); cualquier código nuevo sin pruebas en `infrastructure/`
  podría hacer que ese gate empiece a fallar sin avisar antes.

  Hallazgos de las tres pasadas que se revisaron y se decidió NO atender
  en esta ronda, por criterio explícito de no sobrecomplicar la
  herramienta: agregar un runner de CI para Windows (mejora real, pero
  de mayor alcance -- se deja para cuando el uso en Windows esté más
  consolidado); profundizar las pruebas de los extractores HTML/JSON/XML
  en casos límite (namespaces, anidamiento profundo) -- brecha real pero
  de menor urgencia que las anteriores; y la elección de color de
  `en_revision` (azul "en proceso" en vez de ámbar) -- es una decisión
  de diseño subjetiva, no un error.

- **2026-07-30 — Auditoría de rutas absolutas para compatibilidad con
  Windows (a raíz de un usuario probando la herramienta en Windows) +
  ejemplos de variables de entorno en el manual, también para Windows.**
  Se auditó sistemáticamente el manejo de rutas en todo el código:
  resolución del directorio base (`app/configuration.py`), layout de
  archivos (`infrastructure/filesystem/paths.py`), construcción de URLs
  de SQLite (`infrastructure/database/engine.py`/`migrations.py`),
  empaquetado y desempaquetado de `.agentproj` y de entregables de
  liberación (`infrastructure/filesystem/packager.py`/
  `release_packager.py`), exportación de diagnóstico, resolución de la
  carpeta `migrations/` en modo fuente y empaquetado (PyInstaller), el
  `.spec` de PyInstaller, y el índice local de Qdrant. **No se
  encontraron rutas absolutas hardcodeadas ni errores de separador de
  ruta**: todo el código ya usa `pathlib.Path` de forma consistente,
  construyendo las rutas relativas a un directorio base portable; los
  casos que a primera vista podían parecer riesgosos se verificaron
  explícitamente en vez de darlos por buenos: la URL de SQLite
  (`f"sqlite:///{db_path}"`) resulta correcta tanto en Linux como en
  Windows porque `str(Path)` produce el separador nativo de cada
  sistema y ese formato coincide exactamente con el que documenta
  SQLAlchemy para rutas absolutas de Windows (verificado con
  `PureWindowsPath` real, no supuesto); el empaquetado `.agentproj` ya
  usa `.as_posix()` explícitamente al nombrar los archivos dentro del
  .zip (obligatorio por el estándar ZIP, y correcto sin importar en qué
  sistema operativo se generó o se abre el paquete).
  Se encontró y corrigió, en cambio, un problema real de sintaxis (no
  de rutas): los tres ejemplos de variables de entorno del manual
  (`RAGSTUDIO_HOME`, `RAGSTUDIO_EMBEDDING_PROFILE`,
  `RAGSTUDIO_MAX_CONCURRENT_JOBS`, sección 2.3-2.5) estaban escritos
  solo en sintaxis de shell Unix (`VAR=valor comando`), que no funciona
  igual en `cmd`/PowerShell de Windows -- si el usuario que prueba en
  Windows copió alguno de esos ejemplos tal cual, es la explicación más
  probable de cualquier "inconveniente" que haya reportado. Se agregó
  el equivalente exacto para `cmd` (`set VAR=valor && comando`) y
  PowerShell (`$env:VAR="valor"; comando`) junto a cada ejemplo
  existente, sin quitar el de Linux/macOS. Manual regenerado (22
  páginas, sin cambio de conteo), verificado visualmente.
  Nota de alcance, ya documentada en el capítulo 15.2 del manual y sin
  cambios en esta ronda: esta versión de RAG STUDIO está probada y
  soportada formalmente solo bajo Ubuntu -- nada en el código bloquea
  Windows a propósito, pero tampoco hay una corrida de principio a fin
  ni un ejecutable de PyInstaller verificados ahí todavía.

- **2026-07-29 — Análisis del hallazgo de Tesseract en RAG CONTENT
  STUDIO (sin cambios de código: no aplica aquí) y paleta de colores +
  color semántico de estado en la interfaz (sí implementado).** A
  pedido del consultor, se revisó qué pasó en RAG CONTENT STUDIO con
  Tesseract y con el color de su interfaz, para evaluar si algo de eso
  aplicaba a RAG STUDIO.
  **Tesseract:** RCS encontró y corrigió un bug real -- cuando fallaba
  la extracción (por ejemplo, sin Tesseract instalado), sus documentos
  quedaban atascados para siempre en el estado `en_extraccion`, porque
  guardaban ese estado intermedio antes de invocar al motor real, sin
  ningún `try/except` que lo revirtiera si el motor fallaba, y su
  máquina de estados no permite una transición de un estado a sí mismo
  (así que ni un reintento posterior podía sacarlos de ahí). Se verificó
  el código real de RAG STUDIO (`ExtractSourceText.execute()` y
  `FragmentSource.execute()`, en `application/ingestion/commands/`) y
  se confirmó que **esta clase de bug no existe aquí**: ninguno de los
  dos casos de uso persiste un estado intermedio "en progreso" sobre la
  fuente antes de llamar al extractor o al fragmentador -- ambos arman
  el resultado completo en memoria y solo escriben (`ExtractionRecord`/
  `Chunk`) al final, si todo salió bien; si el extractor lanza una
  excepción, no se guarda nada y la fuente queda exactamente como antes
  del intento, lista para reintentarse sin ninguna acción manual. El
  único estado real que sí existe durante una extracción (`JobStatus.
  EJECUTANDO`, en `workers/jobs.py`) vive solo en memoria mientras el
  proceso sigue corriendo -- nunca se persiste en la base de datos (no
  existe ningún `JobRepository`) -- así que ni siquiera un cierre
  abrupto de la aplicación puede dejar un registro atascado: al no
  haberse guardado nada, simplemente no hay nada que destrabar. Por
  este motivo no se hizo ningún cambio de código para este punto --
  sería una corrección para un problema que esta arquitectura ya evita
  por construcción. (De paso se confirmó que el manejo de Tesseract en
  sí -- idioma por defecto `spa+eng`, degradación controlada si falta
  el extra de OCR -- ya es equivalente al de RCS.)
  **Colores:** aquí sí se encontró una mejora aplicable y de bajo
  riesgo, así que se implementó. RAG STUDIO no tenía, hasta ahora,
  ningún `setStyleSheet()`/`QPalette` propio -- solo el tema por
  defecto del sistema operativo, igual que RCS antes de su cambio; se
  confirmó que agregar color no compromete el rendimiento (no hay
  ningún bucle de repintado continuo que un color pudiera encarecer, y
  el único costo real de esta herramienta -- descarga/cómputo de
  embeddings -- no lo toca un `QPushButton` con color). Nuevo módulo
  `ui/theme.py`, con la misma paleta de azules que ya usa RAG CONTENT
  STUDIO (`#1F3864`/`#2E5395`) -- decisión deliberada: ninguna paleta
  previa de RAG STUDIO existía que respetar (su manual usa los
  encabezados por defecto de Word/LibreOffice, no colores propios), y
  reusar la misma paleta le da identidad visual consistente a las dos
  herramientas hermanas de la misma suite. Dos piezas:
  1. **Hoja de estilos (QSS) global**, aplicada una sola vez sobre
     `QApplication` en `ui.app.main()`, adaptada al inventario real de
     widgets de RAG STUDIO -- que usa `QListWidget` para todas sus
     listas (Proyectos, Fuentes, Intenciones, Complementos, etc.) y
     `QTextBrowser` para sus reportes (Pipeline, Evaluación,
     Liberación), a diferencia de RCS que usa `QTableWidget` en varias
     pantallas -- además de las 8 pestañas principales, botones,
     tarjetas/agrupadores de formulario y campos de entrada.
  2. **Color semántico de estado**: `color_para_estado()` mapea el
     `.value` de los siete enums de estado reales de esta aplicación
     (`ProjectStatus`, `SourceValidationStatus`, `JobStatus`,
     `PipelineRunStatus`, `PipelineItemStatus`, `ReleaseStatus`,
     `EvaluationVerdict` -- el mismo inventario del capítulo 16 del
     manual) a cuatro categorías -- éxito (verde), atención (ámbar), en
     proceso (azul) y bloqueo (rojo) -- nunca reemplazando el texto
     original, solo reforzándolo (accesibilidad básica para
     variaciones de percepción del color). Dos formas de aplicarlo,
     según dónde vive el estado en esta aplicación:
     `aplicar_color_estado_item()` colorea una fila completa de
     `QListWidget` (Proyectos, Fuentes, historial de Liberación), y
     `estado_html()` envuelve una palabra en un `<span>` con color en
     línea dentro de un reporte HTML ya existente (estado de una
     corrida de pipeline y de cada fuente en Ingesta, veredicto general
     y por caso en Calidad, marcas ✔/✘ y estado de la liberación en
     Liberación).
  3. Ruff, Mypy (`ui/` sigue fuera de su alcance, sin cambios) y Bandit
     limpios; las 432 pruebas unit+smoke sin cambios ni regresiones
     (el cambio es puramente de interfaz, no toca `application`/
     `domain`/`infrastructure`). Este entorno de construcción no tiene
     acceso a las bibliotecas gráficas del sistema (falta `libEGL`,
     igual que en RCS), así que no se pudo tomar una captura de
     pantalla real ni correr las pruebas de humo gráficas para
     verificación visual directa -- se agregó una nota al inicio de
     `checklist_validacion_visual.md` y se recomienda que el usuario
     confirme el resultado visual la próxima vez que abra la
     aplicación en su propio equipo.

- **2026-07-29 — Revisión a fondo del Manual de Usuario contra un
  requerimiento explícito de detalle y usabilidad.** El requerimiento
  pedía: contenido muy específico y detallado, fácil de entender para
  un usuario no experto, paso a paso para cada proceso, observaciones
  claras, ejemplos donde aplique, glosario de términos, y todo en
  español. El glosario (capítulo 14) y el idioma ya cumplían; la
  auditoría encontró que cerca de la mitad de las secciones "cómo hacer
  X" del manual describían qué hace una pantalla en prosa, sin dar una
  secuencia numerada real de qué botón pulsar y qué campos llenar --
  particularmente en Proyectos (4.2-4.4), Metadatos (6.1-6.2, el
  proceso más usado), Ingesta (7.1-7.2, 7.4-7.5), Diseño conversacional
  (8.1-8.5 completo, la sección menos detallada pese a ser el núcleo de
  la herramienta), Calidad (9.1-9.2) y Liberación (10.1-10.3). Antes de
  escribir una sola palabra nueva, se verificó contra el código real de
  cada panel PySide6 (`ui/projects/panel.py`, `ui/metadata/panel.py`,
  `ui/ingestion/panel.py`, `ui/conversational/panel.py`,
  `ui/quality/panel.py`, `ui/release/panel.py`, `ui/plugins/panel.py`)
  el nombre exacto de cada botón, cada campo de cada diálogo, cuáles son
  obligatorios, y las opciones exactas de cada combo -- para no
  inventar ni aproximar nada.
  Esa verificación encontró, de paso, dos problemas reales que el
  manual anterior tenía sin saberlo: (1) el botón para crear un
  proyecto se llama "Nuevo proyecto" en la aplicación real, no "Crear
  proyecto" como decía el manual (corregido en 4.1); (2) la nota de la
  sección 6.4 sugería que un campo de metadatos puede aceptar "varios
  valores separados por coma si el campo lo permite", pero la ventana
  real de "Agregar campo" (`_FieldDialog` en `ui/metadata/panel.py`) no
  tiene ninguna casilla para marcar un campo como multivalor -- es una
  limitación real de esta versión (el modelo de dominio sí contempla
  `FieldDefinition.multiple`, pero ningún camino de la interfaz llega a
  activarlo), ahora advertida explícitamente en el manual en vez de
  quedar implícita.
  Se reescribieron con pasos numerados reales, notas y ejemplos: 4.2
  (elegir proyecto activo -- aclarando que es un clic sobre la lista,
  no un botón separado), 4.3 (exportar/importar), 4.4 (archivar --
  advirtiendo que no pide confirmación, a diferencia de eliminar un
  catálogo), 6.1 (crear/editar un campo de esquema, con la lista
  completa de los 15 tipos de dato reales), 6.2 (crear catálogo,
  agregar/editar/eliminar entradas -- aclarando que agregar una entrada
  son dos ventanas seguidas, no un solo formulario), 7.1 (pipeline),
  7.2 (extracción), 7.4 (búsqueda RAG, con los 3 modos y los 2
  filtros), 7.5 (comparador de modelos), el capítulo 8 completo
  (intenciones, variables, guardrails -- con ejemplo real de una
  condición `confianza < 0.70` porque no hay ningún campo de patrón o
  palabra clave, solo texto estructurado "campo operador valor" --,
  esquemas de canalización con un ejemplo mínimo completo, y el
  simulador), 9.1 (crear caso de prueba, con las 14 categorías reales),
  9.2 (ejecutar evaluación, con los 3 alcances), 10.1-10.3 (evaluar
  compuertas, solicitar liberación -- aclarando que, pese al nombre, no
  abre ningún formulario -- y exportar entregables) y 11.3
  (activar/desactivar/validar un complemento).
  El manual creció de 18 a 22 páginas. Regenerado con `build_manual.js`,
  convertido a PDF y verificado visualmente página por página. No se
  tocó ningún código de la aplicación en esta ronda -- fue exclusivamente
  una revisión de documentación.

- **2026-07-29 — Cuatro mejoras adoptadas de RAG CONTENT STUDIO
  (herramienta hermana del mismo autor, con acceso compartido para
  comparar ambos proyectos).** El objetivo explícito de esta ronda fue
  identificar qué de RAG CONTENT STUDIO (que prepara el contenido
  documental) podía aportarle a RAG STUDIO (que configura y evalúa el
  agente conversacional que consume ese contenido) SIN adoptar su
  arquitectura de gobierno documental completa (incidencias, vigencias,
  lotes, base de datos por proyecto) -- eso alteraría el objetivo
  central de esta herramienta y es exactamente el tipo de complejidad
  que se ha evitado en rondas anteriores. Se implementaron cuatro
  mejoras concretas, todas de bajo riesgo y sin impacto en la
  experiencia del usuario final:
  1. **Corrección de seguridad real en `pypdf`.** RAG CONTENT STUDIO ya
     había subido su piso de `pypdf` a `>=6.14.2` tras una corrida de
     `pip-audit` (comentario en su `pyproject.toml` citando
     CVE-2026-59935/-36/-37/-38). Se verificó que la afirmación era
     exacta (las cuatro CVE son reales, de julio de 2026, todas
     denegación de servicio -- bucle infinito o consumo excesivo de
     memoria -- al parsear un PDF manipulado) y que RAG STUDIO seguía
     con `pypdf>=4.0` sin techo: la versión efectivamente instalada en
     este entorno (6.13.1) SÍ es vulnerable a las cuatro. Se corrigió el
     piso a `pypdf>=6.14.2` en `pyproject.toml` y `requirements.txt`, y
     se confirmó que `pip-audit -r requirements.txt` queda limpio y que
     la suite completa (432 pruebas) sigue en verde con la versión
     nueva instalada.
  2. **pip-audit, bandit y pre-commit agregados.** Los tres ya estaban
     configurados en RAG CONTENT STUDIO; ninguno existía en RAG STUDIO
     hasta ahora, y el primero (pip-audit) habría detectado el problema
     del punto 1 automáticamente en vez de depender de una comparación
     manual entre proyectos. Se agregaron a `dev` en `pyproject.toml` y
     a `requirements-dev.txt`, se agregó `[tool.bandit]` (mismo alcance
     que ruff/mypy: app/application/domain/infrastructure/workers,
     excluyendo tests/migrations por generar datos de prueba
     deliberadamente "inseguros"), se creó `.pre-commit-config.yaml`
     (ruff + mypy + bandit + pytest en cada commit local -- pip-audit
     queda fuera de los hooks locales a propósito porque necesita
     internet y no es determinista offline) y se actualizó
     `.github/workflows/tests.yml`: bandit se sumó como paso obligatorio
     del job `lint-and-typecheck` (tan rápido/determinista/sin red como
     ruff y mypy), y se agregó un job nuevo `security-audit` para
     pip-audit, informativo y no bloqueante (`continue-on-error: true`,
     mismo criterio que el job `integration`), acotado a
     `-r requirements.txt`/`-r requirements-dev.txt` para no reportar
     paquetes del entorno del runner que no son dependencias reales del
     proyecto (correr `pip-audit` sin argumentos en este entorno de
     construcción sandbox mezcla cientos de paquetes del sistema
     operativo -- un efecto puramente de este entorno de verificación,
     no del proyecto).
     Bandit, ya configurado, encontró de inmediato cuatro hallazgos
     reales sobre código existente: dos falsos positivos evidentes
     (`B105`, una cadena de puntuación marcada como "posible contraseña
     hardcodeada" en `text_extractors.py`; `B112`, un `except/continue`
     deliberado y ya documentado en `run_evaluation.py` para que un
     complemento roto no tumbe una corrida de evaluación) que se
     suprimieron con `# nosec` puntual y un comentario explicando por
     qué, y dos hallazgos reales sobre el `XmlExtractor` agregado la
     iteración anterior (`B314`/`B405`): `xml.etree.ElementTree` sin
     protección es vulnerable a ataques de entidades externas ("billion
     laughs"). Se corrigió cambiando el import a
     `defusedxml.ElementTree` (reemplazo directo, misma API, mismo
     `ParseError`, agregado como dependencia `defusedxml>=0.7`) -- bandit
     queda en cero hallazgos y la suite completa sigue en verde.
  3. **Tabla de "Mensajes más comunes" en el manual (sección 13.8
     nueva).** El manual de RAG CONTENT STUDIO tiene una tabla de
     referencia rápida (mensaje literal → qué significa → qué hacer)
     que resultó más accionable que la sección narrativa de solución de
     problemas que ya tenía RAG STUDIO. Se agregó una sección
     equivalente con 10 mensajes de validación reales (verificados
     contra el código, no inventados: `domain/projects/entities.py`,
     `domain/documents/entities.py`, `application/metadata/commands/
     set_source_metadata_value.py`, `domain/metadata/exceptions.py`,
     `domain/ingestion/exceptions.py`, `application/rag/queries/
     text_search.py`), cada uno con su significado y la acción a
     tomar.
  4. **Nuevo anexo "Estados y ciclos de vida" (capítulo 16).** RAG
     CONTENT STUDIO documenta, en un anexo dedicado, qué significa cada
     estado que un usuario puede ver en las tablas de la aplicación
     (documento, incidencia, trabajo, lote, severidad, confidencialidad)
     -- RAG STUDIO no tenía nada equivalente, aunque sí tiene sus propios
     estados visibles en pantalla. Se agregó el capítulo 16 con seis
     secciones, cada una verificada directamente contra el enum real en
     el código (no inferida): estados de un proyecto (`ProjectStatus`,
     `domain/projects/entities.py`), estados de validación de una fuente
     (`SourceValidationStatus`, `domain/documents/entities.py`), estados
     de un trabajo en segundo plano (`JobStatus`, `workers/jobs.py` --
     incluyendo la nota honesta de que "Pausado" está declarado en el
     enum pero ningún código lo asigna todavía), estados de una corrida
     del pipeline (`PipelineRunStatus`, `domain/pipeline/entities.py`),
     estado de una liberación (`ReleaseStatus`, `domain/release/
     entities.py` -- con la aclaración honesta de que el documento
     maestro define ocho valores posibles pero el flujo real de hoy solo
     produce dos: Aprobada/Bloqueada, verificado en
     `application/release/commands/request_release.py`) y veredicto de
     un caso de prueba evaluado (`EvaluationVerdict`, `domain/quality/
     entities.py`).
  El manual creció de 15 a 18 páginas. Regenerado con `build_manual.js`,
  convertido a PDF y verificado visualmente página por página (secciones
  13.8 y 16 completas, sin errores de formato). Suite completa
  verificada tras todos los cambios: ruff y mypy en cero hallazgos,
  bandit en cero hallazgos, `pip-audit -r requirements.txt`/`-r
  requirements-dev.txt` limpios, 432 pruebas unit+smoke en verde.
  Deliberadamente NO se adoptó de RAG CONTENT STUDIO: gestión de
  incidencias, seguimiento de vigencia documental, agrupación por
  lotes, base de datos separada por proyecto, ni extender mypy a `ui/`
  (lo logró incluyendo `ui` en su `[tool.mypy] files`, pero migrar los
  widgets PySide6 de RAG STUDIO a chequeo de tipos completo es un
  esfuerzo no trivial que queda como candidato para una futura ronda
  dedicada, no para esta comparación).

- **2026-07-29 — Extractores reales de HTML, JSON y XML: cierra la
  brecha señalada explícitamente en el manual de usuario.** El manual
  ya advertía que estos tres tipos (más API y base de datos) estaban
  reconocidos en `domain.documents.entities.SourceType` pero sin
  extractor -- confirmado en el código: `CompositeTextExtractor` no los
  registraba y la extracción fallaba con `UnsupportedSourceTypeError`
  (controlado, pero sin producir texto). Se agregaron
  `HtmlExtractor`, `JsonExtractor` y `XmlExtractor` a
  `infrastructure/extraction/text_extractors.py`, cableados tanto en el
  constructor por defecto de `CompositeTextExtractor` como en
  `app/bootstrap.py` (que pasa su propia lista explícita -- fácil de
  pasar por alto, y de hecho al principio se me olvidó ahí). Los tres
  siguen, en lo posible, el mismo idioma Markdown que ya usan
  DocxExtractor/XlsxExtractor/CsvExtractor para que las estrategias de
  fragmentación existentes los reconozcan sin cambios: `HtmlExtractor`
  convierte h1-h6 a encabezados '#'*N y `<table>` a tabla Markdown (vía
  el `_HtmlToMarkdownParser`, sobre `html.parser.HTMLParser` de la
  librería estándar -- sin dependencia nueva), descartando el contenido
  de `<head>`/`<script>`/`<style>` por completo. `JsonExtractor`
  detecta el caso común de una lista de objetos "planos" (sin anidar)
  y la convierte en tabla Markdown (reutilizando
  `rows_to_markdown_table`, la misma función que ya comparten
  DOCX/XLSX/CSV); para JSON con estructura más irregular o anidada, se
  aplana a líneas "ruta.al.campo: valor" (`_flatten_json`). XML no
  tiene una noción de "tabla" tan clara como JSON (elementos repetidos,
  atributos vs. sub-elementos), así que siempre se aplana a líneas
  "ruta.al.elemento (atributo=valor): texto" (`_xml_element_to_lines`),
  usando `xml.etree.ElementTree` de la librería estándar. Errores de
  formato (JSON/XML malformado) se dejan propagar tal cual --
  `json.JSONDecodeError`/`xml.etree.ElementTree.ParseError` ya son
  razonablemente descriptivos, el mismo criterio que ya aplicaba
  DocxExtractor para un DOCX corrupto (no todo error de negocio
  necesita envolverse en una excepción de dominio propia). API y base
  de datos quedan deliberadamente sin extractor: no son archivos, son
  conexiones vivas (URL/credenciales/consulta), un problema distinto de
  "parsear un archivo" -- implementarlas de verdad significaría un
  sistema de conectores nuevo, no un extractor más, exactamente el tipo
  de complejidad añadida que se decidió evitar en esta ronda. El manual
  de usuario se actualizó (sección 5.1 y capítulo 15) para reflejar la
  cobertura real, regenerado y verificado visualmente. 15 pruebas
  nuevas en `tests/integration/test_text_extractors.py` (extracción
  real de encabezados/tablas/warnings en HTML, tabla vs. aplanado en
  JSON, atributos y namespaces en XML, y los casos de archivo
  malformado/vacío para los tres), más el ajuste de las dos pruebas
  existentes que usaban HTML como ejemplo de tipo "sin soporte" (ahora
  usan API, que sigue siéndolo). Suite completa verificada: ruff y
  mypy en cero hallazgos, unit+smoke en verde, y una pasada dirigida de
  integración (extractores + ingesta + ida y vuelta de exportación)
  también en verde.

- **2026-07-28 — ruff y mypy configurados y en verde en CI: cuarta
  ronda de madurez post-8-etapas.** Auditoría de esta ronda (ver
  README, punto anterior de "profesionalismo"): el proyecto nunca tuvo
  ni un linter ni chequeo de tipos estático configurado, algo que el
  propio workflow de CI ya reconocía como brecha pendiente desde el
  ítem 6. Se agregó `[tool.ruff]`/`[tool.mypy]` a `pyproject.toml` y un
  nuevo job obligatorio `lint-and-typecheck` en
  `.github/workflows/tests.yml`, junto al ya existente `unit-and-smoke`.
  Decisiones deliberadas de alcance, para no generar ruido sin valor
  real: ruff selecciona solo `E`/`F`/`B` (pycodestyle, pyflakes,
  bugbear) e ignora `E501` (línea larga, por el estilo de comentarios
  extensos en español del proyecto); se decidió EXCLUIR `I` (orden de
  imports) y `UP` (modernizar sintaxis, p. ej. `Optional[X]` ->
  `X | None`) porque activarlas hoy generaría un diff mecánico de
  cientos de líneas en casi todo el proyecto sin corregir ningún error
  real -- candidatas para una futura iteración dedicada, no para esta.
  mypy cubre el mismo alcance que el umbral de cobertura de pytest-cov
  (`app`/`application`/`domain`/`infrastructure`/`workers`, sin `ui/`
  por falta de stubs completos de PySide6) en modo NO estricto
  (`check_untyped_defs` sí, pero sin exigir anotaciones completas en
  todo el código de golpe).
  De los 20 hallazgos reales de ruff (los ~440 restantes eran solo el
  diff mecánico ya descartado arriba), destaca uno real de fiabilidad:
  9 usos de `zip()` sin `strict=`, de los cuales 8 ahora usan
  `strict=True` porque las listas involucradas SÍ deben tener siempre
  la misma longitud por construcción (por ejemplo, un vector de
  embedding por cada fragmento al indexar, en
  `application/rag/commands/index_source.py`) -- antes, si un proveedor
  de embeddings alguna vez devolvía menos vectores que fragmentos,
  `zip()` los emparejaba mal en silencio en vez de fallar; ahora falla
  alto y claro. El noveno (`domain/ingestion/splitting.py`, una
  ventana deslizante de a pares) usa `strict=False` explícito con un
  comentario, porque ahí las longitudes SÍ difieren en 1 a propósito.
  De los 94 hallazgos iniciales de mypy, 70 eran el mismo comentario de
  tipo `# type: Session` repetido en 10 archivos de
  `infrastructure/database/`, ya redundante (el retorno de
  `make_session_factory` ya está tipado como `sessionmaker[Session]`) y
  se quitó sin más. De los 24 restantes, ninguno resultó ser un bug de
  comportamiento real ya activo, pero sí se encontraron y corrigieron
  varias inconsistencias de tipos genuinas que valía la pena resolver:
  un `Optional[Semaphore]` y un `Optional[OcrEngine]` cuyo chequeo de
  `None` vivía en el llamador pero no en el método que de verdad accede
  al valor (se agregó el chequeo también ahí, defensa en profundidad);
  una anotación `docx.Document` que en realidad apunta a una función
  fábrica, no al tipo real (`docx.document.Document`); una
  reconstrucción de `FragmentationPolicy` vía `**dict` con tipos
  heterogéneos, reescrita con ramas explícitas (y, de paso, se eliminó
  una lista de valores por defecto duplicada que ya estaban declarados
  en el propio modelo); una validación de invariante de dominio
  (`catalog_id` obligatorio para campos con catálogo) que ya se
  cumplía en la práctica pero no tenía una red de seguridad explícita
  en el punto de uso; un parámetro `list[RuleCondition]` pasado donde
  se esperaba `list[RuleCondition | dict]` (invarianza de `list` en
  Python: se cambió el parámetro a `Sequence`, covariante, sin ningún
  cambio de comportamiento); y un borrado de SQLAlchemy vía
  `Model.__table__.delete()` reescrito como `delete(Model)` (estilo
  SQLAlchemy 2.0, consistente con el resto del archivo). Se agregó
  `explicit_package_bases = true` a la config de mypy porque el nombre
  de esta carpeta de instalación contiene un espacio, lo cual mypy no
  acepta como nombre de paquete por defecto. Verificado con ruff y
  mypy en cero hallazgos, la suite completa de unit+smoke (432 pruebas)
  y una pasada de pruebas de integración relevantes a los archivos
  tocados (61 pasadas), todo en verde.

- **2026-07-28 — Los datos de la instalación ahora viven dentro de la
  carpeta de la aplicación, no dispersos en el perfil del sistema
  operativo.** Reportado directamente por el usuario: al crear un
  proyecto no aparecía ninguna carpeta con sus datos dentro de esta
  misma carpeta del repositorio, porque `app.configuration.
  default_base_dir()` apuntaba, por diseño original (ADR-001, sección
  11), a la carpeta de perfil de cada sistema operativo (`%APPDATA%\
  RAGStudio` en Windows, `~/Library/Application Support/RAGStudio` en
  macOS, `~/.local/share/ragstudio` en Linux) -- correcto según la
  convención de cada plataforma, pero exactamente el problema que se
  quería evitar: archivos reales (proyectos, `application.db`, caché de
  modelos, logs) dispersos fuera de donde vive la aplicación. Ahora el
  valor por defecto es una subcarpeta `data/` dentro de esta misma
  instalación (junto a `run_app.py`), calculada a partir de la
  ubicación real del código (`app/configuration.py`) cuando se corre
  desde código fuente, o de la ubicación real del ejecutable
  (`Path(sys.executable).resolve().parent`, nunca `sys._MEIPASS`, que es
  un directorio temporal de extracción) cuando está empaquetado con
  PyInstaller -- para que la carpeta `dist/RAGStudio/` también quede
  autocontenida. Se agregó además la variable de entorno opcional
  `RAGSTUDIO_HOME` para quien de verdad necesite otra ubicación (disco
  compartido, varias instalaciones en la misma máquina), con la misma
  prioridad que el resto de los ajustes por variable de entorno:
  parámetro explícito a `load_settings`/`bootstrap`/`start` primero,
  luego `RAGSTUDIO_HOME`, luego el nuevo valor por defecto. `data/` se
  agregó a `.gitignore` (nunca debe subirse al control de versiones).
  Los proyectos de prueba que ya existían en la ubicación anterior del
  sistema operativo se dejan intactos ahí -- por decisión del usuario,
  no se migran automáticamente, ya eran solo pruebas y conviene
  empezar de cero con el proyecto real una vez todos estos ajustes
  están en su lugar; el usuario puede borrarlos manualmente si quiere
  (la ruta exacta depende de su sistema operativo, ver arriba) o
  dejarlos huérfanos sin ningún efecto en el funcionamiento normal de
  la aplicación. Cubierto con 5 pruebas nuevas en
  `tests/unit/app/test_configuration.py` (código fuente, empaquetado
  simulado con `monkeypatch` de `sys.frozen`/`sys.executable`,
  variable de entorno, y prioridad explícito > variable > default).
  Manual de usuario actualizado (sección 2.3) y `packaging/README.md`
  con una nota sobre qué falta verificar contra un ejecutable real.
  Suite completa: 432 pruebas unit+smoke, todas en verde.

- **2026-07-28 — Tercera ronda de madurez: auditoría enfocada en
  usabilidad, no solo en robustez técnica.** Con el pedido explícito de
  no volver la herramienta más compleja de usar, esta ronda auditó
  domain/application/infrastructure/ui/workers/tests buscando tanto
  huecos técnicos como fricciones reales de experiencia para un usuario
  no técnico, y descartó deliberadamente varias mejoras candidatas
  (`ProcessJobRunner` real, reranking con cross-encoder, versionado de
  índices) por agregar complejidad sin beneficio proporcional al
  propósito de la herramienta. Se implementaron solo tres correcciones
  puntuales, sin agregar ninguna pestaña, ajuste ni concepto nuevo:
  (1) se quitó de `ui/projects/panel.py` el botón "Simular tarea larga"
  -- un control huérfano visible en producción junto a "Nuevo
  proyecto"/"Archivar"/"Exportar"/"Importar" que no cumplía ninguna
  función real (solo demostraba internamente que la interfaz no se
  congela) y no estaba documentado en el manual ni en el glosario; la
  prueba de que los trabajos en segundo plano no congelan la interfaz
  sigue cubierta por `tests/smoke/test_job_runner_non_blocking.py`
  contra `demo_long_task`/`ThreadJobRunner` directamente, y
  `checklist_validacion_visual.md` se actualizó para validar esa misma
  propiedad con una acción real (el pipeline de Ingesta) en vez del
  botón eliminado; (2) `application/documents/commands/register_source.py`
  registraba en silencio total cualquier fallo al copiar el archivo
  original de una fuente a `sources/original/` -- correcto no tumbar el
  registro por esto, pero sin ni una línea de rastro; ahora se deja un
  `logger.warning` con el motivo exacto, sin cambiar el comportamiento
  visible (nueva prueba `test_register_source_logs_warning_on_copy_
  failure` en `tests/unit/application/test_document_service.py`); (3)
  el manual tenía "score" en la interfaz de búsqueda (`[0.735]` junto a
  cada resultado en Ingesta → Búsqueda RAG) sin una entrada de glosario
  que lo explicara, pese a definir términos igual de técnicos como
  Índice o Pipeline -- se agregó la entrada "Score (puntaje de
  relevancia)" al capítulo 14 del manual, regenerado y verificado
  visualmente (15 páginas). Suite completa: 427 pruebas unit+smoke
  (426 + la nueva), todas en verde.

- **2026-07-27 — Actualización del Manual de Usuario tras los 7 ítems
  de la segunda evaluación de madurez.** El manual (`RAG_STUDIO_Manual_
  de_Usuario.docx`/`.pdf`, en la raíz del proyecto) llevaba desactualizado
  desde antes de esa ronda de mejoras. Se revisó por completo (778 líneas
  convertidas a markdown para el análisis de brechas) y se actualizó,
  documentando en el mismo lenguaje claro y sin jerga técnica que usa
  todo el manual: los avisos preventivos de compuerta ahora visibles en
  cada pestaña de etapa (nueva sección 3.4 ampliada), el menú "Ayuda" y
  su exportación de diagnóstico (nueva 3.5 y nueva 13.7), la copia
  interna del archivo original al registrar una fuente (nota en 5.2), el
  historial de cambios de metadatos (nota en 6.4) y de extracciones
  (nota en 7.2), el nuevo botón "Exportar entregables" de Liberación
  (nueva 10.3), el almacenamiento seguro de credenciales de complementos
  sensibles y la corrección de una nota desactualizada que decía que los
  complementos Evaluador no estaban conectados a evaluaciones reales --
  ya lo están, solo Proveedor e Importador siguen sin conectarse al flujo
  activo (11.2/11.3), el mensaje "Ya hay un trabajo en curso..." de la
  deduplicación de trabajos (nueva 13.6), y el ajuste opcional avanzado
  `RAGSTUDIO_MAX_CONCURRENT_JOBS` (nueva 2.5) -- la única pieza de las 7
  de esta ronda con impacto directo visible para el usuario final; el
  resto (WAL/busy_timeout, CredentialStore como mecanismo interno,
  pytest-cov/CI, empaquetado PyInstaller) se dejó fuera del manual por
  ser de naturaleza técnica/operativa, ajena al público no técnico al
  que está dirigido (ver 1.2). Se aprovechó además para corregir un
  defecto real y preexistente en el generador (`build_manual.js`): todas
  las listas numeradas de pasos del documento compartían una sola
  referencia de numeración de Word, así que Word encadenaba el contador
  a lo largo de todo el documento en vez de reiniciarlo en cada lista
  (por ejemplo, el primer paso del capítulo 12 se mostraba como "35."
  en vez de "1."). Ahora cada lista de pasos usa su propia referencia de
  numeración, generada dinámicamente. El capítulo 14 (glosario) y el 15
  (anexo, listas de "Cubierto" y "Deliberadamente fuera de alcance") se
  actualizaron para reflejar todas las capacidades nuevas. Verificado
  regenerando el `.docx`, convirtiéndolo a PDF (14 páginas) e
  inspeccionando visualmente las páginas clave, incluida la de la lista
  del capítulo 12 para confirmar que ahora reinicia en "1.".

- **2026-07-27 — Andamiaje de empaquetado con PyInstoller: séptimo y
  último punto de la segunda evaluación de madurez post-8-etapas.**
  Antes no existía ningún script ni configuración de empaquetado --
  solo `pip install -e .` + `run_app.py`, sin forma de generar un
  ejecutable distribuible.
  Lo nuevo: `packaging/ragstudio.spec` (nuevo), que arma `dist/RAGStudio/`
  (modo *onedir*) con `pyinstaller packaging/ragstudio.spec --noconfirm
  --clean`. Incluye como `datas` el `LOGO.png` de la pantalla de
  bienvenida y la carpeta `migrations/` completa (las dos líneas de
  Alembic, global y por proyecto); como `hiddenimports`, las
  dependencias que PyInstaller no detecta caminando imports normales:
  `alembic`, `sqlalchemy.dialects.sqlite`, `qdrant_client`/
  `qdrant_client.local`, `fastembed`, `onnxruntime`, `keyring.backends`,
  y los submódulos de `tiktoken_ext` (`collect_submodules` de
  `PyInstaller.utils.hooks`) -- `tiktoken` registra sus codificaciones
  vía plugins descubiertos en caliente con `pkgutil.iter_modules`, un
  gotcha documentado de PyInstoller+tiktoken que sin esto habría hecho
  fallar `TiktokenCounter` ya empaquetado.
  Beneficio colateral real, no solo cosmético para el empaquetado: al
  revisar cómo `infrastructure.database.migrations` ubica la carpeta
  `migrations/` (`_find_repo_root`, subiendo desde el archivo hasta
  encontrar `pyproject.toml`) se confirmó un bug latente real -- un
  ejecutable de PyInstoller no tiene `pyproject.toml` en disco ni
  `Path(__file__)` apuntando al árbol fuente, así que las migraciones
  Alembic nunca se habrían encontrado corriendo empaquetado, mucho
  antes de que alguien llegara a intentarlo de verdad. Se corrigió con
  `_resolve_migrations_root()`: si `sys._MEIPASS` existe (el
  directorio temporal donde PyInstaller extrae los `datas` incluidos)
  y contiene `migrations/`, se usa ese; si no, cae de vuelta a la
  búsqueda de desarrollo de siempre -- capacidad opcional, mismo
  patrón que el resto de la sesión: en desarrollo/pruebas normales
  (`sys._MEIPASS` no existe) el comportamiento es exactamente el de
  antes.
  Se agregó `pyinstaller>=6.0` como dependencia opcional
  (`[project.optional-dependencies] packaging` en `pyproject.toml`,
  más `requirements-packaging.txt`) -- nunca requerida para correr la
  app ni las pruebas normalmente.
  Honestidad sobre el alcance real de la verificación (ver
  `packaging/README.md` para el detalle completo): en este entorno de
  construcción se corrió `pyinstaller` de verdad y su fase de
  *Analysis* (resolución de imports sobre PySide6, SQLAlchemy/Alembic,
  `qdrant-client`, las dependencias transitivas de `fastembed`,
  `keyring`, `tiktoken_ext`) avanzó sin ningún error durante ~40
  segundos reales, procesando decenas de *hooks* estándar -- señal real
  de que el `.spec` no tiene problemas gruesos de resolución de
  dependencias, pero **no es una compilación completa verificada**:
  este entorno mata cualquier proceso en segundo plano entre una
  llamada de shell y la siguiente (confirmado empíricamente con
  `setsid`+`disown`), y una compilación completa de un árbol tan pesado
  (PySide6 + onnxruntime + qdrant-client, cientos de MB de bibliotecas
  compartidas) tarda varios minutos -- no cabe en ese límite. Nunca se
  generó ni se corrió un ejecutable real, ni en Linux ni en
  Windows/macOS (PyInstaller nunca compila para un sistema operativo
  distinto al que lo ejecuta). Falta, antes de confiar en esto para
  distribuir la app de verdad: correrlo de punta a punta en cada
  sistema operativo objetivo, icono de la aplicación, firma de código,
  empaquetado final (`.msi`/`.dmg`/`.deb`, herramientas específicas de
  cada sistema operativo) y validar el almacén seguro de credenciales
  de `keyring` en los tres sistemas operativos reales (ADR-001, sección
  15) -- todo eso queda fuera de alcance de este ítem, que solo entrega
  el punto de partida.
  Pruebas: 3 pruebas de integración nuevas en
  `tests/integration/test_migrations_path_resolution.py` (encuentra la
  carpeta real de desarrollo; prefiere `sys._MEIPASS` simulado cuando
  existe y trae `migrations/` adentro; cae de vuelta a la búsqueda de
  desarrollo si `_MEIPASS` existe pero no trae `migrations/`) -- las
  426 pruebas unitarias/smoke existentes y las de migraciones Alembic
  reales (`test_alembic_migrations.py`) siguen en verde sin cambios,
  confirmando que el ajuste de `_resolve_migrations_root()` no afecta
  el comportamiento normal de desarrollo/pruebas.

  Con este séptimo punto se cierran los 7 ítems de la segunda
  evaluación de madurez post-8-etapas (SQLite WAL+busy_timeout,
  CredentialStore, deduplicación de trabajos, límite de concurrencia,
  excepciones no capturadas + diagnóstico, pytest-cov + CI, y este
  andamiaje de empaquetado) -- sumados a los 7 ítems de la primera
  evaluación (semántica de intenciones, evaluadores personalizados,
  avisos de compuertas, copia de archivo original, historial de
  cambios, paquete de entregables, tokenizador real), son 14 mejoras de
  madurez consecutivas desde que se cerró el ciclo de las 8 etapas del
  documento maestro.

- **2026-07-27 — pytest-cov + workflow de CI: sexto punto de la segunda
  evaluación de madurez post-8-etapas.** Antes, `pyproject.toml` no
  tenía ninguna configuración de `pytest-cov`, `ruff`, `mypy` ni
  `black`, y no existía ningún `.github/workflows/` -- la única forma
  de medir el estado del proyecto era el conteo de pruebas pasadas,
  sin ningún número de cobertura de líneas/ramas, y nada corría
  automáticamente en cada cambio.
  Lo nuevo: `pytest-cov>=5.0` agregado a `requirements-dev.txt` y a
  `[project.optional-dependencies] dev` en `pyproject.toml`.
  `[tool.coverage.run]`/`[tool.coverage.report]` (nuevo en
  `pyproject.toml`) miden todo el código de la app (`app`,
  `application`, `domain`, `infrastructure`, `workers`, `ui`) sin
  activarse por defecto en un `pytest` normal (nadie que no pida
  cobertura explícitamente ve overhead ni cambio de comportamiento).
  `.github/workflows/tests.yml` (nuevo) define dos jobs: `unit-and-smoke`
  (rápido, determinista, sin red -- exige `--cov-fail-under=80` sobre
  app/application/domain/infrastructure/workers, medido en ~82% real en
  esta iteración) y `integration` (`continue-on-error: true`, sin gate
  de cobertura -- varias pruebas de integración dependen de red real
  para descargar modelos/codificaciones, o de un backend real de
  `keyring`, y se omiten explícitamente cuando no están disponibles,
  como en este mismo entorno de construcción). Con integración incluida
  esos mismos paquetes suben a ~95%, medido de verdad en esta sesión
  (`coverage combine` acumulando sobre toda la suite) -- ese número
  queda documentado en el README como referencia, no como gate de CI,
  porque ese segundo job no es tan determinista. `ui/` se mide (para
  que el reporte sea honesto y completo) pero queda fuera del umbral
  que bloquea: sus widgets Qt reales están en 0% en cualquier entorno
  sin servidor gráfico (este entorno de construcción incluido), y se
  validan manualmente en la máquina real del usuario -- la lógica ya
  extraída de Qt en iteraciones anteriores sigue con cobertura real.
  No se configuraron `ruff`/`mypy`/`black`: el alcance de este ítem fue
  pruebas automatizadas y CI, no estilo estático (`ruff` ya se había
  investigado antes de esta segunda evaluación y se concluyó que sus
  533 hallazgos son ruido de configuración por defecto, no una
  regresión real -- ver notas de la auditoría de esta iteración).
  Ningún archivo ni carpeta nuevos rompen ADR-001: ambos son plomería
  de proceso (CI/cobertura), no código de la aplicación.
  Verificado en esta misma sesión: `pytest tests/unit tests/smoke -q`
  (sin flags de cobertura) sigue funcionando exactamente igual que
  antes (426 pruebas en verde); el comando exacto de
  `unit-and-smoke` del workflow corrido localmente confirma
  `Required test coverage of 80% reached. Total coverage: 82.00%`; y el
  YAML del workflow se validó con `yaml.safe_load`.

- **2026-07-27 — Excepciones no capturadas al log + paquete de
  diagnóstico exportable: quinto punto de la segunda evaluación de
  madurez post-8-etapas.** Antes, el logging estructurado
  (`app/logging_setup.py`) era sólido para lo que cada `try`/`except`
  explícito decidía registrar, pero un crash fuera de esos bloques (un
  bug real en `application`/UI, o en el propio `ThreadJobRunner`) no
  dejaba ningún rastro: ni `sys.excepthook` ni `threading.excepthook`
  estaban intervenidos, así que la única pista para diagnosticar un
  problema real del usuario habría sido lo que la terminal mostrara en
  el momento (si el usuario la tenía abierta y alcanzaba a verlo).
  Lo nuevo: `install_global_exception_hooks(logger)` (`app/logging_setup.py`)
  instala `sys.excepthook` y `threading.excepthook` -- cualquier
  excepción que llegue hasta ahí se registra con `logger.critical(...,
  exc_info=...)` (traceback completo, con la misma redacción de
  credenciales que ya aplica `RedactSensitiveDataFilter`) y luego se
  reenvía al manejador original (`sys.__excepthook__`), así que el
  comportamiento visible en la terminal no cambia, solo se agrega el
  registro. `KeyboardInterrupt` se excluye a propósito: es una
  interrupción intencional del usuario (Ctrl+C), no un error que haya
  que diagnosticar. `app/bootstrap.py` llama a esta función justo
  después de `configure_logging`, así que queda activa desde el primer
  momento de cualquier instalación real.
  Además, un nuevo paquete de diagnóstico exportable: `infrastructure.
  filesystem.diagnostics.FilesystemDiagnosticsExporter` arma un `.zip`
  con `info.json` (versión de RAG STUDIO vía `importlib.metadata`,
  versión de Python, `platform.platform()`, `base_dir`) y una copia de
  todos los archivos de `logs/`; `application.diagnostics_facade.
  DiagnosticsFacade` lo expone a `application` con el mismo criterio ya
  usado en `application.jobs_facade.BackgroundJobs` para `workers`
  (depende directamente de `infrastructure` sin inventar un puerto de
  `domain`, porque "empaquetar logs en un zip" no es una regla de
  negocio ni tiene un segundo adaptador intercambiable). La ventana
  principal (`ui/projects/main_window.py`) agrega un menú "Ayuda" con
  "Exportar diagnóstico…" -- no depende de un proyecto activo, igual
  que Complementos, así que vive en la barra de menú en vez de en una
  pestaña; usa `QFileDialog.getSaveFileName` igual que el exportador de
  entregables de Liberación (ítem 6 de la primera evaluación de
  madurez).
  Pruebas: 3 pruebas unitarias nuevas en
  `tests/unit/app/test_logging_setup.py` (excepción no capturada real
  llega al log con el traceback correcto; `KeyboardInterrupt` no se
  registra como error; una excepción no capturada en un hilo real
  también llega al log, con el nombre del hilo), 5 en el nuevo
  `tests/integration/test_diagnostics_export.py` (zip real con
  info.json, inclusión de logs existentes, no falla sin logs, crea
  directorios destino que falten, y la fachada delega correctamente), y
  1 nueva en `tests/smoke/test_app_bootstrap.py` (`bootstrap` conecta un
  exportador de diagnóstico que de verdad funciona). Total: 426 pruebas
  unitarias/smoke en verde (antes 422; las 5 de
  `test_diagnostics_export.py` son de integración, no cuentan en ese
  total). Se agregó `AppContext.diagnostics` (nuevo campo) -- solo se construye
  dentro de `bootstrap()`, no hay ningún otro sitio del código que
  construya `AppContext` a mano, así que no rompe ningún llamador
  existente. Verificado también en vivo contra `app/bootstrap.py`
  end-to-end: una excepción no capturada real queda en `ragstudio.log`
  con su traceback, y `export_diagnostics_package` produce un `.zip`
  real con `info.json` y los logs, tal como se diseñó.

- **2026-07-27 — Límite de concurrencia configurable + ProcessJobRunner
  documentado con honestidad: cuarto punto de la segunda evaluación de
  madurez post-8-etapas.** Antes, `ThreadJobRunner.submit()` lanzaba un
  hilo nuevo por cada trabajo, sin ningún límite -- nada impedía que la
  app intentara correr, por ejemplo, 10 extracciones/fragmentaciones a
  la vez si algo (un script, un futuro trabajo por lote) las lanzara
  todas juntas, compitiendo sin control por CPU/memoria/E-S. Además,
  `ProcessJobRunner` (pensado para trabajo realmente pesado en procesos
  separados) llevaba desde la Etapa 1 con un comentario ya
  desactualizado ("se implementa junto con el orquestador de ingesta,
  Etapa 3") que nunca se cumplió ni se corrigió, aunque las etapas 3-8
  ya se completaron hace tiempo -- una brecha real que ni siquiera
  aparecía documentada en "Limitaciones conocidas".
  Lo nuevo: `ThreadJobRunner(max_concurrent_jobs=None)` -- `None` es
  sin límite (comportamiento exacto de antes de este ítem); un entero
  usa un `threading.Semaphore` que el hilo de cada trabajo debe adquirir
  antes de pasar de `JobStatus.PENDIENTE` a PREPARANDO/EJECUTANDO
  (`submit()` sigue regresando de inmediato siempre, sin bloquear al
  llamador -- el límite vive del lado del hilo en segundo plano, nunca
  del lado de quien envía el trabajo). Es independiente y compatible
  con la deduplicación por `key` del ítem anterior: ambos mecanismos
  conviven en el mismo `_runner()`. `AppSettings.max_concurrent_jobs`
  (`app/configuration.py`) expone la opción con el mismo patrón ya
  usado para `embedding_profile`: parámetro explícito a
  `load_settings`/`bootstrap`/`app.lifecycle.start` > variable de
  entorno `RAGSTUDIO_MAX_CONCURRENT_JOBS` > `None` por defecto.
  `ProcessJobRunner.submit` sigue lanzando `NotImplementedError` (nadie
  lo llama todavía), pero su docstring y su mensaje de error ahora
  explican con honestidad qué falta y por qué: todo el trabajo pesado
  real de esta app corre hoy en hilos (no procesos), lo cual funciona
  en la práctica porque buena parte de ese trabajo libera el GIL de
  Python, pero implementar procesos de verdad requeriría resolver cómo
  cruzar `application`/`domain` entre procesos (sesiones de SQLAlchemy
  no son picklables) -- cierra la nota desactualizada sin fingir que se
  resolvió el problema de fondo.
  Pruebas: 4 pruebas nuevas en `test_job_runner_non_blocking.py` (sin
  límite todos arrancan de inmediato; con límite=1 el segundo trabajo
  se queda PENDIENTE hasta que el primero libera su cupo; el límite
  convive con la deduplicación por `key` del ítem anterior), más 6 en
  el nuevo `tests/integration/test_max_concurrent_jobs_configuration.py`
  (mismo patrón de opción que `test_embedding_profile_configuration.py`:
  default, parámetro explícito, variable de entorno, precedencia, y
  `bootstrap` construyendo un `ThreadJobRunner` limitado o sin límite
  según corresponda). Total: 422 pruebas unitarias/smoke en verde
  (antes 419), cero regresiones. Verificado también en vivo contra
  `app/bootstrap.py` end-to-end: con `max_concurrent_jobs=1`, un
  segundo trabajo enviado mientras el primero ocupa el único cupo se
  queda de verdad en `JobStatus.PENDIENTE` y arranca en cuanto el
  primero libera el cupo, tal como se diseñó.

- **2026-07-27 — Deduplicación de trabajos por clave en ThreadJobRunner:
  tercer punto de la segunda evaluación de madurez post-8-etapas.**
  Antes, `ThreadJobRunner.submit()` lanzaba un hilo nuevo sin cola,
  semáforo ni registro de "qué recurso ya tiene un trabajo en curso" --
  nada impedía, a nivel del runner, lanzar dos trabajos sobre la misma
  fuente (extraer y fragmentar a la vez, por ejemplo) en carrera real.
  Cada panel de la UI ya se autolimitaba con su propio `_active_job`
  (un solo trabajo activo por panel a la vez), pero esa es una
  convención de cada pantalla, no una garantía de la capa correcta:
  nada la exigía para quien llamara a `application` directamente (un
  script, una prueba, un futuro trabajo por lote).
  Lo nuevo: `ThreadJobRunner.submit(fn, key=None)` acepta una clave
  lógica opcional; si se pasa, se reserva de inmediato (antes de lanzar
  el hilo, bajo el mismo lock que ya protegía `self._jobs`) y se libera
  en un `finally` cuando el trabajo termina (completado, cancelado o
  fallido) -- un segundo `submit` con la misma clave mientras la
  reserva sigue activa lanza `JobAlreadyRunningError` de inmediato, en
  vez de dejar correr dos trabajos en carrera. Sin `key` (el valor por
  defecto), el comportamiento es exactamente el de antes de este ítem:
  cero deduplicación, para no romper ningún llamador existente.
  `application.jobs_facade.BackgroundJobs.submit_task`/
  `is_key_running` exponen lo mismo hacia `application`. La UI
  (`ui/ingestion/panel.py`, `ui/quality/panel.py`) ya pasa `key` en los
  trabajos que escriben datos: `f"ingesta:{project_id}:{source_id}"`
  compartida entre extraer/fragmentar/indexar una misma fuente (para
  que se excluyan mutuamente entre sí, no solo cada operación consigo
  misma), y `f"pipeline:{project_id}"`/`f"evaluacion:{project_id}"` a
  nivel de proyecto para el pipeline reproducible y una corrida de
  evaluación; búsqueda y comparador de modelos, al ser de solo lectura,
  no llevan `key`. Un nuevo helper `IngestionPanel._submit_job` evita
  duplicar el manejo de `JobAlreadyRunningError` en los 4 sitios de esa
  pestaña que ahora usan `key`.
  Alcance deliberadamente acotado (ver "Limitaciones conocidas"): el
  pipeline reproducible reserva su propia clave de proyecto pero no la
  de cada fuente individual que procesa por dentro, así que en teoría
  un trabajo manual sobre una fuente todavía podría solaparse con un
  pipeline procesando esa misma fuente en ese instante -- cerrar esa
  brecha del todo queda para una iteración posterior si un caso real lo
  justifica.
  Pruebas: 5 pruebas nuevas en `tests/smoke/test_job_runner_non_blocking.py`
  (sin key se comporta como antes; misma key mientras corre lanza
  `JobAlreadyRunningError`; la clave se libera al completar y al fallar,
  permitiendo un nuevo `submit` después; claves distintas corren de
  verdad en paralelo sin esperarse), más 3 en el nuevo
  `tests/unit/application/test_jobs_facade.py` (mismo comportamiento a
  través de `BackgroundJobs`). Total: 419 pruebas unitarias/smoke en
  verde (antes 411), cero regresiones.

- **2026-07-27 — CredentialStore para secretos de complementos: segundo
  punto de la segunda evaluación de madurez post-8-etapas.** Antes,
  `Plugin.config` (donde vive, por ejemplo, la API key de un proveedor
  de embeddings/LLM externo registrado como complemento) se serializaba
  siempre con `json.dumps` y se guardaba así, en texto plano, en
  `application.db` -- ADR-001 (sección 12) exige explícitamente que
  ninguna credencial viaje en texto plano, y no existía ningún puerto
  ni adaptador para evitarlo.
  Lo nuevo: un puerto `CredentialStore` (`domain.plugins.ports`) con
  `set_secret`/`get_secret`/`delete_secret`, y un adaptador real
  `KeyringCredentialStore` (`infrastructure.security.
  keyring_credential_store`) sobre la librería `keyring`, que delega en
  el almacén seguro nativo del sistema operativo (Windows Credential
  Locker, Keychain de macOS, Secret Service de D-Bus en Linux) sin
  manejar cifrado directamente. `RegisterPlugin` (comando de
  `application.plugins.commands`) recibe este almacén como capacidad
  opcional (`credential_store: Optional[CredentialStore] = None`,
  mismo patrón que `file_store`/`release_packager`/`token_counter` de
  ítems anteriores): al registrar un complemento, cualquier clave de
  `config` cuyo nombre parezca sensible (`domain.plugins.entities.
  is_sensitive_config_key`: contiene "key", "secret", "token",
  "password", "credential" o "contraseña", sin distinguir mayúsculas)
  se guarda en el almacén bajo una clave estable
  (`credential_key(code, campo)`) y se reemplaza en `Plugin.config`
  (lo que sí se persiste en `application.db`) por el marcador
  `CREDENTIAL_STORE_PLACEHOLDER` -- así queda claro que el campo tiene
  un valor configurado, sin exponerlo. Un nuevo
  `PluginService.resolve_plugin_config(plugin)` (respaldado por
  `ResolvePluginConfig`, `application.plugins.queries`) hace el camino
  inverso cuando haga falta el valor real (por ejemplo, para quien en
  el futuro construya de verdad una instancia del complemento a partir
  de su `entry_point`).
  Sin `credential_store` configurado, o si el almacén falla porque no
  hay backend real disponible (`CredentialStoreError` --
  típicamente un entorno headless sin sesión gráfica ni daemon de
  credenciales, confirmado en este entorno de construcción:
  `keyring.get_keyring()` resuelve a `keyring.backends.fail.Keyring`),
  el valor se guarda tal como llegó (texto plano) y se registra una
  advertencia clara en el log -- mismo criterio de degradación segura
  que `TokenizerError`/`EmbeddingProviderError` para dependencias
  externas: nunca fue ni es un requisito para usar el resto de la app,
  y no rompe el registro del complemento.
  Se agregó `keyring>=24.0` a las dependencias del proyecto.
  Pruebas: 3 pruebas unitarias nuevas en `test_plugin_entities.py`
  (detección de claves sensibles y namespacing de `credential_key` por
  `code`), 6 en `test_plugin_service.py` (externalización exitosa,
  sin almacén configurado, con almacén que falla, claves no sensibles
  nunca llegan al almacén, resolución de vuelta con y sin almacén). Se
  agregó además `tests/integration/test_keyring_credential_store.py`
  (mismo patrón que `test_fastembed_provider.py`/
  `test_tiktoken_counter.py`): 3 pruebas contra `keyring` real, que se
  omiten explícitamente con motivo claro cuando no hay backend del
  sistema operativo disponible (como en este entorno, confirmado), y 3
  pruebas adicionales sin backend real (con dobles vía `monkeypatch`)
  que sí corren siempre y verifican los mensajes de error de
  `CredentialStoreError`, incluida la distinción entre "la clave nunca
  existió" (no debe fallar, `delete_secret` es idempotente) y "el
  backend está roto de verdad" (sí debe propagar el error). Total: 411
  pruebas unitarias/smoke en verde (antes 391), cero regresiones en
  `test_plugin_repositories.py`/`test_quality_repositories.py`.
  Verificado también en vivo contra `app/bootstrap.py` end-to-end:
  registrar un complemento PROVEEDOR con `api_key` en su config no
  rompe el registro y cae de vuelta a texto plano con una advertencia
  clara en el log, tal como se diseñó, en este entorno sin backend real
  de `keyring`.

- **2026-07-27 — SQLite en modo WAL + busy_timeout: primer punto de la
  segunda evaluación de madurez post-8-etapas.** Antes,
  `infrastructure.database.engine.make_sqlite_engine` abría cada base
  SQLite (global o por proyecto) con el modo de journaling por defecto
  (rollback journal) y sin `busy_timeout` explícito, pese a que
  `check_same_thread=False` ya reconocía que la misma base se abre desde
  varios hilos a la vez (la UI y `workers.jobs.ThreadJobRunner`). Con
  ese modo por defecto, una escritura concurrente real (por ejemplo,
  fragmentar una fuente en segundo plano mientras se guarda un cambio de
  metadatos de otra) podía producir `OperationalError: database is
  locked` en vez de esperar y reintentar -- no era un riesgo teórico,
  es el patrón de uso normal de la app.
  Lo nuevo: cada conexión nueva ejecuta `PRAGMA journal_mode=WAL` (los
  lectores no bloquean al escritor ni viceversa) y `PRAGMA
  busy_timeout=30000` (si de todos modos hay contención momentánea,
  reintentar en silencio hasta 30s en vez de fallar de inmediato), vía
  un listener `event.listens_for(engine, "connect")`; ambos parámetros
  son configurables (`busy_timeout_ms`), con 30s como valor por defecto.
  Efecto secundario esperado y ya resuelto: el modo WAL crea archivos
  sidecar `project.db-wal`/`project.db-shm` junto a `project.db` --
  `FilesystemProjectPackager.export` (el empaquetador `.agentproj`)
  ahora hace `PRAGMA wal_checkpoint(TRUNCATE)` sobre `project.db` antes
  de recorrer el directorio del proyecto (para que el contenido del WAL
  quede volcado al archivo principal antes de empaquetar) y además
  excluye por si acaso cualquier `-wal`/`-shm`/`-journal` residual del
  recorrido -- esos sidecars son un detalle interno de la conexión
  abierta, nunca parte del contenido lógico exportable del proyecto.
  Pruebas: `tests/integration/test_sqlite_engine_concurrency.py` (nuevo)
  confirma contra archivos `.db` reales que el modo WAL queda activo,
  que `busy_timeout` queda configurado con el valor pedido (por defecto
  y personalizado), y que 6 hilos escribiendo de verdad al mismo archivo
  (150 inserciones en total, cada hilo con su propio engine, igual que
  hace cada operación real de repositorio) no lanzan "database is
  locked". Se corrió además toda la suite existente (511
  pruebas unit/smoke/integración, incluyendo las 4 líneas de migraciones
  Alembic y los 3 escenarios de export/import `.agentproj` entre dos
  instalaciones) para confirmar cero regresiones tras el cambio de modo
  de journaling.

- **2026-07-27 — Tokenizador real para fragmentación: séptimo punto de
  la evaluación de madurez post-8-etapas.** Antes, `FragmentSource`
  medía el "tamaño" de cada fragmento contando palabras separadas por
  espacios (`domain.ingestion.splitting.word_count`) -- una
  aproximación razonable pero distinta de cómo un modelo de embeddings
  realmente cuenta tokens (subpalabras, puntuación como token propio,
  etc.), lo que podía hacer que fragmentos "del tamaño configurado" en
  palabras resultaran más grandes o más chicos de lo esperado en tokens
  reales una vez enviados al proveedor de embeddings.
  Lo nuevo: un puerto `TokenCounter` (`domain.ingestion.ports`) con un
  único método `count_tokens(text) -> int`, y un adaptador real
  `TiktokenCounter` (`infrastructure.tokenization.tiktoken_counter`)
  que usa la librería `tiktoken` (codificación `cl100k_base`, la misma
  familia BPE que los modelos GPT/embeddings de OpenAI) con carga
  perezosa de la codificación en el primer uso. `FragmentSource` recibe
  este contador como capacidad opcional (`token_counter: Optional[TokenCounter] = None`,
  mismo patrón que `file_store` y `release_packager` de ítems
  anteriores); al ejecutar una fragmentación hace una única llamada de
  "calentamiento" para detectar si el tokenizador está disponible
  (`_resolve_count_tokens`) y, si falla (`TokenizerError` -- típicamente
  por no tener conexión para la descarga inicial de la codificación, el
  mismo tipo de limitación ya aceptada para `FastEmbedEmbeddingProvider`
  y sus modelos de Hugging Face), cae de vuelta a `word_count` sin
  romper la corrida; si el tokenizador se vuelve disponible en una
  corrida posterior (por ejemplo tras recuperar la conexión), la app se
  autorepara sola, sin reinicio, porque la detección se repite en cada
  ejecución en vez de recordarse permanentemente.
  El algoritmo de ventana deslizante de `split_by_size` (y también
  `merge_small_spans` y `split_by_tables`) se rediseñó para trabajar
  por presupuesto de tokens en vez de por conteo de palabras: se
  calcula el costo en tokens de cada palabra una sola vez
  (`count_tokens` inyectable, con `word_count` como valor por defecto
  que preserva el comportamiento de siempre) y luego la ventana crece
  mientras la suma acumulada no supere `target_tokens`, sin partir
  nunca una palabra; el solape se calcula caminando hacia atrás desde
  el final de la ventana hasta acumular `overlap_tokens`. Se verificó
  matemáticamente (y con toda la suite previa de pruebas, sin cambios,
  en verde) que este nuevo algoritmo es equivalente al anterior cuando
  `count_tokens = word_count`.
  `app/bootstrap.py` conecta `TiktokenCounter()` como el `token_counter`
  real de `IngestionService`/`FragmentSource`. Se agregó `tiktoken>=0.7`
  a las dependencias del proyecto.
  Pruebas: 8 pruebas unitarias nuevas (4 en `test_splitting.py` sobre el
  algoritmo de ventana por presupuesto de tokens con un contador falso
  distinguible de `word_count`, 4 en `test_ingestion_service.py` sobre
  el cableado de `FragmentSource` incluyendo el mecanismo de caída de
  vuelta a `word_count`), para un total de 391 pruebas unitarias/smoke
  en verde. Se agregó además `tests/integration/test_tiktoken_counter.py`
  (mismo patrón que `test_fastembed_provider.py`): 3 pruebas contra el
  `tiktoken` real, que se omiten explícitamente con motivo claro cuando
  no hay red para la descarga inicial de la codificación (como en este
  entorno de desarrollo, confirmado -- `pip install tiktoken` funciona,
  pero `tiktoken.get_encoding("cl100k_base")` falla por la restricción
  de red del entorno), y 3 pruebas adicionales sin red real (con dobles
  vía `monkeypatch`) que sí corren siempre y verifican los mensajes de
  error de `TokenizerError` y que la codificación se carga una sola vez.
  Verificado también en vivo contra `app/bootstrap.py` end-to-end
  (registrar fuente, extraer, fragmentar): la fragmentación produce
  fragmentos con `token_count` coherente sin lanzar excepción, cayendo
  de vuelta a `word_count` en este entorno sin red, tal como se diseñó.

- **2026-07-27 — Paquete exportable de entregables de liberación:
  sexto punto de la evaluación de madurez post-8-etapas.** Antes, los
  8 entregables formales del documento maestro solo existían como un
  dict JSON inline en `ReleaseRecord.deliverables_report` -- para
  compartirlos fuera de la app (con un cliente, un auditor, otro
  equipo) no había más opción que consultar el historial de
  liberaciones dentro de RAG STUDIO. El registro en base de datos
  sigue siendo el auditable de verdad; lo nuevo es poder volcarlo a un
  `.zip` real en disco bajo pedido, sin recalcular nada.
  - `domain.release.ports.ReleasePackager` (puerto nuevo):
    `export(record, destination_path) -> str`, capacidad opcional
    (igual patrón que `source_file_store`/`embedding_provider_factory`)
    -- sin ella, `ReleaseService.export_deliverables_package` lanza un
    `RuntimeError` claro en vez de fallar en silencio o con un
    `AttributeError` críptico.
  - `infrastructure.filesystem.release_packager.FilesystemReleasePackager`:
    escribe `manifest.json` (identificación + evidencia + si las
    compuertas se cumplieron), `dictamen.txt` (texto plano),
    `checklist.json` (cada compuerta con su motivo) y un
    `entregables/<clave>.json` por cada uno de los 8 entregables ya
    compilados -- deliberadamente SIN el manifiesto de integridad
    (hashes sha256) que sí usa `.agentproj`: este paquete es un
    entregable de lectura para humanos y auditoría externa, no algo
    que se vuelva a importar como proyecto.
  - `ExportDeliverablesPackage` (application, nuevo) +
    `ReleaseService.export_deliverables_package(project_id, record_id,
    destination_path)`: busca el `ReleaseRecord` por id (cualquiera del
    historial, no solo el más reciente) y delega en el packager.
  - `app/bootstrap.py` construye `FilesystemReleasePackager()` y lo
    pasa a `ReleaseService`.
  - UI: botón nuevo "Exportar entregables…" en la pestaña Liberación,
    habilitado sobre la liberación que se esté mostrando (recién
    solicitada o abierta con doble clic desde el historial) -- usa
    `QFileDialog.getSaveFileName` con filtro `*.zip`, mismo patrón que
    "Exportar proyecto" en la pestaña Proyectos.
  - Verificado de extremo a extremo contra `app/bootstrap.py` real: un
    `request_release` real seguido de `export_deliverables_package`
    produce un `.zip` legible con los 11 archivos esperados (manifest,
    dictamen, checklist, 8 entregables).
  - Pruebas nuevas: 3 en `test_release_service.py` (delega en el
    packager configurado, falla claro sin packager configurado, falla
    para un record_id inexistente) con un `InMemoryReleasePackager`
    nuevo en `fakes_release.py`; 1 en `test_release_repositories.py`
    (escritura real de un `.zip` con `zipfile`, verificando cada
    archivo interno byte a byte). 383 pruebas unitarias en total
    (más las de integración), todas verdes.

- **2026-07-27 — Historial de cambios en metadatos y extracciones:
  quinto punto de la evaluación de madurez post-8-etapas.** Antes,
  tanto `source_metadata_value` como `extraction_record` eran upsert
  puro: sobrescribir un valor de metadatos, o volver a extraer una
  fuente, borraba en silencio cualquier rastro de lo que había antes
  -- sin poder responder "¿cuál era el valor anterior, y cuándo
  cambió?" ni "¿qué decía la extracción antes de la última corrida?".
  El valor/extracción VIGENTE sigue siendo upsert (una sola fila, para
  lecturas rápidas en el resto de la app); lo nuevo son dos tablas de
  solo inserción, append-only, que nunca se actualizan ni se borran.
  - `domain.metadata.entities.MetadataValueChange` (dominio nuevo):
    `previous_value`/`new_value`/`changed_at` por cada vez que
    `SourceMetadataRepository.save_value` cambia de verdad el valor
    vigente -- un guardado que repite el mismo valor no genera ruido
    (`previous_value=None` marca la primera asignación).
  - `SourceMetadataRepository.list_value_history(project_id, source_id,
    field_id=None)` (puerto nuevo), más reciente primero.
  - `ExtractionRepository.list_history(project_id, source_id)` (puerto
    nuevo): a diferencia del historial de metadatos, aquí se registra
    CADA llamada a `save()`, incluida la primera -- cada corrida de
    extracción es un evento real por sí mismo (método usado,
    advertencias propias), no algo que tenga sentido filtrar por
    "¿cambió el texto?".
  - Infraestructura: `MetadataValueChangeRecord`/
    `ExtractionRecordHistoryRecord` (tablas nuevas
    `metadata_value_change`/`extraction_record_history`, migración
    `0010_change_history`); `SqlAlchemySourceMetadataRepository.save_value`
    y `SqlAlchemyExtractionRepository.save` agregan la fila de
    historial dentro de la misma transacción que el upsert de
    siempre, sin cambiar su comportamiento vigente.
  - `MetadataService.list_value_history`/
    `IngestionService.list_extraction_history` (fachadas nuevas) y dos
    botones nuevos ("Ver historial de cambios" en Metadatos → Valores
    por fuente; "Ver historial de extracciones" en Ingesta →
    Extracción) que muestran el historial en un diálogo de solo
    lectura -- sin esto, la auditoría solo habría sido accesible desde
    application directamente (pruebas o scripts), nunca desde la
    interfaz.
  - Verificado de extremo a extremo contra `app/bootstrap.py` real:
    dos cambios de un campo de metadatos y dos extracciones sucesivas
    de la misma fuente (con contenido externo modificado entre
    medio) producen exactamente 2 entradas de historial cada una,
    persistidas en `project.db`.
  - Pruebas nuevas: 5 en `test_metadata_service.py` + 3 en
    `test_ingestion_service.py` (unitarias, con
    `InMemorySourceMetadataRepository`/`InMemoryExtractionRepository`
    actualizados para llevar su propio historial en memoria); 1 en
    `test_documents_metadata_integration.py` + 2 en
    `test_ingestion_repositories.py` (SQLite real vía Alembic). 380
    pruebas unitarias en total (más las de integración), todas verdes.

- **2026-07-27 — Copiar el archivo original al registrar una fuente:
  cuarto punto de la evaluación de madurez post-8-etapas.** Antes, la
  extracción (`ExtractSourceText`) leía siempre `Source.location`
  directamente -- si el archivo externo original se movía, se
  renombraba o se borraba después de registrar la fuente, cualquier
  extracción o re-extracción posterior fallaba, aunque el contenido ya
  se hubiera usado antes con éxito. El directorio `sources/original/`
  ya estaba reservado en el layout desde Etapa 1
  (`infrastructure/filesystem/paths.py`) pero nada escribía ahí
  todavía (limitación documentada explícitamente, ver bitácora
  anterior).
  - `domain.documents.ports.SourceFileStore` (puerto nuevo):
    `store_original(project_id, source_id, external_path) -> str`,
    capacidad opcional (igual patrón que `embedding_provider_factory`
    en `RagService`/`ocr_engine` en `PdfTextExtractor`) -- sin ella,
    cero cambio de comportamiento.
  - `infrastructure.filesystem.source_file_store.FilesystemSourceFileStore`:
    implementación real con `shutil.copy2` hacia
    `<project_dir>/sources/original/<source_id><extensión>`; un fallo
    de copia (archivo no encontrado, sin permisos) se propaga tal cual
    -- decidir qué hacer ante ese fallo es responsabilidad de
    application, no de este puerto.
  - `Source.original_copy_path: Optional[str] = None` (entidad nueva):
    `None` para fuentes de tipos sin archivo real (api/base_de_datos),
    con `location` vacía, o cuando la copia falló -- en cualquiera de
    esos casos la extracción sigue leyendo `location` directamente,
    exactamente el comportamiento de siempre.
    `domain.documents.entities.NON_FILE_SOURCE_TYPES` (constante
    compartida) documenta esa distinción en un solo lugar.
  - `RegisterSource`/`UpdateSourceDetails` (application) intentan la
    copia -- al registrar, y al corregir la ubicación mientras siga
    sin bloquear (antes de la primera extracción) -- y cualquier
    excepción al copiar se atrapa en silencio: registrar o editar una
    fuente nunca debe fallar por un problema al copiar bytes.
  - `ExtractSourceText.execute` ahora lee de
    `source.original_copy_path or source.location` -- una sola línea
    de cambio que resuelve el problema real: una vez que existe la
    copia local, ni la extracción inicial ni ninguna re-extracción
    futura dependen de que el archivo externo original siga
    existiendo en el mismo lugar.
  - Migración `0009_source_original_copy` (nueva columna nullable en
    `source`, sin backfill posible ni necesario: NULL tiene el mismo
    significado que el comportamiento de antes de este cambio).
  - Verificado de extremo a extremo contra `app/bootstrap.py` real
    (no solo con dobles de prueba): registrar una fuente TXT con un
    archivo externo real produce una copia legible en
    `sources/original/`, persistida en `project.db`.
  - Pruebas nuevas: 7 en `tests/unit/application/test_document_service.py`
    (copia al registrar, sin `file_store` no cambia nada, se omite
    para api/base_de_datos, se omite con `location` vacía, un fallo de
    copia no tumba el registro, re-copia al cambiar `location`, no
    vuelve a copiar si `location` no cambió) con un
    `InMemorySourceFileStore` nuevo en `fakes_documents.py`; 3 en
    `tests/integration/test_source_file_store.py` (copia real con
    `shutil`, propagación de `OSError` para un archivo inexistente, y
    el flujo completo `DocumentService` + SQLite real, incluyendo
    borrar el archivo externo después y confirmar que la copia local
    sigue intacta). 376 pruebas en total (366 unitarias + 3 de
    integración nuevas + el resto de integración ya existente), todas
    verdes.

- **2026-07-27 — Avisos tempranos (no bloqueantes) de compuertas de
  Liberación por pestaña: tercer punto de la evaluación de madurez
  post-8-etapas.** Antes, la única forma de saber si una compuerta de
  Etapa 7 ("Metadatos", "Fragmentación", "Pipeline reproducible",
  "Índice y recuperación", "Diseño conversacional", "Calidad") se
  cumplía era ir hasta la pestaña Liberación y solicitar una
  evaluación -- sin esa visita, un usuario podía trabajar varias
  sesiones en Metadatos o Calidad sin enterarse de que, por ejemplo,
  todavía no había ningún caso de prueba en el banco. No se agregó
  ningún bloqueo nuevo (alcance deliberadamente descartado, ver
  "Limitaciones conocidas"): las compuertas siguen evaluándose de
  verdad solo al solicitar una liberación real; lo nuevo es
  visibilidad, en una línea, dentro de cada pestaña relevante.
  - `ReleaseService.evaluate_gates(project_id)` (Etapa 7) ya era una
    fachada pública read-only suficiente -- cero código nuevo de
    dominio o de aplicación para este ítem, solo interfaz.
  - `ui/release/gate_status_logic.py` (nuevo, sin PySide6 -- mismo
    criterio que `ui/ingestion/search_highlighting.py`): `find_gate()`
    y `gate_status_text()`, lógica pura y probada directamente.
  - `ui/release/gate_status.py` (nuevo): `GateStatusLabel(QLabel)`,
    con `refresh(release_service, project_id)` envuelto en
    `try/except` -- un fallo al evaluar (p. ej. otra etapa sin
    configurar todavía) nunca debe tumbar la pestaña, solo se muestra
    un mensaje neutral.
  - Conectado en las 4 pestañas correspondientes: `MetadataPanel`
    (compuerta "Metadatos", refrescada en `set_active_project` y tras
    crear el esquema o agregar/editar un campo); `IngestionPanel`
    (las 3 compuertas que concentra: "Fragmentación", "Pipeline
    reproducible", "Índice y recuperación" -- refrescadas en
    `set_active_project`, tras guardar una política de fragmentación,
    tras una corrida de pipeline y tras indexar); `ConversationalPanel`
    (compuerta "Diseño conversacional", refrescada en
    `set_active_project` y tras activar/desactivar una intención o un
    guardrail); `QualityPanel` (compuerta "Calidad", refrescada en
    `set_active_project`, tras crear un caso de prueba y tras terminar
    una corrida de evaluación).
  - Pruebas nuevas: `tests/unit/ui/test_gate_status_logic.py` (5
    pruebas de la lógica pura). 359 pruebas unitarias en total, todas
    verdes. `GateStatusLabel` en sí (la subclase de `QLabel`) no tiene
    prueba directa por la misma razón de siempre en este proyecto: el
    sandbox de construcción no tiene `libEGL`/servidor gráfico (ver
    `tests/smoke/test_ui_construction.py`), así que la superficie con
    PySide6 se mantiene deliberadamente delgada (un wrapper fino sobre
    la lógica ya probada) para minimizar lo que queda sin cubrir aquí.

- **2026-07-27 — Complementos EVALUADOR (Etapa 8) ya se invocan de
  verdad en `RunEvaluation` (Etapa 6): segundo punto de la evaluación de
  madurez post-8-etapas.** Desde que se construyó Etapa 8, un
  `CustomEvaluator` se podía registrar y validar, pero `RunEvaluation`
  nunca lo invocaba durante una corrida real -- la brecha clásica entre
  "mecanismo construido" y "mecanismo conectado".
  - `RunEvaluation.__init__` acepta ahora `plugin_repository`
    (`Optional[PluginRepository] = None`, capacidad opcional igual que
    `embedding_provider_factory` en `RagService`): sin él, cero cambio de
    comportamiento -- todas las pruebas existentes lo confirman sin
    tocarse.
  - `_load_custom_evaluators()`: resuelve, una sola vez por corrida (no
    por caso de prueba), los complementos EVALUADOR activos, cargando y
    validando cada uno con `domain.plugins.loader.load_and_validate` e
    instanciándolo. Un complemento roto (entry_point inválido, no
    implementa el contrato, falla al instanciar) se descarta para esa
    corrida sin abortar el resto -- la validación explícita ya vive en
    Complementos ("Validar seleccionado"), `RunEvaluation` no vuelve a
    diagnosticar la salud de un complemento.
  - Por cada caso de prueba, además de los criterios integrados de
    siempre, se llama a `evaluator.evaluate(trace, test_case)` de cada
    evaluador cargado. Un rechazo (`aprobado=False`) cuenta como
    AMARILLO ("requiere revisión") -- el contrato no expone una noción
    de severidad propia, así que se trata igual que el resto de
    discrepancias "blandas". Si el propio `evaluate()` lanza una
    excepción en tiempo de ejecución, se reporta como discrepancia
    (AMARILLO) sin tumbar el resto del caso -- mismo aislamiento de
    fallas que el resto de `RunEvaluation`.
  - `app/bootstrap.py`: la construcción de `plugin_repository`/
    `plugin_service` (Etapa 8) se movió antes de `quality_service`
    (Etapa 6) en el orden del archivo, porque ahora existe una
    dependencia real entre ambos -- documentado explícitamente en el
    comentario para que no se lea como un desorden accidental.
  - Pruebas nuevas: 6 en `tests/unit/application/test_run_evaluation.py`
    (rechazo baja a AMARILLO, complemento desactivado se ignora,
    entry_point roto se ignora sin tumbar la corrida, excepción en
    tiempo de ejecución se reporta sin tumbar el caso, aprobación activa
    no cambia el veredicto, y sin `plugin_repository` el comportamiento
    es idéntico al de antes). Se agregaron 3 `CustomEvaluator` de prueba
    reales e importables en `tests/unit/application/fakes_quality.py`
    (`AlwaysRejectCustomEvaluator`, `AlwaysApproveCustomEvaluator`,
    `BrokenCustomEvaluator`) -- necesarios porque `load_and_validate`
    hace un import real por `entry_point`, no admite un doble en
    memoria. 354 pruebas unitarias en total, todas verdes.

- **2026-07-27 — Emparejamiento HÍBRIDO de intención (léxico + semántico):
  primer punto de la evaluación de madurez post-8-etapas.** Con las 8
  etapas completas, se hizo un análisis honesto de qué procesos seguían
  en nivel MVP pese a estar "terminados" -- el emparejamiento de
  intención (`domain.conversational.intent_matching`) salió como el de
  mayor impacto real: el heurístico léxico de Jaccard no reconoce
  paráfrasis ni sinónimos ("quiero darme de baja" vs. "cómo suspendo mi
  inscripción" no comparten ni una palabra). La corrección reutiliza el
  mismo `EmbeddingProvider` que ya tiene `RagService` desde Etapa 4 (un
  solo modelo de embeddings por proyecto, no uno nuevo) en vez de
  reemplazar el heurístico léxico:
  - `match_intent(query_text, intents, embed_query=None, embed_texts=None)`:
    los dos parámetros nuevos son opcionales -- sin ellos, el
    comportamiento es idéntico byte a byte al heurístico léxico de
    antes (las pruebas existentes no se tocaron). Con ellos, el score
    final por intención es el MÁXIMO entre la similitud léxica de
    Jaccard y una similitud semántica de coseno contra los mismos
    ejemplos positivos/negativos (misma fórmula "positivo menos
    negativo" que el lado léxico) -- tomar el máximo, no un promedio,
    garantiza que la combinación híbrida nunca reconoce MENOS que el
    léxico solo, únicamente puede encontrar coincidencias adicionales.
  - Degradación silenciosa: si `embed_query`/`embed_texts` lanzan
    `EmbeddingProviderError` (sin red para el modelo, por ejemplo), se
    seguía con el score léxico -- Diseño conversacional sigue siendo
    usable sin conexión, la dependencia de red real solo entra cuando
    de verdad hay que buscar en el índice (acción RESPONDER).
  - `RagService` (Etapa 4) expone ahora `embed_query`/`embed_texts` como
    métodos públicos de la fachada (delegan al `EmbeddingProvider` que
    ya recibía en el constructor) para que `SimulateConversation`
    (Etapa 5) pueda reusarlos sin que `application.conversational`
    dependa de `infrastructure` directamente.
  - Pruebas nuevas: 4 en `tests/unit/domain/test_intent_matching.py`
    (coincide sin overlap léxico, se degrada sin propagar la excepción,
    sigue devolviendo `None` sin overlap real, y el comportamiento sin
    embebedor es idéntico al de antes). Se detectó y corrigió un caso
    real durante la propia escritura de pruebas: el fake de embeddings
    compartido (`FakeEmbeddingProvider`, vectores de ruido derivados de
    un hash del texto completo) produce coincidencias falsas en el
    emparejamiento semántico porque su "similitud" no tiene relación
    real con el significado -- se agregó
    `WordOverlapFakeEmbeddingProvider` (índice de palabra por orden de
    aparición, sin colisión) específicamente para
    `tests/unit/application/test_simulate_conversation.py`, sin tocar
    el fake original que usan otras 12 suites de pruebas de RAG. 348
    pruebas unitarias en total, todas verdes.

- **2026-07-27 — Revertido un cambio roto en `run_app.py` y agregada una
  pantalla de bienvenida real con `ui/LOGO.png`.** Al revisar el código
  se detectó que `run_app.py` había sido modificado fuera de este ciclo
  de trabajo con un intento de mostrar el logo: creaba un `QMainWindow`
  con el logo como contenido central, pero nunca lo mostraba
  (`window.show()` faltante) y además llamaba a `ui.app.main()`, que a
  su vez intenta crear una **segunda** `QApplication` -- PySide6 no lo
  permite, así que el arranque real habría fallado. Se revirtió
  `run_app.py` a su forma simple de siempre (solo delega a
  `ui.app.main()`) y se implementó la pantalla de bienvenida en el
  lugar correcto:
  - `ui/app.py`: nueva función `_show_splash(app)` que carga
    `ui/LOGO.png` con `QPixmap`, lo escala a 480px de ancho y lo muestra
    en un `QSplashScreen` **antes** de correr `app.lifecycle.start()`
    (que hace el bootstrap: migraciones, conexión a SQLite, etc.). El
    splash se cierra justo cuando la ventana principal ya está
    construida (`splash.finish(window)`), así que cubre exactamente el
    tiempo de arranque real, no un tiempo fijo arbitrario. Si el logo no
    existe o no puede leerse, se omite el splash sin interrumpir el
    arranque (no es un requisito duro para que la app funcione).
  - `tests/smoke/test_ui_construction.py`: se revirtió la prueba que
    había quedado ligada al diseño roto anterior
    (`test_run_app_creates_qapplication_before_widgets`, que esperaba
    que `run_app.py` creara la `QApplication` y llamara `app.exec()` por
    fuera) y se añadieron dos pruebas acordes al diseño correcto:
    `test_run_app_delegates_to_ui_app_main` y
    `test_splash_is_skipped_gracefully_when_logo_missing`.
  - 344 pruebas unitarias verdes tras el cambio; la prueba de humo de
    construcción de la ventana sigue omitiéndose en este entorno de
    verificación por falta de `libEGL` (limitación conocida y ya
    documentada, no relacionada con este cambio).
  - **Ajuste posterior — centrado y maximizado reales.** Se pidió
    además que el splash apareciera centrado y que la ventana principal
    abriera maximizada. Se agregó `_center_on_primary_screen()` en
    `ui/app.py` (centra el splash usando la geometría de la pantalla
    principal, pidiéndolo *después* de `show()`, no antes, porque varios
    gestores de ventanas ignoran `move()` sobre una ventana todavía no
    mapeada) y se cambió `window.show()` por `window.showMaximized()`.
    Aun así, en Ubuntu con sesión **Wayland** (la sesión por defecto al
    iniciar con GNOME en versiones recientes) el splash seguía
    apareciendo pegado a la esquina superior izquierda: Wayland prohíbe
    por protocolo que una aplicación posicione sus propias ventanas
    top-level -- no es un parámetro de Qt ni de esta app, es una
    restricción de seguridad/UX del compositor, la misma razón por la
    que `move()` no tiene efecto. Como Ubuntu incluye XWayland por
    defecto, `run_app.py` ahora detecta `XDG_SESSION_TYPE == "wayland"`
    y, solo si el usuario no fijó ya `QT_QPA_PLATFORM` por su cuenta,
    fuerza `QT_QPA_PLATFORM=xcb` antes de construir la `QApplication`,
    para que el centrado del splash y el maximizado de la ventana
    principal sí se apliquen.
  - **Segundo ajuste — el splash dejó de verse y el maximizado seguía
    fallando.** Al corregir el orden de las llamadas (maximizar antes de
    `splash.finish()`, como documenta y ejemplifica Qt) el logo dejó de
    verse por completo: con una base SQLite local el arranque completo
    (`app.lifecycle.start()` + construcción de `MainWindow`) puede tardar
    menos de lo que el ojo humano percibe, así que el splash se cerraba
    antes de pintarse una sola vez. Se agregó un mínimo de un segundo de
    visibilidad garantizada (bombeando el loop de eventos con
    `app.processEvents()` en vez de bloquear con un `sleep`) y se procesan
    eventos también justo después de `showMaximized()`, para darle tiempo
    al gestor de ventanas de aplicar el maximizado antes de cerrar el
    splash.
  - **Tercer ajuste — el splash ya se ve centrado, pero la ventana
    seguía sin maximizarse.** No todos los gestores de ventanas de Linux
    respetan `showMaximized()` como estado *inicial* de una ventana que
    nunca se ha mostrado; varios solo lo aplican como un cambio de estado
    sobre una ventana que ya está mapeada. Se cambió la secuencia en
    `ui/app.py` a `window.show()` (normal) → `app.processEvents()` (para
    que quede realmente mapeada) → `window.showMaximized()` →
    `app.processEvents()` de nuevo, y solo entonces `splash.finish(window)`.
  - **Cuarto ajuste — persistía sin maximizar; la terminal reveló la causa
    real.** El registro de arranque mostró `base_dir=.../snap/code/.../
    ragstudio`: la app se estaba lanzando desde el terminal integrado de
    un editor instalado vía snap, un entorno confinado donde el gestor de
    ventanas no siempre honra el hint EWMH nativo de "maximizada"
    (`showMaximized()` depende por completo de esa cooperación externa).
    Se agregó `_fill_primary_screen()` en `ui/app.py`: además de pedir
    `showMaximized()`, fija explícitamente `setGeometry()` de la ventana
    al área disponible de la pantalla principal -- así queda a pantalla
    completa sin depender de que el entorno respete el hint nativo.
  - **Quinto ajuste — seguía sin llenar la pantalla; se pidió el
    diagnóstico real de la sesión.** Con un diagnóstico dirigido (tamaño y
    geometría disponible de cada pantalla vía `QApplication.screens()`) se
    confirmó una única pantalla de 1920x1080 sin escalado (`devicePixelRatio
    1.0`) -- se descartó un problema de cálculo de geometría o de DPI. La
    causa real era el **orden**: `_fill_primary_screen()` se llamaba antes
    de `showMaximized()`, y el propio `showMaximized()` podía pisar esa
    geometría correcta con su propio cálculo (más angosto) al resolverse
    contra XWayland. Se invirtió el orden (`showMaximized()` primero, la
    geometría manual al final, así prevalece) y se agregó un registro de
    diagnóstico permanente (`context.logger.info` con la geometría final y
    `isMaximized()`) para poder confirmar el resultado real desde la
    terminal en el siguiente arranque sin depender solo de capturas de
    pantalla.
  - **Sexto ajuste — el registro confirmó geometry=(0,32,1920,982) exacto,
    pero la captura de pantalla mostró la ventana centrada y más chica de
    todos modos.** Esa contradicción (Qt cree que la geometría es
    correcta, pero lo que se renderiza es otra cosa) apunta a que
    GNOME/Mutter reafirma su propia "colocación inteligente" (centrada,
    tamaño natural) por encima de un `setGeometry()`/`showMaximized()`
    pedido *después* de que la ventana ya se mostró una vez -- distinto de
    pedir el estado maximizado *antes* de la primera vez que se muestra,
    que si suele respetarse como estado inicial. Se simplificó
    `ui/app.py` a una sola secuencia limpia:
    `window.setWindowState(Qt.WindowState.WindowMaximized)` seguido de
    una única llamada a `window.show()`, sin resize()/showMaximized()/
    setGeometry() adicionales después que puedan entrar en conflicto con
    la política del gestor de ventanas.
  - **Séptimo ajuste — el registro develó el bug real: `isMaximized()=True`
    con `geometry=(0,0,1135,600)`.** Con el estado maximizado pedido antes
    del primer `show()`, GNOME/Mutter marcó la propiedad EWMH de
    "maximizada" como cierta (de ahí que Qt la reporte en `True`) pero
    nunca aplicó el resize real -- un bug conocido de Mutter con ventanas
    XWayland maximizadas *antes* de su primer mapeo (1135x600 es,
    justamente, el tamaño natural que tomaría la ventana sin maximizar,
    no el de la pantalla). El camino que Mutter sí maneja de forma
    confiable es el que corresponde a la interacción real de un usuario:
    ventana ya visible y luego solicitud de maximizar (como si alguien
    presionara el botón). Se volvió a `window.show()` → `app.processEvents()`
    → `window.showMaximized()` → `app.processEvents()`, sin fijar el estado
    antes del primer show ni corregir la geometría a mano después.
  - **Octavo ajuste — resultado bit por bit idéntico al anterior pese al
    cambio de orden.** El registro repitió, con esta secuencia
    "corregida", el mismo `geometry=(0,0,1135,600) isMaximized=True`
    exacto. Que dos secuencias de código distintas den el mismo resultado
    exacto descarta una condición de carrera resoluble intercalando más
    `app.processEvents()`: Mutter/XWayland necesita una vuelta real del
    *event loop en ejecución* para completar el protocolo de maximizado,
    no una ráfaga de bombeos manuales antes de `app.exec()`. Se cambió a
    diferir la solicitud con `QTimer.singleShot(300, ...)`: la ventana se
    muestra normal de inmediato y, 300 ms después de que la aplicación ya
    está corriendo de verdad (no antes de entrar al loop), se pide el
    maximizado, se registra el resultado y se cierra el splash -- como si
    la hubiera disparado un usuario con la app ya viva, no como parte del
    arranque sincrónico.

- **2026-07-27 — Hueco real de interfaz cerrado: asignar valores de
  metadatos a una fuente.** Encontrado mientras se preparaba el manual
  de usuario (redactar los pasos de la pestaña Metadatos obligó a
  intentar seguirlos en la interfaz real): `MetadataService.
  set_source_metadata_value` existe desde Etapa 2 y tiene pruebas
  completas, pero **nunca se conectó a ningún botón de ningún panel**
  -- un usuario no tenía forma de etiquetar una fuente con un valor de
  metadatos sin escribir código. Esto rompía en la práctica el puente
  documentado "Fuente → Metadatos → Filtro de recuperación" para
  cualquier persona que no fuera programadora.
  - `application/metadata/queries/list_source_metadata_values.py`
    (`ListSourceMetadataValues`) + `MetadataService.
    list_source_metadata_values(project_id, source_id)`: expone lo que
    ya sabía `SourceMetadataRepository.list_values_for_source` desde
    Etapa 2, para que la UI pueda mostrar los valores vigentes de una
    fuente, no solo escribir nuevos.
  - `ui/metadata/panel.py`: nueva sub-pestaña "Valores por fuente"
    (selector de fuente, lista de valores actuales, selector de campo +
    valor + "Guardar valor"). El control de valor cambia automáticamente
    entre una casilla de texto libre y una lista desplegable de
    entradas del catálogo cuando el campo elegido está ligado a uno
    (`field.catalog_id`) -- evita que el usuario tenga que adivinar o
    escribir a mano un código de catálogo válido, y reutiliza el error
    de dominio existente (`InvalidMetadataValueError`) si de todos
    modos no coincide.
  - 2 pruebas nuevas de `list_source_metadata_values`
    (`tests/unit/application/test_metadata_service.py`). 473 pruebas en
    total, todas verdes (mismas 3 omisiones de siempre). Verificado
    también de punta a punta contra `app/bootstrap.py` real: un campo de
    texto y un campo ligado a catálogo, ambos asignados a una fuente
    real, listados correctamente, y un valor fuera del catálogo
    rechazado con el mensaje de dominio correcto (no una excepción
    cruda).
  - **Por qué importa señalarlo explícitamente**: este hueco no había
    aparecido en ninguna auditoría anterior contra el documento maestro
    porque esas auditorías comparaban *funcionalidad de application*
    contra el documento, no *qué es alcanzable desde la interfaz* --
    ambas cosas pueden divergir, como aquí. Queda como recordatorio de
    que la cobertura de pruebas de `application` no sustituye una
    revisión de que cada caso de uso relevante tenga de verdad un
    camino real en la UI.

- **2026-07-27 — Cierre de 2 brechas encontradas en la auditoría contra
  el documento maestro tras completar las 8 etapas: extracción real de
  XLSX/CSV y un paso explícito de Normalización.** Con las 8 etapas ya
  completas, se corrió una batería exhaustiva de pruebas (unitarias,
  integración, humo, `py_compile` de todo el árbol, `ruff` para
  detectar código muerto/nombres indefinidos, y un recorrido de
  extremo a extremo de las 8 etapas contra `app/bootstrap.py` real) y
  se comparó sistemáticamente lo implementado contra el alcance mínimo
  obligatorio de la primera versión que el propio documento maestro
  enumera ("Debe incluir: ... Extracción de PDF, DOCX, XLSX, CSV y
  texto. Normalización. ..."). Se encontraron exactamente 2 huecos
  reales frente a esa lista (no frente a los "complementos"/
  "conectores empresariales" que el documento sí defiere a propósito):
  XLSX/CSV no tenían extractor, y no existía un paso de normalización
  de texto propio.
  - `infrastructure/extraction/text_extractors.py`: `XlsxExtractor`
    (vía `openpyxl`, `read_only=True, data_only=True` -- lee el valor
    ya calculado de una fórmula, no la fórmula en sí) y `CsvExtractor`
    (vía `csv.Sniffer`, detecta coma/punto y coma/tabulador, con
    manejo de BOM `utf-8-sig`). Ambos convierten sus datos al mismo
    formato de tabla Markdown que ya usaba `DocxExtractor`
    (`rows_to_markdown_table`, extraído como función compartida) --
    `FragmentationStrategy.POR_TABLA` los reconoce sin cambios. Una
    hoja XLSX vacía se omite con advertencia en vez de romper.
  - `domain/ingestion/normalization.py` (`normalize_text`): NFC
    Unicode, saltos de línea unificados, espacios finales de línea
    quitados, líneas en blanco excesivas colapsadas, caracteres de
    control removidos -- normalización de forma, no de contenido (no
    corrige ortografía). Integrado en
    `application/ingestion/commands/extract_source_text.py`, entre la
    extracción y el guardado. **Decisión importante de correctitud**:
    solo se aplica cuando la extracción no produjo `page_breaks`
    (TXT/DOCX/XLSX/CSV/imagen) -- normalizar el texto completo de un
    PDF después de calcular sus saltos de página invalidaría esos
    desplazamientos (trazabilidad de página, A2); PDF ya aplica su
    propia normalización específica (`repair_letter_spaced_text`) por
    página, antes de fijar esos desplazamientos, así que no se le
    aplica el paso general. Verificado explícitamente con una prueba
    que confirma que el texto paginado no se toca.
  - Nueva dependencia: `openpyxl>=3.1` (pyproject.toml,
    requirements.txt) -- CSV no necesitó ninguna (`csv` es de la
    biblioteca estándar).
  - 18 pruebas nuevas: 10 de `normalize_text`
    (`tests/unit/domain/test_normalization.py`, incluida una prueba de
    idempotencia y una que confirma que no toca el espaciado interno
    de una tabla Markdown), 2 de integración de `ExtractSourceText`
    confirmando cuándo se normaliza y cuándo no, 6 de integración real
    de `XlsxExtractor`/`CsvExtractor` contra archivos `.xlsx`/`.csv`
    generados en la propia prueba (no mocks). Se actualizó además la
    prueba de cobertura de tipos soportados
    (`test_supports_reports_coverage_without_html_json_xml_api_or_database`,
    antes probaba HTML/XLSX juntos como "sin soporte"; XLSX ya tiene
    soporte real) y una prueba que usaba XLSX como ejemplo de "tipo no
    soportado" (ahora usa HTML). 471 pruebas en total, todas verdes
    (mismas 3 omisiones de siempre). Verificado también de punta a
    punta: un archivo `.xlsx` real con una hoja de datos y una hoja
    vacía, y un `.csv` con BOM y delimitador `;`, ambos extraídos e
    incorporados correctamente vía `app/bootstrap.py` real.
  - **Conclusión de la auditoría**: con estas 2 brechas cerradas, la
    herramienta cumple el alcance mínimo obligatorio de la primera
    versión completo, además de las 8 etapas del ciclo metodológico
    completo. Las demás observaciones (compuertas preventivas dentro
    de cada pantalla, HTML/JSON/XML/API/base de datos, flujo "crear
    proyecto desde plantilla", manejo de secretos de complementos,
    instalador multiplataforma) son mejoras deliberadamente pospuestas
    y documentadas, no huecos frente al objetivo central para el uso
    local bajo Ubuntu que se está dando a la herramienta hoy.

- **2026-07-27 — Etapa 8 completa: Complementos (registro global de
  plantillas, nuevos proveedores, importadores y evaluadores
  personalizados, con un cargador dinámico real).** Con esto se cierra
  el ciclo completo de las 8 etapas del documento maestro. El documento
  es explícito en que "la primera versión no debería intentar cubrir
  todos los conectores y modelos posibles": los conectores
  empresariales, modelos adicionales y canalizaciones reales "pueden
  agregarse posteriormente mediante complementos" -- hasta ahora no
  existía ningún mecanismo para registrar ni cargar uno.
  - Contexto nuevo `domain/plugins/`: `PluginKind` (los 4 tipos exactos
    del documento maestro: plantilla, proveedor, importador, evaluador)
    y `Plugin` (código único dentro de su tipo, nombre, descripción,
    versión, `entry_point` opcional en formato
    `"paquete.modulo:NombreDeClase"`, `config` como JSON libre,
    habilitado/deshabilitado). **Decisión arquitectónica que rompe con
    el patrón de las Etapas 2-7**: un complemento no pertenece a un
    proyecto, así que `PluginRepository` no recibe `project_id` y su
    implementación vive en `application.db` (línea de migración
    `global/`, migración `0002_plugins.py`), no en el `project.db` de
    cada proyecto -- coherente con el propio docstring de `GlobalBase`
    desde Etapa 1 ("plantillas, catálogos reutilizables -- el resto se
    añade cuando exista su caso de uso").
  - `domain/plugins/loader.py` (`load_and_validate`, la pieza central):
    resuelve un `entry_point` con `importlib` y confirma que la clase
    obtenida en verdad es subclase concreta del puerto de dominio que
    le corresponde a su tipo (`EmbeddingProvider` de Etapa 4 para
    proveedor, `TextExtractor` de Etapa 3 para importador, un
    `CustomEvaluator` nuevo para evaluador) -- nunca un `ImportError`/
    `AttributeError` crudo, siempre `PluginLoadError` con un mensaje
    legible. Vive en `domain`, no en `infrastructure`, porque solo usa
    `importlib` de la biblioteca estándar (ADR-001 lo permite) y no hay
    ningún adaptador alternativo que intercambiar -- a diferencia de
    `EmbeddingProvider`/`VectorStore`, "cómo se importa un módulo de
    Python" es siempre lo mismo, así que un puerto con una sola
    implementación posible no aportaría nada. Verificado con clases
    reales del propio proyecto (`FastEmbedEmbeddingProvider`,
    `TxtExtractor`), no solo con dobles: carga y valida un proveedor
    real, rechaza un `TextExtractor` registrado como si fuera un
    proveedor (contrato equivocado), y rechaza un módulo inexistente.
  - `application/plugins/commands/register_plugin.py`
    (`RegisterPlugin`): rechaza un código duplicado dentro del mismo
    tipo (`DuplicatePluginCodeError`) y exige `entry_point` para los 3
    tipos que cargan código (`MissingEntryPointError`) -- solo una
    plantilla puede registrarse sin código, porque es datos. `
    application/plugins/queries/validate_plugin.py` (`ValidatePlugin`)
    intenta cargar el `entry_point` y devuelve `{"ok", "message"}` sin
    lanzar (para que la UI lo muestre sin manejo de excepciones) --
    **nunca invoca la lógica de negocio del complemento**
    (`embed_texts`/`extract`/`evaluate`), solo confirma que se puede
    importar y que implementa el contrato correcto.
  - Persistencia real: `PluginRecord` (`GlobalBase`, `application.db`,
    restricción única `(kind, code)` -- el mismo código puede repetirse
    entre tipos distintos, p. ej. un proveedor y un importador ambos
    con code="azure", pero no dos proveedores con el mismo code).
  - `PluginService` (fachada) no depende de ningún otro servicio de
    application (a diferencia de `QualityService`/`ReleaseService`):
    el registro de complementos es independiente de los seis contextos
    de proyecto.
  - **Alcance deliberado, documentado explícitamente en el propio
    dominio y en "Limitaciones conocidas"**: esta iteración entrega el
    mecanismo de registro y carga, no complementos de terceros ya
    integrados -- registrar un proveedor no hace que `RagService` lo
    use automáticamente; un evaluador personalizado se puede validar
    pero `RunEvaluation` (Etapa 6) no lo invoca todavía durante una
    corrida real; una plantilla registra su configuración por defecto
    pero no existe un flujo "crear proyecto desde esta plantilla" que
    la aplique (`Project.template_id` sigue siendo solo una referencia
    de texto libre); no hay manejo especial de secretos para valores
    como una API key dentro de `Plugin.config` (viaja en texto plano en
    `application.db`, sin cifrado ni almacén seguro de credenciales).
  - UI: pestaña nueva "Complementos" -- **la única pestaña de toda la
    aplicación que no depende de ningún proyecto activo** (opera sobre
    `application.db`, no sobre un `project.db`), con formulario de
    registro (tipo, código, nombre, versión, entry_point, configuración
    libre "clave=valor"), lista con activar/desactivar, y un botón
    "Validar" que llama a `validate_plugin` y muestra el resultado real
    sin ejecutar el complemento. `application/plugins/options.py`
    expone el vocabulario de tipos y una etiqueta legible del contrato
    esperado de cada uno, sin que la UI importe domain.
  - 31 pruebas nuevas: 15 de dominio (`test_plugin_entities.py`,
    `test_plugin_loader.py` -- estas últimas contra clases reales del
    proyecto, no dobles), 11 de `PluginService`
    (`test_plugin_service.py`), 5 de integración real con SQLite vía
    Alembic sobre la línea `global/` (`test_plugin_repositories.py`).
    453 pruebas en total, todas verdes (mismas 3 omisiones de siempre).
    Verificado también de punta a punta contra `app/bootstrap.py` real:
    registrar un proveedor con el `entry_point` real de
    `FastEmbedEmbeddingProvider` y validarlo con éxito, registrar una
    plantilla sin código, activar/desactivar, listar por tipo, y
    confirmar que un código duplicado o un tipo sin `entry_point` se
    rechazan con el error de dominio correcto, no con una excepción
    cruda.
  - **Título de la ventana simplificado a "RAG STUDIO"** (pedido
    explícito del usuario, con captura de pantalla mostrando el título
    largo "Núcleo + Gobierno documental + ... (Etapas 1-7)"): enumerar
    cada etapa completada en la barra de título dejó de ser práctico en
    cuanto se cerró el ciclo completo de las 8 etapas -- ese detalle
    ahora vive en este README (encabezado y bitácora) y en las pestañas
    mismas, no en `ui/projects/main_window.py`.

- **2026-07-27 — Etapa 7 completa: Liberación (compuertas de avance,
  dictamen y entregables formales sobre los seis contextos previos).**
  El documento maestro exige que "la propia aplicación imponga la
  metodología" en vez de depender de que el usuario la recuerde: una
  liberación debe bloquearse ante uso de contenido vencido, respuesta
  con fuente no validada, incumplimiento de filtro obligatorio,
  invención crítica, exposición de información restringida,
  canalización crítica fallida o pérdida de trazabilidad. Hasta ahora
  no había ningún mecanismo que verificara, de un solo vistazo, si un
  proyecto está listo para liberarse.
  - Contexto nuevo `domain/release/`: `ReleaseStatus` (los 8 valores
    exactos del documento maestro: no iniciada, en preparación, en
    ejecución, en revisión, aprobada, rechazada, bloqueada, sustituida),
    `GateResult` (nombre, si pasó, motivo legible), `ReleaseChecklist`
    (lista de `GateResult` con `all_passed`/`failed_gates`),
    `ReleaseRecord` (una solicitud de liberación evaluada: estado,
    checklist, dictamen en texto plano, evidencia de las versiones
    congeladas -- id de esquema/corrida de pipeline/corrida de
    evaluación --, y el reporte de entregables). Se conserva el
    historial completo de liberaciones (igual que `PipelineRun`/
    `EvaluationRun`): una liberación bloqueada o rechazada queda como
    evidencia de que se intentó y por qué no procedió, nunca se
    sobreescribe.
  - `application/release/queries/evaluate_release_gates.py`
    (`EvaluateReleaseGates`, la pieza central): evalúa 6 compuertas
    llamando solo a los seis facades ya existentes, sin reimplementar
    ninguna verificación -- Metadatos (`MetadataService.get_schema` con
    al menos un campo), Fragmentación (`IngestionService.
    list_fragmentation_policies` no vacío), Pipeline reproducible
    (última corrida con `is_usable_as_index_base`), Índice y
    recuperación (`RagService.get_index_info` con al menos un fragmento
    indexado), Diseño conversacional (al menos una intención activa y
    un guardrail activo) y Calidad (al menos un caso de prueba y la
    última corrida de evaluación sin `has_blocking_failures`). Sigue el
    mismo precedente ya establecido de "servicios de application que
    dependen de otros servicios de application" (como `QualityService`
    dependiendo de `ConversationalService`).
  - `application/release/queries/generate_deliverables_report.py`
    compila los 8 entregables formales del documento maestro
    (especificación de metadatos, diseño de fragmentación, pipeline
    reproducible, índice y reporte de recuperación, catálogo de reglas,
    esquema de canalización, banco de pruebas, matriz de resultados
    esperados) como un dict serializable a JSON, leyendo de los seis
    contextos previos -- **decisión de alcance**: se guarda inline en
    `ReleaseRecord.deliverables_report`, no como 8 archivos separados en
    el paquete `.agentproj` (ver "Limitaciones conocidas").
  - `application/release/commands/request_release.py`
    (`RequestRelease`): evalúa las compuertas, compila los entregables,
    decide `APROBADA` si todas pasan o `BLOQUEADA` si alguna falla,
    arma un dictamen en texto plano nombrando las compuertas
    incumplidas, y persiste el registro completo.
  - **Alcance deliberado, documentado explícitamente en el propio
    dominio**: no hay compuerta de Etapa 1 (Objetivo/Usuarios/Alcance/
    Fuentes iniciales/Riesgo) porque `Project` no tiene esos campos; las
    compuertas se evalúan solo al solicitar una liberación, no como
    bloqueo preventivo retrofitado en cada pantalla de las Etapas 2-6
    (sigue siendo posible, por ejemplo, fragmentar sin esquema
    aprobado).
  - Persistencia real: `ReleaseRecordRecord` (migración
    `0008_release.py`, historial completo como `PipelineRun`/
    `EvaluationRun`, nunca upsert).
  - `ReleaseService` (fachada) depende de los seis servicios previos
    (`MetadataService`, `IngestionService`, `PipelineService`,
    `RagService`, `ConversationalService`, `QualityService`) -- no
    duplica ninguna verificación ya implementada en ellos.
  - UI: pestaña nueva "Liberación" (nivel de proyecto): botón "Evaluar
    compuertas" (solo lectura, muestra el detalle de cada compuerta),
    botón "Solicitar liberación" (persiste el intento y muestra el
    dictamen + evidencia), historial de liberaciones con doble clic
    para reabrir cualquiera. A diferencia de Ingesta/Diseño
    conversacional/Calidad, esta pestaña no usa hilos en segundo plano:
    evaluar compuertas y solicitar una liberación son solo lecturas de
    repositorios ya existentes, sin llamadas a embeddings ni red.
  - 23 pruebas nuevas: 4 de entidades de dominio
    (`tests/unit/domain/test_release_entities.py`), 14 de
    `ReleaseService`/`EvaluateReleaseGates`/`RequestRelease`
    (`tests/unit/application/test_release_service.py`, cada compuerta
    probada en su estado de falla y de éxito, más el dictamen bloqueado/
    aprobado y el historial), 5 de integración real con SQLite vía
    Alembic. 422 pruebas en total, todas verdes (mismas 3 omisiones de
    siempre). Verificado también de punta a punta contra
    `app/bootstrap.py` real: un proyecto recién creado evalúa las 6
    compuertas en falso y una solicitud de liberación queda
    `BLOQUEADA` con un dictamen nombrando las 6 compuertas incumplidas.

- **2026-07-27 — Etapa 6 completa: Calidad (banco de pruebas, corridas
  de evaluación con semáforos, regresión entre corridas y bloqueos
  automáticos por hallazgos críticos).** El documento maestro pide un
  banco de pruebas (B4) y criterios de aceptación (B5) sobre el motor
  conversacional de Etapa 5 -- hasta ahora, probar una intención,
  guardrail o esquema de canalización solo se podía hacer a mano, uno
  por uno, en el Simulador. Se construyó de un solo bloque, mismo
  patrón de capas que el resto del proyecto.
  - Contexto nuevo `domain/quality/`: `TestCase` (código legible tipo
    "TEST-ADM-001", categoría -- las 14 del documento maestro:
    respuesta directa/condicionada, consulta ambigua, sin información,
    con canalización, contradicción, fuente vencida/no validada,
    privacidad, seguridad, cambio de intención, conversación
    multivuelta, error técnico, manipulación de instrucciones --,
    consulta, datos proporcionados, intención/dato faltante/acción
    esperados, acción prohibida, si se espera canalización real, fuente
    esperada en el primer resultado, severidad). `EvaluationResultItem`
    guarda el veredicto de un caso dentro de una corrida (semáforos
    exactos del documento: Verde/Amarillo/Rojo/Gris) más las
    discrepancias encontradas en texto plano. `EvaluationRun` conserva
    el historial completo de corridas (igual que `PipelineRun`, no
    upsert) con `overall_verdict` (el más severo de sus items) y
    `has_blocking_failures` (cualquier Rojo) -- misma forma que
    `PipelineRun.is_usable_as_index_base`, pensada como la señal que una
    futura Etapa 7 (liberación) necesitaría para bloquear.
  - **Alcance deliberado, documentado explícitamente en el propio
    dominio**: los criterios de aceptación del documento maestro
    incluyen varios que exigirían juzgar una respuesta en lenguaje
    natural ("claridad", "citación", "ausencia de invenciones",
    "fundamentación") -- fuera de alcance porque esta herramienta
    nunca genera texto con un modelo de lenguaje ("la pieza central no
    es el modelo generativo", ya citado en Etapa 4 y 5). `TestCase`
    solo compara contra lo que `SimulationTrace` sí produce: intención,
    variables, acción, canalización, fuente/fragmento recuperado.
  - `application/quality/commands/run_evaluation.py` (`RunEvaluation`,
    la pieza central): llama a `ConversationalService.simulate()` por
    cada caso seleccionado (sin reimplementar el motor conversacional),
    compara el `SimulationTrace` contra lo esperado y calcula el
    veredicto -- una acción prohibida siempre es Rojo; una acción
    esperada que no se cumplió es Rojo si la severidad del caso es
    alta/crítica, Amarillo si no; una intención, dato faltante,
    canalización o fuente esperada que no coincide es Amarillo. Tres
    alcances de ejecución (completa/por categoría/individual, de los
    ocho tipos del documento maestro -- comparación entre modelos/
    índices/reglas/prompts queda fuera, ver "Limitaciones conocidas").
    Aislamiento de fallas por caso (mismo criterio que `RunPipeline`):
    si simular un caso lanza una excepción, ese caso queda en Gris con
    el error, sin abortar el resto del banco. Regresión: compara contra
    la corrida anterior completa del proyecto por código de caso -- si
    un caso estaba en Verde y deja de estarlo, se marca `regressed`.
  - `QualityService` (fachada) reutiliza `ConversationalService` ya
    construido en `app/bootstrap.py` -- no duplica nada de Etapa 5.
  - Persistencia real: `TestCaseRecord` (upsert por id, igual criterio
    que Intent/GuardrailRule) y `EvaluationRunRecord`/
    `EvaluationResultItemRecord` (migración `0007_quality.py`,
    historial completo como `PipelineRun`).
  - **Detalle de higiene de pruebas**: `TestCase`/`TestCategory`/
    `TestSeverity` son nombres tomados del vocabulario del propio
    documento maestro ("casos de prueba"), pero coinciden con el patrón
    `Test*` que pytest usa para autodetectar clases de prueba --
    generaban una advertencia de recolección en cualquier módulo que
    los importara. Se les agregó `__test__ = False` (o
    `ClassVar[bool]` en el caso de `TestCase`, que es un modelo
    Pydantic) para que pytest los ignore explícitamente.
  - UI: pestaña nueva "Calidad" (nivel de proyecto), con sub-pestañas
    "Banco de pruebas" (crear/activar/desactivar/listar casos) y
    "Evaluación" (selector de alcance, reporte con semáforo y
    discrepancias por caso, veredicto general, aviso de bloqueo y de
    regresiones, historial de corridas con doble clic para reabrir
    cualquiera). `application/quality/options.py` expone los
    vocabularios de enums a la UI sin que esta importe domain
    directamente (mismo patrón que en Etapa 5); reutiliza
    `RULE_ACTION_OPTIONS` de Etapa 5 para acción esperada/prohibida y
    `parse_provided_variables` de `ui.conversational.parsing` para el
    campo de datos proporcionados.
  - 32 pruebas nuevas: 6 de entidades de dominio
    (`tests/unit/domain/test_quality_entities.py`), 15 de
    `RunEvaluation` (`tests/unit/application/test_run_evaluation.py`,
    incluyendo cada tipo de veredicto, aislamiento de fallas, los tres
    alcances de ejecución, regresión entre corridas y cancelación entre
    casos), 4 de `QualityService`, 7 de integración real con SQLite vía
    Alembic. 399 pruebas en total, todas verdes (mismas 3 omisiones de
    siempre). Verificado
    también de punta a punta contra `app/bootstrap.py` real: creación
    de proyecto, intención, dos casos de prueba reales, una corrida
    completa (veredicto Verde, sin bloqueos), una corrida individual, y
    el historial con ambas corridas -- sin necesitar red, porque los
    casos de ejemplo no llegan a necesitar el modelo de embeddings
    (misma limitación de siempre para el camino de "responder").

- **2026-07-27 — Etapa 5 completa: Diseño conversacional (intenciones,
  variables conversacionales, guardrails, esquema de canalización y un
  simulador que los conecta con el motor RAG de Etapa 4).** El
  documento maestro describe la correspondencia "Fuentes → Metadatos →
  Fragmentos → Índice → Intenciones → Variables → Filtros → Guardrails
  → Canalización → Pruebas → Evidencias → Liberación" como el núcleo
  diferenciador de la herramienta; hasta ahora todo lo construido
  llegaba solo hasta "Índice" (Etapa 4). Se construyó de un solo bloque
  (decisión del usuario), siguiendo el mismo patrón de capas que el
  resto del proyecto.
  - Contexto nuevo `domain/conversational/`: `Intent` (nombre,
    descripción, ejemplos positivos/negativos, prioridad, nivel de
    riesgo, datos mínimos/opcionales, preguntas aclaratorias, regla de
    respuesta, canalización alternativa), `ConversationalVariable`
    (con `metadata_field_id` opcional -- el puente documentado "Dato
    conversacional → Campo de metadatos → Filtro de recuperación"),
    `GuardrailRule` (13 tipos de regla del catálogo del documento
    maestro; condiciones "[Campo] [Operador] [Valor]" combinadas con
    Y; acción resultante: responder/aclarar/abstenerse/canalizar) y
    `ChannelingScheme` (motivo, condición, área destino, prioridad,
    datos obligatorios/permitidos/prohibidos, resumen, medio, mensaje
    al usuario, acción alternativa).
  - `domain/conversational/intent_matching.py`: emparejamiento de
    intención con similitud de Jaccard sobre tokens (mismo criterio
    que BM25 en Etapa 4: "la pieza central no es el modelo generativo
    ni la base vectorial", documento maestro) -- sin LLM ni
    clasificador entrenado, con ejemplos negativos para distinguir
    intenciones parecidas en superficie. **Corrección durante la
    verificación end-to-end**: sin filtrar conectores comunes del
    español ("de", "la", "que"...), dos consultas sin relación real
    podían "emparejar" solo por compartir una preposición -- se agregó
    una lista de conectores a ignorar (mismo criterio que
    `ui.ingestion.search_highlighting`, pero aquí afecta el resultado
    real, no solo qué se resalta) y una prueba de regresión para el
    caso exacto que lo reveló.
  - `domain/conversational/rule_evaluation.py`: evalúa condiciones
    campo/operador/valor (con coerción numérica cuando ambos lados lo
    permiten, texto sin distinguir mayúsculas si no) y, cuando varias
    reglas activas disparan a la vez, elige la acción más severa
    (canalizar > abstenerse > aclarar > responder) en vez de la
    primera por casualidad de orden.
  - `application/conversational/queries/simulate_conversation.py`
    (`SimulateConversation`, la pieza central): empareja la intención,
    detecta datos mínimos faltantes (si faltan, siempre exige aclarar
    antes de responder -- la "regla de oro" de B2, combinada por
    severidad con lo que decidan los guardrails, nunca se "relaja" a
    responder), aplica guardrails, y si la decisión final es responder,
    llama a `RagService.search_hybrid` **forzando siempre
    `only_usable_sources=True`** (a diferencia del Laboratorio RAG de
    Etapa 4, donde es opt-in) -- un motor conversacional real nunca
    debe responder con contenido rechazado, vencido o no validado. Los
    resultados se filtran además por cada variable conversacional
    proporcionada que esté ligada a un campo de metadatos (el puente
    "Dato conversacional → Campo de metadatos → Filtro de
    recuperación"), reutilizando `SourceMetadataRepository.get_value`
    fuente por fuente en vez de crear un índice inverso nuevo. Si la
    búsqueda no deja resultados utilizables, la decisión final pasa a
    abstenerse -- nunca se responde con la búsqueda vacía.
  - El reporte (`SimulationTrace`) sigue el listado exacto que pide el
    documento maestro para el simulador: intención, confianza,
    variables detectadas/faltantes, pregunta aclaratoria, filtros,
    fuentes, fragmentos, reglas activadas, decisión tomada,
    canalización.
  - Persistencia real: `IntentRecord`/`ConversationalVariableRecord`/
    `GuardrailRuleRecord`/`ChannelingSchemeRecord` (migración
    `0006_conversational_design.py`) -- upsert por id (o por código
    para variables/esquemas), igual convención que la mayoría de las
    tablas de configuración del proyecto (no como `PipelineRun`, que sí
    conserva historial completo).
  - `ConversationalService` (fachada) reutiliza `RagService` y
    `SourceMetadataRepository` ya construidos en `app/bootstrap.py` --
    no duplica nada de Ingesta/RAG/Metadatos.
  - UI: pestaña nueva "Diseño conversacional" (nivel de proyecto, no de
    fuente), ya nacida con sub-pestañas por proceso (Intenciones,
    Variables, Guardrails, Canalización, Simulador) siguiendo el mismo
    criterio recién adoptado en Ingesta. `application/conversational/
    options.py` expone los vocabularios de enums a la UI sin que esta
    importe domain directamente (mismo patrón que
    `FRAGMENTATION_STRATEGY_OPTIONS`); `ui/conversational/parsing.py`
    interpreta los campos de texto libre del formulario (listas,
    pares "código: pregunta", condiciones "campo operador valor") como
    funciones puras sin Qt, devolviendo dicts en vez de construir tipos
    de dominio -- es `ConversationalService` quien los construye,
    para que la UI nunca importe domain (ADR-001).
  - Alcance deliberadamente acotado para esta primera versión (ver
    también "Limitaciones conocidas"): CRUD de cada catálogo es Crear +
    Activar/Desactivar + listar, sin edición completa; la canalización
    se simula (genera el paquete estructurado) sin integrarse con
    sistemas externos reales; el simulador opera una consulta a la vez,
    sin memoria entre llamadas.
  - 60 pruebas nuevas: 8 de `match_intent`
    (`tests/unit/domain/test_intent_matching.py`), 10 de evaluación de
    guardrails (`tests/unit/domain/test_rule_evaluation.py`), 7 de
    `ConversationalService` (CRUD), 10 de `SimulateConversation`
    (respuesta directa, aclaración por dato faltante, abstención sin
    intención reconocida, canalización con y sin esquema configurado,
    filtro por variable ligada a metadatos, abstención por filtro que
    excluye todo, y la garantía de nunca usar una fuente no validada
    aunque el Laboratorio RAG sí la mostraría), 8 de integración real
    con SQLite vía Alembic, 9 de `ui.conversational.parsing`. 367
    pruebas en total, todas verdes (mismas 3 omisiones de siempre).
    Verificado también de punta a punta contra `app/bootstrap.py` real:
    creación de proyecto, intención, variable, guardrail y esquema de
    canalización reales, con dos simulaciones reales (aclaración por
    dato faltante, y canalización disparada por un guardrail de riesgo
    alto) -- ambas sin necesitar red, porque no llegan a llamar al
    modelo de embeddings; el camino de "responder" (que sí necesita
    `search_hybrid`) queda cubierto por las 10 pruebas con dobles, ya
    que este entorno de construcción no tiene red hacia Hugging Face
    (misma limitación de siempre, documentada desde Etapa 4).

- **2026-07-27 — Reorganización de la pestaña Ingesta en sub-pestañas
  por etapa (usabilidad, sin cambios de lógica).** El usuario reportó
  (con una captura real) que la pestaña Ingesta quedó demasiado
  cargada: los cinco procesos (Pipeline, Extracción, Fragmentación,
  Búsqueda RAG, Comparador de modelos) vivían apilados en una sola
  columna vertical, cada uno con muy poco espacio para mostrar su
  resultado -- había que scrollear una pestaña larguísima para ver
  cualquier cosa completa.
  - Se preguntó al usuario entre tres enfoques (sub-pestañas, paneles
    colapsables, dos columnas con divisor); eligió sub-pestañas.
  - `ui/ingestion/panel.py`: se agregó un `QTabWidget` (`self._tabs`)
    justo debajo de la barra de estado/progreso/cancelar (que se queda
    fija y visible sin importar la sub-pestaña activa, porque un
    trabajo en segundo plano puede venir de cualquiera de ellas). Cada
    `QGroupBox` que antes se agregaba con `layout.addWidget(...)` ahora
    se agrega como una pestaña de `self._tabs` ("Pipeline",
    "Extracción", "Fragmentación", "Búsqueda RAG", "Comparador de
    modelos") -- cambio puramente de distribución: ningún widget,
    señal/slot, ni lógica de habilitado/deshabilitado cambió de sitio o
    de comportamiento.
  - Sin pruebas nuevas (no hay lógica nueva que probar; ningún test
    existente dependía de la jerarquía de layouts). 313 pruebas en
    total, todas verdes (mismas 3 omitidas de siempre) tras el cambio.
    Verificado también con `py_compile` sobre el archivo modificado.

- **2026-07-27 — Pipeline reproducible por lote (Etapa 3, Ingesta):
  corrida completa del proyecto con incrementalidad, reanudación y
  trazabilidad.** El documento maestro exige una "Compuerta 3" (no usar
  una corrida incompleta como base de índice) y un pipeline con
  extracción, fragmentación, indexación, reanudación e incrementalidad
  sobre el conjunto de fuentes de un proyecto -- hasta ahora cada fuente
  se procesaba a mano, una por una, sin ningún registro de corridas.
  - Contexto nuevo `domain/pipeline/`: `PipelineRun` (una corrida)
    contiene una lista de `PipelineRunItem` (una fuente dentro de esa
    corrida), cada uno con estado `EXITOSO`/`FALLIDO`/`OMITIDO`/
    `CANCELADO`. `PipelineRun.is_usable_as_index_base` solo es `True` si
    la corrida terminó `COMPLETO` (sin ninguna fuente fallida) -- esa es
    la Compuerta 3 hecha código, no solo documentación.
  - **Decisión de diseño clave sobre incrementalidad**: `Source.content_hash`
    existe en el modelo de dominio desde antes, pero se confirmó por
    revisión de código que la UI real (`ui/sources/panel.py`) nunca lo
    calcula ni lo usa -- así que no sirve como señal real de "¿cambió
    este archivo?". En su lugar, `RunPipeline._hash_file()` calcula un
    SHA-256 real del contenido del archivo en `Source.location` en cada
    corrida, y lo compara contra el hash guardado en el último
    `PipelineRunItem` exitoso de esa fuente (`PipelineRunRepository.
    get_last_successful_item`). Si no cambió, la fuente se marca
    `OMITIDO` sin volver a extraer/fragmentar/indexar. El mismo
    mecanismo da "reanudación" gratis: una fuente que falló antes nunca
    tiene un item exitoso registrado, así que siempre se vuelve a
    procesar en la siguiente corrida.
  - Aislamiento de fallas: `RunPipeline._process_source` atrapa
    cualquier excepción de una fuente (deliberadamente amplio, a
    diferencia del resto del código que atrapa excepciones específicas)
    para que la falla de una fuente no aborte el lote completo -- "corridas
    con errores/advertencias y trazabilidad" es un requisito literal del
    documento maestro, no solo "que no truene".
  - `document_type_code` del pipeline queda como un solo parámetro por
    corrida (default `"default"`), no por fuente -- limitación conocida
    documentada más abajo, para no ampliar el alcance de esta pieza.
  - Persistencia real: `PipelineRunRecord`/`PipelineRunItemRecord`
    (migración `0005_pipeline_runs.py`) guardan **historial completo**
    de corridas (a diferencia de la mayoría de las tablas del proyecto,
    que solo guardan el estado más reciente) -- el documento maestro
    exige poder auditar corridas pasadas, no solo la última.
  - `application/pipeline/service.py`: `PipelineService` (fachada) con
    `run()`, `get_run()`, `list_runs()`; se conecta en `app/bootstrap.py`
    reutilizando las instancias ya existentes de `IngestionService` y
    `RagService` (no duplica su lógica).
  - UI: nueva sección "Pipeline del proyecto (todas las fuentes)" en la
    pestaña Ingesta, a nivel de proyecto (no de fuente individual):
    campo `document_type_code`, botón "Ejecutar pipeline completo" y un
    reporte con el resultado de cada fuente (icono de estado, fragmentos
    indexados, advertencias, error). Corre en segundo plano igual que
    extracción/fragmentación/indexación, con soporte de cancelación.
  - 20 pruebas nuevas: 4 de entidades de dominio
    (`tests/unit/domain/test_pipeline_entities.py`), 7 de `RunPipeline`
    (`tests/unit/application/test_run_pipeline.py`, incluyendo
    incrementalidad, reanudación tras fallo real de archivo, una fuente
    fallida sin abortar el lote, y cancelación entre fuentes), 3 de
    `PipelineService`, 6 de integración real con SQLite vía Alembic
    (`tests/integration/test_pipeline_repositories.py`). 313 pruebas en
    total, todas verdes (mismas 3 omitidas de siempre). Verificado
    además de punta a punta contra `app/bootstrap.py` real: creación de
    proyecto y fuente reales, corrida del pipeline y segunda corrida
    detectando correctamente que la fuente no cambió -- el único punto
    que no se pudo verificar aquí es el camino 100% exitoso completo,
    porque este entorno de construcción no tiene red hacia Hugging Face
    para descargar el modelo de embeddings real (misma limitación de
    siempre); el aislamiento de fallas sí quedó demostrado en la
    práctica: la corrida real terminó `COMPLETO_CON_ERRORES` con un
    error claro en vez de tronar, y `list_runs` devolvió el historial de
    ambas corridas correctamente.

- **2026-07-27 — Búsqueda textual (BM25) y búsqueda híbrida con
  reranking por Reciprocal Rank Fusion (Etapa 4, Laboratorio RAG).**
  Hasta ahora la pestaña Ingesta solo tenía búsqueda semántica (por
  vector); el documento maestro pide también textual e híbrida, y
  reranking, para el "Laboratorio RAG" de Etapa 4.
  - `domain/rag/text_search.py` (nuevo): `bm25_scores(query, documents)`,
    implementación pura de BM25 (Robertson/Sparck Jones) sin
    dependencias externas -- suficiente para el tamaño de corpus típico
    de un proyecto; si algún día no lo es, migrar a SQLite FTS5 (ya se
    usa SQLite para todo lo demás) es un cambio aislado a la clase
    `TextSearch`, sin tocar el resto del motor.
  - `application/rag/queries/text_search.py` (nuevo): `TextSearch`, con
    el mismo criterio de `CompareEmbeddingProfiles` -- calcula bajo
    demanda sobre `ChunkRepository`, sin necesitar índice vectorial ni
    haber indexado la fuente. Reutiliza `SemanticSearchResult` como
    tipo de resultado (mismo `chunk`+`score`, aunque el score sea BM25,
    no similitud coseno -- documentado en el docstring para no
    confundir escalas).
  - `application/rag/queries/hybrid_search.py` (nuevo): `HybridSearch`
    combina `SemanticSearch` + `TextSearch` con **Reciprocal Rank
    Fusion** (RRF, Cormack et al. 2009): combina *posiciones* de cada
    lista (no scores directamente, que viven en escalas distintas e
    incomparables) con `score = Σ 1/(60 + rango)`. Se eligió RRF en vez
    de un cross-encoder/LLM para el reranking a propósito: cumple el
    mismo requisito (mejorar el orden combinando señales) sin la
    dependencia pesada de otro modelo a descargar/cargar, respetando
    "local primero" y "sin tareas pesadas en la interfaz" del documento
    maestro.
  - `application/rag/_source_usability.py` (nuevo, refactor): la regla
    "fuente VALIDADO + vigente" que ya tenía `SemanticSearch` (ver
    bitácora anterior del mismo día) se extrajo a una función
    compartida, para que `TextSearch`/`HybridSearch` la reutilicen en
    vez de duplicarla -- mismo criterio que reusar `cosine_similarity`
    en `FakeVectorStore`.
  - `RagService` gana `search_text()` y `search_hybrid()`, con la misma
    firma que `search()` (incluye `only_usable_sources`). No son
    "capacidad opcional" como el comparador de modelos o el OCR: no
    exigen ninguna dependencia nueva, así que siempre están
    disponibles.
  - UI: nuevo selector "Modo:" (Semántica/Textual/Híbrida) junto al
    campo de consulta en la pestaña Ingesta. El aviso de "relevancia
    baja" (calibrado para similitud coseno) solo se muestra en modo
    Semántica; Textual/Híbrida muestran una nota aclarando que su score
    no es una similitud coseno y solo ordena esos resultados entre sí.
  - 22 pruebas nuevas: 8 de `bm25_scores` (`tests/unit/domain/test_text_search.py`),
    7 de `TextSearch` (`tests/unit/application/test_text_search.py`),
    4 de `HybridSearch` (`tests/unit/application/test_hybrid_search.py`),
    3 de wiring en `RagService`. 293 pruebas en total, todas verdes
    (mismas 3 omitidas de siempre). Verificado además contra
    `app/bootstrap.py` real: `search_text` funciona de punta a punta
    sin red (a diferencia de la búsqueda semántica, no necesita
    descargar ningún modelo de embeddings).
- **2026-07-27 — `imagen_escaneada` como fuente independiente (Módulo
  5).** Hasta ahora, OCR (Módulo 4) solo se usaba como respaldo dentro
  de `PdfTextExtractor` para páginas de PDF sin capa de texto; un
  archivo de imagen suelto (JPG, PNG...) registrado directamente como
  fuente con `SourceType.IMAGEN_ESCANEADA` (el valor del enum ya
  existía desde Etapa 2, pero sin extractor detrás) simplemente no
  tenía forma de producir texto.
  - `ImageTextExtractor` (nuevo, en
    `infrastructure/extraction/text_extractors.py`) cubre ese caso:
    reutiliza el mismo puerto `OcrEngine` de Módulo 4, pero a
    diferencia de `PdfTextExtractor` **no necesita PyMuPDF** -- la
    imagen ya viene rasterizada, no hay una página de PDF que
    convertir antes de reconocerla. Solo lee los bytes del archivo y
    se los pasa al motor OCR.
  - Mismo patrón de "capacidad opcional" que el resto de Módulo 4: sin
    `ocr_engine` (valor por defecto), no puede extraer nada -- se
    reporta con una advertencia clara ("no hay un motor OCR
    configurado") en vez de fallar en silencio o con un error críptico;
    `ExtractSourceText` convierte ese texto vacío en
    `EmptyExtractionError`, igual que cualquier otra fuente vacía.
  - `app/bootstrap.py` comparte el mismo `TesseractOcrEngine` (o su
    ausencia) entre `PdfTextExtractor` e `ImageTextExtractor` -- una
    sola decisión de "¿hay OCR disponible en este entorno?" para
    ambos, sin duplicar la lógica de detección.
  - Se corrigió el docstring de `UnsupportedSourceTypeError`, que
    todavía mencionaba `imagen_escaneada` como ejemplo de tipo sin
    extractor -- ya no lo es (aunque sin OCR configurado, el resultado
    sigue siendo "sin texto", ahora vía `EmptyExtractionError`, un
    error distinto y más preciso).
  - 8 pruebas nuevas en `tests/integration/test_text_extractors.py`
    (sin OCR, con motor falso que reconoce texto, con motor falso que
    falla, imagen sin texto reconocible, dispatch vía
    `CompositeTextExtractor`, y una con Tesseract real de punta a
    punta) más la corrección de una prueba existente que ya no aplica
    (`test_supports_reports_coverage...`: antes afirmaba que
    `imagen_escaneada` no tenía soporte, ahora sí lo tiene). 267
    pruebas en total, todas verdes (mismas 3 omitidas de siempre).
  - No hizo falta ningún cambio en la UI: el selector de
    `source_type` en la pestaña Fuentes ya listaba
    `imagen_escaneada` desde Etapa 2 (se genera del enum
    `SourceType` completo), simplemente no tenía extractor detrás
    hasta ahora.
- **2026-07-27 — Control de documentos excluidos: la búsqueda semántica
  puede excluir fuentes rechazadas, vencidas o no validadas.** Al
  revisar contra el documento maestro qué falta para el ciclo completo
  (Etapas 5-8 siguen sin empezar; ver bitácora del mismo día más abajo
  para el inventario completo), apareció un hallazgo real: ni
  `IndexSource` ni `SemanticSearch` revisaban nunca
  `Source.validation_status` ni su vigencia (`valid_from`/`valid_to`)
  -- contradice un "supuesto prohibido" explícito del documento maestro
  ("no usar documentos rechazados, vencidos o no validados cuando las
  reglas lo impidan"). Antes de este cambio, una fuente `RECHAZADO`,
  `VENCIDO` o todavía en `BORRADOR` se indexaba y se recuperaba en
  búsquedas exactamente igual que una `VALIDADO` y vigente.
  - Se decidió filtrar en la **búsqueda**, no al indexar: una fuente
    puede pasar a `RECHAZADO`/`VENCIDO` después de haberse indexado, sin
    que nadie vuelva a pulsar "Indexar esta fuente" -- filtrar solo al
    indexar dejaría vectores obsoletos disponibles para siempre.
    Filtrar en `SemanticSearch.execute()` (justo donde el resultado se
    "usa") es la garantía real, sin importar cuándo cambió el estado de
    la fuente relativo a cuándo se indexó.
  - Capacidad opcional otra vez: `SemanticSearch`/`RagService` aceptan
    un `source_repository` opcional (`None` por defecto -- sin cambio
    de comportamiento para quien no lo pase) y un nuevo parámetro
    `only_usable_sources: bool = False` en `search()`. Pedir el filtro
    sin haber configurado `source_repository` lanza
    `SourceFilterUnavailableError` con mensaje claro, en vez de
    ignorar el filtro en silencio (lo que dejaría pasar contenido
    rechazado sin que quien llama se entere). `app/bootstrap.py`
    reutiliza el mismo `SourceRepository` que ya existía para
    `document_service`.
  - Es opt-in a propósito: Etapa 4 sigue siendo un "laboratorio" donde
    a veces conviene buscar sobre todo lo indexado, incluidos
    borradores, mientras se prueba. El filtro se expone como una
    casilla nueva "Solo fuentes vigentes y validadas" junto a "Solo
    esta fuente" en la pestaña Ingesta -- el motor conversacional que
    se construya en Etapa 5 forzaría este filtro siempre a `True` para
    respuestas reales a un usuario final.
  - Un resultado con el filtro activo puede tener menos de `limit`
    elementos aunque existan más candidatos sin filtrar: se prefiere
    devolver de menos que arriesgarse a filtrar de más (documentado
    como comportamiento intencional, no limitación a corregir).
  - Un fragmento cuya fuente ya no existe en el repositorio (huérfano)
    se trata como no usable bajo el filtro, no como "usable por
    defecto".
  - 4 pruebas nuevas en `tests/unit/application/test_rag_service.py`
    (error claro sin `source_repository`, exclusión real de
    rechazado/vencido/borrador, comportamiento sin cambios cuando el
    filtro no se pide, fragmento huérfano tratado como no usable). 271
    pruebas en total, todas verdes (mismas 3 omitidas de siempre).
- **2026-07-27 — Auditoría contra el documento maestro: inventario de
  lo pendiente para el ciclo completo (Etapas 5-8).** A petición del
  usuario ("terminar la herramienta al 100%"), se revisó
  `RAG_STUDIO_Documento_Maestro_Proyecto_IA_v1.0.docx` (las 8 etapas
  con compuertas obligatorias) contra el estado real del código. Hoy
  están cubiertas, con matices, las Etapas 1 (Núcleo), 2 (Gobierno
  documental), 3 (Ingesta) y 4 (Laboratorio RAG, salvo lo que sigue).
  Pendiente, en orden de aparición en el documento maestro:
  - **Etapa 4, resto**: búsqueda textual y búsqueda híbrida (hoy solo
    hay búsqueda semántica por vector), reranking.
  - **Etapa 3, "pipeline reproducible" como entidad propia**: hoy todo
    es fuente por fuente desde la UI; falta una "corrida" sobre un lote
    completo del proyecto, con su propio reporte de errores/
    advertencias/tiempos y reanudación/incrementalidad real (reprocesar
    solo lo que cambió).
  - **Etapa 5 (Diseño conversacional): sin empezar.** Intenciones,
    variables y preguntas aclaratorias, catálogo de reglas y
    guardrails, esquema de canalización, simulador de conversación --
    un contexto de dominio nuevo completo, con su propia pestaña.
  - **Etapa 6 (Calidad): sin empezar.** Banco de pruebas (casos
    directos, ambiguos, sin datos, seguridad, privacidad, vigencia,
    contradicción, multivuelta, manipulación), centro de evaluación,
    comparación entre corridas, semáforos y bloqueos automáticos por
    hallazgos críticos.
  - **Etapa 7 (Documentación y liberación): parcial.** Ya existe
    empaquetado `.agentproj` con exportar/importar (Etapa 1); falta el
    generador documental que arme automáticamente los 8 entregables
    formales del documento maestro desde los datos reales del
    proyecto, más el dictamen de liberación, manifiesto y hashes de
    integridad.
  - **Etapa 8 (Extensibilidad): sin empezar.** `plugins/` existe
    reservado, sin SDK ni contrato de extensión todavía.
  - **Transversal: compuertas (0-7) sin mecanismo propio.** Nada
    impide hoy indexar sin metadatos aprobados o "liberar" sin pruebas
    -- es una capa de estado/validación que atraviesa todas las etapas
    y no se ha construido.
  - Se acordó con el usuario posponer el piloto UDL con datos reales
    (no es parte de los requisitos iniciales -- la herramienta debe
    quedar abierta a cualquier agente conversacional futuro) y
    concentrar el esfuerzo en cerrar el motor genérico primero, en
    Ubuntu, dejando Windows/macOS para una validación posterior.
- **2026-07-27 — Tipos documentales adicionales: artículo, pregunta
  +respuesta, tabla (Módulo 5).** Tercera pieza del orden pedido por
  el usuario (OCR → comparador de modelos → tipos documentales
  adicionales). Tres nuevas `FragmentationStrategy` que se configuran
  igual que las tres ya existentes (por `document_type_code` en la
  pestaña Ingesta, sin cambio de código para usarlas):
  - `por_articulo` (reglamentos): un fragmento por artículo completo,
    detectado por líneas que empiezan con "Artículo N" / "Art. N"
    (mayúsculas/minúsculas y con o sin punto y guion), sin
    sub-dividirlo aunque exceda `target_tokens` -- el supuesto y su
    consecuencia nunca quedan en fragmentos distintos
    (INVESTIGACION.odt, A2: "artículo completo, incluso si excede el
    tamaño estándar").
  - `pregunta_respuesta` (preguntas frecuentes): un fragmento por
    pregunta completa, detectado por líneas que empiezan con
    "P:"/"Pregunta:"/"Q:", sin solapamiento. Estos fragmentos se
    marcan con `ChunkType.PREGUNTA_RESPUESTA` (valor del enum que ya
    existía desde Etapa 3 pero que ningún divisor usaba todavía).
  - `por_tabla`: reconoce tablas en formato Markdown (fila de
    encabezado + fila separadora de guiones + filas de datos, todas
    con "|") y arma fragmentos que siempre repiten encabezado y
    separador si la tabla excede `target_tokens` (INVESTIGACION.odt,
    A2: "repetir encabezados en cada fragmento"). El texto que no es
    tabla se fragmenta igual que `por_tamaño`. Los fragmentos de tabla
    se marcan con `ChunkType.TABLA` (mismo caso: el enum ya existía,
    ahora se usa de verdad).
  - Las tres viven como funciones puras nuevas en
    `domain/ingestion/splitting.py` (`split_by_articles`,
    `split_by_qa_pairs`, `split_by_tables`), sin depender de PySide6 ni
    de infraestructura -- mismo patrón que `split_by_size`/
    `split_by_headings` ya existentes. `FragmentSource._split` ahora
    devuelve `(título, span, ChunkType)` en vez de solo `(título,
    span)`, para que cada estrategia pueda decidir el tipo de sus
    fragmentos sin tocar `execute()`.
  - **DocxExtractor ahora también extrae tablas reales de DOCX**
    (antes desaparecían por completo: `document.paragraphs` nunca las
    incluye). Se recorren párrafos y tablas en su orden real de
    aparición en el documento -- python-docx no lo expone
    directamente, así que se usa el idiom estándar de su FAQ
    ("Access all paragraphs and tables, in document order") -- y cada
    tabla se convierte a una tabla Markdown antes de fragmentar, para
    que `por_tabla` la reconozca igual que si viniera de un .txt/.md
    escrito a mano.
  - No se tocó `_has_meaningful_content` (el filtro de "encabezado sin
    cuerpo" de `IndexSource`, ver bitácora anterior): se revisó que
    ningún fragmento de artículo/pregunta/tabla pueda coincidir
    exactamente con su propio `section_title` salvo en el caso real de
    "artículo sin cuerpo" o "pregunta sin respuesta", donde descartarlo
    de la búsqueda semántica es el comportamiento correcto.
  - 24 pruebas nuevas: 12 de las funciones puras de división
    (`tests/unit/domain/test_splitting.py`), 3 de extremo a extremo con
    `IngestionService` real por cada estrategia nueva
    (`tests/unit/application/test_ingestion_service.py`), 1 de
    extracción real de tablas DOCX
    (`tests/integration/test_text_extractors.py`). 260 pruebas en
    total, todas verdes (mismas 3 omitidas de siempre).
  - La lista de fragmentos de la pestaña Ingesta ahora muestra el tipo
    de fragmento cuando no es el genérico "texto" (p. ej. "tipo:
    tabla"), para poder validar visualmente que cada estrategia nueva
    marca los `Chunk` con el tipo esperado.
  - Limitación conocida (ver "Limitaciones conocidas"): `por_tabla`
    solo reconoce tablas en formato Markdown; para PDF, donde pypdf no
    reconstruye la estructura de una tabla, una tabla sigue
    fragmentándose como texto narrativo.
- **2026-07-27 — Comparador de modelos de embeddings A vs B (pestaña
  Ingesta).** Segunda pieza del orden pedido por el usuario (OCR →
  comparador de modelos → tipos documentales adicionales). Permite
  elegir dos perfiles de embeddings configurados (p. ej. `simetrico` vs
  `asimetrico_e5_large`), escribir una consulta y ver, lado a lado, los
  fragmentos mejor puntuados por cada modelo -- con las coincidencias
  resaltadas igual que en el buscador normal -- para decidir con datos
  reales cuál conviene antes de cambiar el perfil activo de un
  proyecto.
  - Decisión de alcance deliberada: el cálculo se hace **en memoria**,
    con similitud coseno pura (`domain/rag/entities.py:cosine_similarity`)
    sobre los fragmentos ya existentes del proyecto (o de una sola
    fuente si se marca "Solo esta fuente") -- no se crea un segundo
    índice persistido en Qdrant. `QdrantLocalVectorStore` usa un nombre
    de colección fijo (`"chunks"`), no parametrizado por perfil;
    soportar índices paralelos por perfil habría requerido la
    versión completa de la sección 5 de ADR-001 (múltiples índices por
    proyecto), un cambio mucho más invasivo que no se justifica todavía
    solo para comparar modelos puntualmente.
  - `application/rag/queries/compare_embedding_profiles.py` (nuevo):
    `CompareEmbeddingProfiles` recibe el repositorio de fragmentos y
    una fábrica `provider_factory: Callable[[str], EmbeddingProvider]`
    -- no importa infraestructura directamente, respetando ADR-001
    (aplicación nunca depende de infraestructura concreta). La fábrica
    real (`make_provider_for_profile`) solo se conecta en
    `app/bootstrap.py`, la raíz de composición.
  - Capacidad opcional otra vez: `RagService` acepta
    `embedding_provider_factory` y `available_embedding_profiles` como
    parámetros opcionales (`None` por defecto). Sin ellos, `RagService`
    se comporta exactamente igual que antes; `compare_profiles()` sin
    fábrica configurada lanza
    `EmbeddingProfileComparisonUnavailableError` con mensaje claro en
    vez de fallar en silencio o con un error críptico.
  - Nuevo método `ChunkRepository.list_for_project(project_id)` (puerto
    de dominio + implementación real en `SqlAlchemyChunkRepository` +
    doble de prueba en memoria) para poder comparar sobre todo el
    proyecto y no solo una fuente a la vez.
  - UI: sección nueva "Comparador de modelos de embeddings (A vs B)" en
    la pestaña Ingesta, con dos selectores de perfil, campo de
    consulta, casilla "Solo esta fuente" y resultados en `QTextBrowser`
    con resaltado reutilizando `search_highlighting.py`. Si la
    instalación tiene menos de 2 perfiles configurados, el comparador
    se deshabilita con un aviso explícito en vez de aparecer roto.
  - 17 pruebas nuevas (5 de `cosine_similarity` en el dominio, 7 del
    comparador en `application`, 4 de `RagService.compare_profiles`/
    `available_embedding_profiles`, 1 de `list_for_project` contra
    SQLite real). 245 pruebas en total, todas verdes (mismas 3
    omitidas de siempre: smoke test de UI sin `libEGL`/`libGL`, y 2
    pruebas de `fastembed` que necesitan red real hacia Hugging Face).
    Verificado además que `app/bootstrap.py` conecta correctamente la
    fábrica real (`make_provider_for_profile`) y la lista real de
    perfiles disponibles -- el intento de comparar sí llega hasta
    pedir la descarga del modelo de Hugging Face, deteniéndose solo por
    la falta de red de este entorno de construcción, no por un error de
    cableado.
- **2026-07-27 — OCR real para PDF escaneado (Módulo 4), dependencia
  opcional.** `PdfTextExtractor` ahora acepta un `ocr_engine` opcional
  (puerto `domain.ingestion.ports.OcrEngine`); cuando una página no
  produce texto vía pypdf, se rasteriza con PyMuPDF (`fitz`, sin
  binario externo adicional) y se reconoce con Tesseract real vía
  `pytesseract` (`infrastructure/extraction/ocr_engine.py`,
  `TesseractOcrEngine`, idioma por defecto `spa+eng`). Sin `ocr_engine`
  (valor por defecto), el comportamiento es exactamente el mismo que
  antes de Módulo 4 -- ningún llamador existente cambia de
  comportamiento sin pedirlo explícitamente.
  - Dependencia opcional de verdad: extra `ocr` en `pyproject.toml` +
    `requirements-ocr.txt` (pytesseract, Pillow, PyMuPDF) -- además
    requiere el binario de `tesseract` instalado en el sistema
    operativo (no lo instala pip). `app/bootstrap.py` solo conecta el
    motor real si `ocr_dependencies_available()` confirma que las
    librerías de Python están instaladas; si no, sigue construyendo
    `PdfTextExtractor` sin OCR, como siempre, y deja constancia en el
    log.
  - Un fallo de OCR (falta el binario, falta PyMuPDF) se captura por
    extracción completa, no por página: en cuanto falla una vez, dejan
    de reintentarse las páginas siguientes del mismo documento -- una
    razón clara en las advertencias basta, reintentar sería lento y
    repetitivo. El método reportado (`pdf_texto`, `pdf_ocr`,
    `pdf_texto+ocr`) refleja de qué páginas salió el texto realmente.
  - Pruebas con PDFs reales construidos con PyMuPDF insertando una
    imagen (sin capa de texto) por página -- reproduce fielmente el
    caso real sin necesitar un scanner físico ni un archivo de
    muestra. Incluye una prueba con Tesseract real de punta a punta
    (`lang="eng"`, porque este entorno de construcción solo tiene
    instalado el paquete de idioma inglés -- una máquina real debe
    instalar también `tesseract-ocr-spa` para los documentos en
    español de RAG STUDIO) y varias con un `OcrEngine` de prueba para
    el control de flujo (mezcla de páginas con/sin OCR, no reintentar
    tras fallar). 22 pruebas nuevas. 228 pruebas en total, todas
    verdes (3 omitidas: el smoke test de UI sin `libEGL`/`libGL`, y 2
    de `fastembed` que necesitan red completa).
  - Fuera de alcance de esta entrada (documentado en limitaciones):
    `SourceType.IMAGEN_ESCANEADA` como tipo de fuente independiente
    (archivos de imagen sueltos, no PDF) sigue sin extractor -- solo
    se cubrió "PDF con páginas escaneadas", que es lo que pedía el
    backlog ("OCR para PDF escaneado").

- **2026-07-26 — Correcciones de la primera ronda de validación visual
  manual (Proyectos, Fuentes, Metadatos), hecha por el usuario en su
  laptop real siguiendo `checklist_validacion_visual.md`.** Hallazgos
  reales y su corrección:
  - *Error crudo de Pydantic al agregar un campo tipo catálogo sin
    catalog_id.* El model_validator de `FieldDefinition` (dominio) ya
    lo detectaba, pero como `pydantic.ValidationError` crudo, y la UI
    lo mostraba tal cual (un mensaje técnico con jerga de Pydantic).
    Se agregó `CatalogRequiredForFieldTypeError` (dominio) y un chequeo
    explícito en `AddFieldDefinition`/`UpdateFieldDefinition` antes de
    construir el modelo, con el mismo estilo de mensaje claro que el
    resto de errores de la app.
  - *El combo "Catálogo" del diálogo de campo, y el sufijo
    "catálogo=..." en la lista de campos del esquema, mostraban el id
    crudo del catálogo en vez de su nombre* — imposible de identificar
    con más de un catálogo creado. Se corrigió pasando pares
    (id, nombre) al diálogo (mismo patrón que ya usaba el selector de
    catálogos) y agregando `_catalog_name()` para resolver el nombre al
    refrescar la lista de campos.
  - *"Crear esquema" no confirmaba éxito* — el usuario no sabía si
    había funcionado sin ver la lista cambiar. Se agregó un
    `QMessageBox.information` de confirmación.
  - *"Nuevo proyecto" con nombre vacío no avisaba nada* — se creía
    correcto no crear el proyecto, pero sin mensaje el usuario no sabe
    si funcionó o no. Se agregó una advertencia clara (solo cuando se
    confirma el diálogo con nombre vacío, no cuando se cancela).
  - *Registrar una fuente con la carpeta contenedora en "Ubicación" (no
    la ruta completa del archivo) fallaba tarde, en la pestaña Ingesta,
    con un `OSError` crudo del sistema de archivos* (`[Errno 21] Es un
    directorio: '...'`) — funcional (mostraba un diálogo de error, no
    tumbaba la app) pero con un mensaje técnico y en el momento
    equivocado. Dos correcciones: (1) se agregó un botón "Elegir
    archivo…" en el diálogo de registro de fuentes (`QFileDialog`, que
    por construcción nunca puede devolver un directorio) y, si el
    Título está vacío, se rellena con el nombre del archivo elegido;
    (2) se agregó `SourceLocationUnreadableError` (dominio) y
    `ExtractSourceText.execute` ahora envuelve cualquier `OSError` de
    `TextExtractor.extract` en ese error claro, con instrucciones de
    cómo corregirlo.
  - 4 pruebas nuevas + 1 actualizada (la que ya cubría el caso de
    catálogo faltante en edición, que antes esperaba `ValueError`
    genérico -- ahora espera `CatalogRequiredForFieldTypeError`
    específico). 186 pruebas en total, todas verdes.
  - Nota para el usuario: la fuente que ya registraste con la ruta de
    la carpeta (no del archivo) puede quedarse como está o eliminarse
    -- no hace falta borrarla para seguir probando; simplemente
    regístrala de nuevo con "Elegir archivo…" para continuar con la
    validación de la pestaña Ingesta.

- **2026-07-26 — Pestaña Fuentes: ver detalle al seleccionar + editar
  con bloqueo de campos estructurales.** A raíz de que el error de
  "carpeta en vez de archivo" (ver entrada anterior) solo fue visible
  hasta la extracción -- al seleccionar la fuente en la lista no se
  veía ningún dato para corregirlo antes -- se agregó:
  - Al seleccionar una fuente, un panel de detalle debajo de la lista
    ahora muestra todos sus datos (título, tipo, ubicación, área
    propietaria, nivel de acceso, estado de validación, vigencia,
    autoridad).
  - Un botón "Editar fuente" abre el mismo diálogo de registro,
    precargado con los datos actuales.
  - Los campos descriptivos (título, área propietaria, nivel de
    acceso) siempre son editables.
  - Los campos estructurales (ubicación, tipo de documento) solo son
    editables si la fuente **todavía no tiene texto extraído**. En
    cuanto existe una extracción, esos dos campos se bloquean en el
    diálogo (con una nota explicando por qué) y, aunque se intentaran
    forzar, `UpdateSourceDetails` (aplicación) los rechaza con
    `SourceStructuralFieldsLockedError` (dominio). La razón: cambiar el
    documento real de una fuente que ya fue extraída y fragmentada
    rompe la trazabilidad entre el texto indexado y su origen -- el
    camino correcto es registrar una fuente nueva indicando que
    sustituye a la anterior (`supersedes_source_id`, ya existente desde
    Etapa 2).
  - Backend nuevo: `Source.with_updated_details` (dominio),
    `UpdateSourceDetails` (comando de aplicación),
    `DocumentService.update_source_details`/`has_extraction`.
    `DocumentService` ahora depende también de `ExtractionRepository`
    (mismo patrón de dependencia entre contextos que ya usaba
    `FragmentSource`) para poder consultar si una fuente ya tiene
    extracción antes de permitir el cambio estructural.
  - 6 pruebas nuevas de backend + actualización de los puntos donde se
    construye `DocumentService` (app y pruebas existentes). 192
    pruebas en total, todas verdes.

- **2026-07-26 — Aviso de relevancia baja en la búsqueda semántica
  (pestaña Ingesta).** Hallazgo real: al probar la búsqueda con la
  palabra "Tiempo" sobre un plan de estudios sin relación temática, se
  obtuvieron resultados con score 0.14-0.28, y no había forma de saber
  si eso era correcto o un error -- la búsqueda semántica (similitud
  coseno) siempre devuelve los top-K vectores más cercanos, aunque
  ninguno sea realmente relevante. Se agregó una advertencia visible
  cuando el mejor score de la búsqueda no alcanza un umbral mínimo
  (`domain.rag.entities.DEFAULT_MIN_RELEVANT_SCORE = 0.35`,
  configurable vía `RagService.has_low_relevance(results, min_score=...)`):
  los resultados se siguen mostrando igual que antes (no se ocultan,
  siguen siendo información válida sobre qué hay más cerca), pero
  ahora aparece primero un aviso de "relevancia baja" con el mejor
  score obtenido, para que quede claro que probablemente el proyecto
  no tiene contenido relacionado con esa consulta. 10 pruebas nuevas
  (dominio + aplicación). 202 pruebas en total, todas verdes.
  - Nota para el usuario: 0.35 es un punto de partida razonable para
    el modelo simétrico por defecto (MiniLM), no un valor validado
    estadísticamente -- si en la práctica resulta muy sensible o muy
    laxo, es un solo número para ajustar.

- **2026-07-26 — Corrección de texto "letra por letra" en la
  extracción de PDF (pypdf).** Al investigar por qué la búsqueda de
  "Métodos Numéricos y Matlab" -- una frase que aparece literalmente
  en el PDF -- daba un score bajo (0.341) en vez de uno claramente
  alto, se encontró que el texto extraído tenía un artefacto real:
  ciertas palabras salían con cada letra separada por un espacio
  simple, p. ej. `3 e r . C u a t r i m e s t r e` en vez de
  `3er. Cuatrimestre` (visible en el panel "Extracción" de la pestaña
  Ingesta). Es un comportamiento conocido de `pypdf` con fuentes de
  tracking/justificado amplio: el motor de embeddings terminaba viendo
  16 tokens de una sola letra en vez de dos palabras, lo cual diluye
  mucho la calidad del vector -- una causa más probable del score bajo
  que la sola dilución por tamaño de chunk.
  - Se agregó `repair_letter_spaced_text()` en
    `infrastructure/extraction/text_extractors.py`, aplicado
    automáticamente a cada página extraída en `PdfTextExtractor`: junta
    corridas de 4 o más "palabras" de un solo carácter separadas por
    espacio simple, y reinserta un espacio donde una mayúscula sigue a
    una minúscula/dígito/puntuación (para recuperar límites de palabra
    en Title Case, frecuente en nombres de materias y encabezados). No
    es una reconstrucción perfecta -- un bloque completamente en
    mayúsculas queda unido sin cortes -- pero es muy superior a dejar
    el texto fragmentado letra por letra.
  - El umbral de 4+ letras consecutivas evita falsos positivos sobre
    texto normal en español, donde no es común encontrar 4 o más
    palabras de una sola letra seguidas (y, o, a, u, e).
  - 6 pruebas nuevas (la función pura + que el extractor de PDF la
    aplique sin romper el caso normal). 208 pruebas en total, todas
    verdes.
  - Nota para el usuario: vuelve a extraer el texto de la fuente
    "Electromecanica" (o cualquier otra que muestre este patrón en el
    panel de extracción) para que la corrección tome efecto -- el
    texto ya extraído y guardado no se corrige retroactivamente, hace
    falta re-extraer.

- **2026-07-26 — Segunda ronda de la corrección anterior: abreviaturas
  cortas letra-espaciadas que la primera versión no detectaba.** El
  usuario re-extrajo y re-probó: "Métodos Numéricos y Matlab" ya
  aparecía intacto en el texto extraído (la corrección anterior
  funcionó ahí), pero más abajo en el mismo documento seguía viéndose
  "3 e r.  Cuatrimestre" sin corregir. Causa: en ese caso solo la
  abreviatura del ordinal quedó letra-espaciada ("3 e r.", con el
  punto pegado a la "r" -- un token de 2 caracteres, no de 1), y la
  palabra siguiente ("Cuatrimestre") ya estaba intacta -- por eso la
  corrida detectada era de solo 3 tokens, por debajo del umbral
  mínimo de 4 que exigía la primera versión.
  - `repair_letter_spaced_text()` ahora también reconoce un token
    "letra + un signo de puntuación pegado" (p. ej. "r.") como parte
    de la corrida, y además corrige corridas cortas (2-3 tokens)
    cuando vienen seguidas de un espacio doble -- pypdf reproduce en
    el ancho del espacio el hueco real entre palabras del PDF
    original, así que un espacio doble justo después de la corrida es
    una señal adicional de que ahí termina una palabra real. Sin esa
    señal, las corridas cortas se siguen dejando intactas (para no
    fusionar, por ejemplo, dos encabezados de una sola letra en una
    tabla).
  - 2 pruebas nuevas (el caso real de la abreviatura corta + un caso
    negativo de control). 210 pruebas en total, todas verdes.
  - Nota para el usuario: igual que la corrección anterior, hace falta
    volver a extraer el texto para que aplique -- y como antes, no es
    una reconstrucción perfecta de límites de palabra en todos los
    casos, solo la mejora suficiente para que el modelo de embeddings
    no vea basura de un carácter.

- **2026-07-26 — Confirmado empíricamente: el tamaño de fragmento
  importa más que el texto para la calidad de búsqueda en documentos
  tipo lista (planes de estudio, catálogos).** Con el texto de
  extracción ya corregido (ver las dos entradas anteriores), el
  usuario probó la misma búsqueda ("Métodos Numéricos y Matlab") con
  tres tamaños de fragmento distintos, aislando así la variable de
  granularidad:
  - `por_encabezado` (sin encabezados Markdown reales en esta fuente,
    solo viñetas "•") -- 1 solo fragmento con las 352 tokens de todo
    el documento: score 0.244.
  - `por_tamaño`, 500 tokens objetivo -- 2 fragmentos: score 0.341.
  - `por_tamaño`, 80 tokens objetivo (política nueva `tamlow`) -- 15
    fragmentos: score 0.487, ya por encima del umbral de relevancia
    (0.35) -- el aviso de "relevancia baja" deja de aparecer.
  - Conclusión: para documentos que son básicamente listas cortas
    (una materia, un trámite, un requisito por línea), meter decenas
    de ítems distintos en un solo fragmento diluye el embedding de
    cada ítem individual -- ninguna consulta específica destaca frente
    a las demás. No fue necesario ningún cambio de código: el
    mecanismo de políticas de fragmentación por `document_type_code`
    (Etapa 3) ya permite crear una política con "Tokens objetivo" bajo
    para este tipo de documento sin afectar a otros.
  - Recomendación de uso (no una regla automática de la app todavía):
    para fuentes tipo lista/catálogo, usa `por_tamaño` con un
    "Tokens objetivo" bajo (60-100) en vez del valor por defecto (500,
    pensado para prosa continua). `por_encabezado` solo ayuda si la
    fuente tiene encabezados Markdown reales (`#`, `##`) -- si no los
    tiene, se comporta como un solo fragmento gigante.

- **2026-07-26 — Decisión de producto: el modelo de embeddings por
  defecto se queda como está (simétrico/MiniLM).** Con los datos
  reales del experimento ya confirmados (E5-large acierta mejor en
  preguntas de lenguaje natural, pero pesa 10× más: 2.25 GB vs. 252 MB,
  ~7 min vs. ~1 min de descarga, y sus scores viven en otra escala), se
  decidió no cambiar el default de ningún proyecto nuevo. Motivo
  implícito de la decisión: el costo de descarga/RAM no se justifica
  todavía para el uso actual, y el perfil `asimetrico_e5_large` ya
  queda disponible sin fricción para quien lo necesite (parámetro
  explícito o variable de entorno `RAGSTUDIO_EMBEDDING_PROFILE`, ver
  bitácora del 2026-07-26 sobre el modelo configurable). No hubo
  cambio de código -- esta entrada solo cierra la decisión pendiente
  que quedaba anotada en "Próximos pasos sugeridos".

- **2026-07-27 — Comparador de resultados de búsqueda: resaltado de
  coincidencias (pestaña Ingesta).** Primera pieza del punto 9 de
  "Próximos pasos sugeridos" (reranking queda pendiente, sin uso real
  todavía que lo justifique). Cada resultado de búsqueda ahora resalta
  con fondo amarillo las palabras de la consulta que aparecen en el
  fragmento, para entender mejor por qué un resultado quedó arriba de
  otro sin depender solo del score.
  - `self._search_results` pasó de `QListWidget` (solo texto plano) a
    `QTextBrowser` (rich text) en `ui/ingestion/panel.py`, ya que
    resaltar coincidencias requiere HTML/CSS inline dentro de cada
    resultado -- ninguna otra pestaña tenía este patrón, así que se
    introduce aquí por primera vez.
  - La lógica de qué palabras resaltar y cómo envolverlas en HTML vive
    en `ui/ingestion/search_highlighting.py` (nuevo), separada de
    `panel.py` a propósito: son funciones puras sin PySide6, así se
    pueden probar con pytest normal en cualquier entorno -- incluido
    este entorno de construcción, que no tiene las bibliotecas nativas
    de Qt (`libEGL`/`libGL`) para importar `panel.py` directamente.
    `extract_highlight_terms()` descarta conectores comunes del
    español (de, la, y, el...) y palabras de 1-2 letras -- resaltar
    "y" en cada resultado sería ruido, no señal.
  - La consulta usada para resaltar se guarda por separado
    (`self._pending_search_query`) en vez de leerse de nuevo del campo
    de texto al momento de mostrar resultados, para no resaltar la
    consulta equivocada si el usuario escribe algo distinto mientras la
    búsqueda todavía corre en segundo plano.
  - 9 pruebas nuevas (`tests/unit/ui/test_search_highlighting.py`,
    paquete de pruebas nuevo para lógica de `ui/` sin Qt). 219 pruebas
    en total, todas verdes (3 omitidas: el smoke test de UI -- sigue
    sin `libEGL`/`libGL` en este entorno, aunque `PySide6-Essentials`
    sí se pudo instalar y usarse para verificar sintaxis -- y las 2
    pruebas de `fastembed` que necesitan red completa).
- **2026-07-26 — `pytest -v` completo en la laptop real del usuario:
  186 pruebas, todas verdes, cero omitidas.** Corrida real en Linux
  (Python 3.12.3, pytest 9.1.1, entorno `.venv` propio del usuario, no
  el `venv` de este entorno de construcción). Confirma varias cosas a
  la vez: (1) las dos pruebas de `test_fastembed_provider.py` que aquí
  se omiten por falta de red real hacia Hugging Face sí pasan ahí
  (`test_embed_texts_returns_one_vector_per_text_with_consistent_dimension`,
  `test_similar_spanish_texts_are_closer_than_unrelated_ones`); (2) las
  pruebas de humo de la UI real (`test_ui_construction.py`, con PySide6
  de verdad, no el stub usado en este entorno para desarrollo) también
  pasan; (3) todas las pruebas nuevas de esta iteración (migraciones
  diferidas, cancelación cooperativa, prefijos de modelo asimétrico,
  perfil de embeddings configurable) pasan igual fuera de este entorno
  de construcción, no solo aquí. En este entorno la misma corrida da
  183 pasadas + 3 omitidas (186 - 3 = 183): la diferencia es
  exactamente esas 3 pruebas dependientes de red/UI real, esperado y
  ya documentado, no una discrepancia sin explicación. Pendiente:
  Windows y macOS (sección "Próximos pasos"), y la validación visual
  manual de las 4 pestañas con una fuente real (que `pytest` no
  cubre).
- **2026-07-26 — Modelo de embeddings configurable por perfil (decisión
  del usuario: opción explícita, no nuevo default).** Tras confirmar
  con datos reales que el modelo asimétrico mejora la búsqueda (ver la
  entrada de abajo), se le preguntó al usuario qué hacer con ese
  hallazgo: cambiar el default para todos, dejarlo como opción
  configurable, o no tocar nada. Eligió la opción configurable.
  Implementación: `make_provider_for_profile(profile, cache_dir=None)`
  en `fastembed_provider.py` resuelve un perfil corto (`"simetrico"`
  default, `"asimetrico_e5_large"`) a un `EmbeddingProvider` concreto,
  sin exponer nombres de modelo/prefijos crudos; `AppSettings` gana un
  campo `embedding_profile`, resuelto en `load_settings()` con
  prioridad parámetro explícito > variable de entorno
  `RAGSTUDIO_EMBEDDING_PROFILE` > default; `bootstrap()`/`start()`
  aceptan el mismo parámetro y lo pasan hasta `load_settings`. Nadie
  que no lo pida ve un cambio: el default sigue siendo
  `"simetrico"` en todos los call-sites existentes (`run_app.py`,
  `demo_plan_estudios.py`, todos los fixtures de prueba). 11 pruebas
  nuevas (resolución de perfil en `load_settings`, wiring correcto en
  `bootstrap` con y sin perfil explícito, error claro con un perfil
  desconocido) — ninguna requiere red, porque la carga real del modelo
  es perezosa. 183 pruebas en total, todas verdes. Documentado en
  README cómo activarlo (`RAGSTUDIO_EMBEDDING_PROFILE=asimetrico_e5_large
  python run_app.py`) junto con su costo y la advertencia de que no se
  puede mezclar con un índice ya construido con el otro modelo
  (`EmbeddingDimensionMismatchError`, comportamiento ya existente de
  Etapa 4, no nuevo).
- **2026-07-26 — Resultado real del experimento de modelo asimétrico,
  corrido por el usuario: confirma la hipótesis, con una salvedad de
  costo.** El usuario corrió `python experimento_modelo_asimetrico.py`
  en su laptop (con internet completo, sin el bloqueo de red de este
  entorno de construcción). Resultado para las 3 búsquedas de ejemplo
  sobre el plan de estudios real:
  - *"¿Qué materias se llevan en el primer cuatrimestre?"* —
    **simétrico (MiniLM)**: top-3 = 12vo, 13vo, 10mo Cuatrimestre
    (scores 0.26-0.30, ninguno es el correcto). **Asimétrico
    (E5-large)**: top-3 = **1er. Cuatrimestre (0.860, #1)**, 11vo
    (0.853), 6to (0.841) — acierta el resultado correcto en primer
    lugar. Mejora clara y contundente, justo el caso que motivó el
    experimento.
  - *"estadística e investigación de operaciones"* — **simétrico**:
    6to (0.496, correcto: tiene "Investigación de Operaciones I"), 9no
    (0.494), 8vo (0.479) -- los dos últimos sin relación obvia con la
    consulta. **Asimétrico**: 6to (0.836, "Investigación de Operaciones
    I"), 7mo (0.825, "Investigación de Operaciones II"), 4to (0.825,
    "Estadística I") -- los tres resultados son directamente relevantes
    a la consulta. Mejora también aquí, no solo en el caso que fallaba.
  - *"optativas de idioma"* — ambos modelos devuelven cuatrimestres
    distintos entre sí (3er/2do/4to el simétrico; 8vo/4to/6to el
    asimétrico) y ninguno permite confirmar cuál acertó mejor sin
    revisar el documento original a detalle (el plan de estudios no
    parece nombrar una "optativa de idioma" de forma literal) --
    resultado no concluyente para esta consulta en particular.
  - Costo observado: el modelo asimétrico descargó 2.25 GB (contra 252
    MB del simétrico) y tardó ~7 minutos en descargarse la primera vez
    (contra ~1 minuto); sus scores de similitud viven en una escala muy
    distinta (0.82-0.86 típicamente, contra 0.26-0.50 del simétrico) --
    consistente con lo ya anotado en limitaciones sobre por qué no se
    puede comparar un score absoluto entre modelos.
  - Conclusión: el diagnóstico de la limitación (modelo simétrico
    penaliza preguntas en lenguaje natural contra contenido tipo lista)
    queda confirmado con datos reales, no solo con hipótesis. Cambiar
    el modelo por defecto del proyecto a uno asimétrico es una decisión
    de producto pendiente de acordar con el usuario (10× más pesado en
    descarga/RAM/tiempo de indexado, a cambio de mejor calidad en
    preguntas naturales) -- no se cambió unilateralmente el default.
- **2026-07-26 — Soporte para modelos de embeddings asimétricos +
  intento de experimento real (bloqueado por red, no por código).**
  `domain.rag.ports.EmbeddingProvider` gana un método `embed_query`
  (con default que delega en `embed_texts`, así que ningún adaptador ni
  prueba existente cambia de comportamiento); `SemanticSearch` ahora
  llama a `embed_query` en vez de `embed_texts` para la consulta.
  `FastEmbedEmbeddingProvider` acepta `query_prefix`/`passage_prefix`
  (vacíos por defecto) y aplica cada uno del lado que corresponde;
  `make_multilingual_e5_large_provider()` es una fábrica lista para
  `intfloat/multilingual-e5-large` (único modelo multilingüe asimétrico
  que trae empaquetado `fastembed` — no incluye `bge-m3` ni
  `multilingual-e5-base`) con los prefijos `"query: "`/`"passage: "`
  que pide la tarjeta de ese modelo en Hugging Face. 6 pruebas nuevas
  (con un modelo falso vía monkeypatch, sin red) verifican que los
  prefijos se aplican del lado correcto y que el comportamiento
  simétrico por defecto no cambió. Se construyó también
  `experimento_modelo_asimetrico.py` (raíz del proyecto, mismo patrón
  que `demo_plan_estudios.py`): corre el pipeline completo dos veces
  sobre el plan de estudios real, una vez por modelo, cada una en su
  propia instalación temporal desechable (no toca el proyecto real del
  usuario), e imprime los resultados de las mismas 3 búsquedas de
  ejemplo para comparar de lado a lado. Se intentó correrlo de verdad
  en este entorno de construcción: la descarga del modelo asimétrico
  falló con `403 Forbidden` de Hugging Face (tras instalar `socksio`,
  que sí hacía falta para el proxy SOCKS del entorno) — a diferencia
  del modelo simétrico por defecto, que en este mismo entorno sí se
  descarga sin problema (confirmado varias veces en esta iteración).
  Es decir: la causa es una restricción de red específica de este
  entorno de construcción hacia ese modelo en particular, no un error
  de la implementación — se documenta así en vez de simular un
  resultado. 172 pruebas en total, todas verdes. Falta que el usuario
  corra `python experimento_modelo_asimetrico.py` en su laptop (con
  salida completa a internet) para obtener la comparación real.
- **2026-07-25 — Cancelación cooperativa real en extracción y
  fragmentación.** `ExtractSourceText.execute` y `FragmentSource.execute`
  ahora aceptan un parámetro `is_cancelled: Callable[[], bool]`
  (por defecto `lambda: False`, así que ningún llamador existente —
  scripts, pruebas — cambia de comportamiento) y lo revisan antes de
  persistir; `FragmentSource` también lo revisa en cada vuelta del
  bucle que arma los `Chunk`, el único punto real de la Etapa 3 con un
  bucle largo. Si se detecta la cancelación, la función devuelve `None`
  sin llamar a `save`/`delete_for_source`/`save_many` — los datos
  anteriores de la fuente quedan intactos. `IngestionService` expone el
  mismo parámetro hacia `ui/ingestion/panel.py`, que ahora pasa
  `handle.is_cancelled` al enviar el trabajo a segundo plano
  (`_on_extract`/`_on_fragment`); el mensaje de `_poll_active_job` para
  el estado "cancelado" distingue extracción/fragmentación (no se
  guardó nada nuevo) de indexación/búsqueda (corren hasta terminar
  igual que antes — ver limitaciones). 4 pruebas nuevas confirman: se
  cancela antes de empezar (extracción y fragmentación), se cancela
  después de "extraer" pero antes de guardar, y se cancela a la mitad
  del bucle de fragmentos — en los tres casos no se persiste nada y los
  datos previos (si había) no se tocan. 166 pruebas en total, todas
  verdes. No se tocó `IndexSource`/`RagService.search` (quedan sin
  cancelación real) porque son llamadas únicas a `embed_texts`/`upsert`
  sin un bucle propio; se documenta como límite conocido, no como
  bucle pendiente de revisar.
- **2026-07-25 — Bug real reportado por el usuario: `sqlite3.OperationalError:
  no such table: index_info` al abrir un proyecto existente en la GUI, y
  corrección arquitectónica de fondo.** El usuario compartió el
  traceback completo al correr `run_app.py` y seleccionar un proyecto
  ya existente (`ui/ingestion/panel.py` → `set_active_project` →
  `_refresh_index_info` → `rag_service.get_index_info` →
  `SqlAlchemyIndexInfoRepository.get`). Causa raíz: todos los
  repositorios SQLAlchemy (`repositories.py`, `document_repositories.py`,
  `ingestion_repositories.py`, `metadata_repositories.py`,
  `rag_repositories.py`) seguían el mismo patrón —
  `if not db_path.exists(): ensure_project_layout(...); upgrade_project(db_path)`
  — es decir, solo corrían las migraciones Alembic la primera vez que
  se creaba el archivo `project.db`. Un proyecto creado (o solo abierto)
  antes de que existiera la migración `0004_index_info` en el código
  (como el proyecto real del usuario, generado con `demo_plan_estudios.py`
  en una corrida anterior) nunca vuelve a pasar por `upgrade_project`
  una vez que el archivo ya existe en disco, así que se queda
  permanentemente en su esquema viejo aunque el código ya conozca
  migraciones nuevas — un problema general, no exclusivo de
  `index_info`: cualquier migración futura tendría el mismo defecto
  para proyectos ya creados. Corrección: se añadió
  `ensure_project_db(paths, project_id)` en
  `infrastructure/database/migrations.py`, que siempre corre
  `ensure_project_layout` + `upgrade_project(db_path)` sin condicionarlo
  a que el archivo exista — seguro porque Alembic ya es idempotente
  (guarda la revisión aplicada en su propia tabla `alembic_version` y
  solo aplica las migraciones pendientes). Se reemplazaron los 8
  call-sites del patrón viejo en los 5 archivos de repositorios por
  esta única función. 2 pruebas nuevas de regresión simulan un
  `project.db` "viejo" (con solo 0001-0003 aplicadas) y confirman que
  al abrirlo con el código actual se aplica 0004 automáticamente, sin
  error — una a nivel de migración (`ensure_project_db` directo) y otra
  reproduciendo la llamada exacta que falló en la GUI
  (`SqlAlchemyIndexInfoRepository.get`). 162 pruebas en total (160 + 2
  nuevas), todas verdes. El usuario solo necesita volver a abrir
  `run_app.py`; no requiere ningún paso manual de migración — la
  próxima vez que se abra ese proyecto, `0004` se aplica sola.
- **2026-07-24 — Segunda corrida real tras el filtro de encabezados:
  el filtro funcionó, pero queda un límite de calidad más de fondo.**
  El usuario volvió a correr `demo_plan_estudios.py` después de la
  corrección de `IndexSource`: "Plan de Estudios" ya no aparece
  (15 fragmentos indexados en vez de 16, confirmado). Pero la primera
  búsqueda ("¿Qué materias se llevan en el primer cuatrimestre?")
  siguió sin ubicar "1er. Cuatrimestre" entre los tres mejores
  resultados. Se descartó que fuera otro bug: es el modelo de
  embeddings (`paraphrase-multilingual-MiniLM-L12-v2`, pensado para
  comparar frases parecidas entre sí, no preguntas contra listas de
  materias sin descripción) combinado con un contenido fuente que es
  literalmente solo nombres de materias, sin texto narrativo. Con el
  usuario se decidió documentar el hallazgo como limitación conocida
  en vez de cambiar de modelo ahora — comparar modelos de embeddings
  ya estaba fuera del alcance acordado para el núcleo de la Etapa 4.
- **2026-07-24 — Primera corrida real de punta a punta (`fastembed`
  real, en la laptop del usuario) y hallazgo + corrección de calidad
  de búsqueda.** El usuario corrió `demo_plan_estudios.py` con
  internet: se descargó el modelo (384 dimensiones), se indexaron los
  16 fragmentos y las tres búsquedas de ejemplo devolvieron resultados
  reales — primera confirmación end-to-end de las Etapas 1-4 con
  embeddings de verdad, no con dobles de prueba. Al revisar los
  resultados se encontró un problema real: en 2 de las 3 búsquedas, el
  fragmento "Plan de Estudios" (un encabezado sin cuerpo propio, solo
  agrupa a los cuatrimestres siguientes) ganaba por encima de
  fragmentos con contenido real y obviamente más relevante. Se
  corrigió en `IndexSource` (`application/rag/commands/index_source.py`):
  antes de embeber/indexar, se descartan los `Chunk` cuyo texto es
  exactamente su `section_title` (sin más contenido) — solo aplica a
  fragmentos con encabezado (`POR_ENCABEZADO`), nunca a fragmentos
  cortos legítimos sin encabezado (`POR_TAMANIO`/`DOCUMENTO_COMPLETO`).
  Esos fragmentos siguen existiendo como `Chunk` normal (se ven en la
  pestaña Ingesta), solo se excluyen del índice vectorial. 3 pruebas
  nuevas (160 en total) confirman: se descarta un encabezado sin
  cuerpo, se conserva un fragmento corto sin encabezado, y una fuente
  donde *todos* sus fragmentos son encabezados sin cuerpo indexa 0 sin
  error. Se volvió a verificar contra el documento real (con un
  embedder determinístico, sustituido solo para esta verificación) que
  "Plan de Estudios" ya no aparece en los resultados.
- **2026-07-24 — `demo_plan_estudios.py`: pipeline real de punta a
  punta sobre un documento real.** El usuario compartió `plan de
  estudios ingenieria industrial.docx` (con texto real, a diferencia
  de los dos PDF-imagen anteriores) y pidió continuar con los
  próximos pasos. Se construyó un script de demostración que usa
  `app.lifecycle.start()` (la instalación real, la misma que abre
  `run_app.py`) para registrar la fuente, extraer su texto (2423
  caracteres, método `docx`), fragmentarla por encabezado (16
  fragmentos — título, "Plan de Estudios" y un fragmento por cada uno
  de los 14 cuatrimestres), indexarla y correr tres búsquedas
  semánticas de ejemplo. Es idempotente: si se corre dos veces,
  reutiliza el proyecto y la fuente existentes en vez de duplicarlos
  (se verificó explícitamente). El paso de indexación con `fastembed`
  real no se pudo ejecutar en este entorno de construcción (sin
  salida a Hugging Face, limitación ya conocida) — se verificó toda la
  lógica del script sustituyendo temporalmente el proveedor de
  embeddings por uno determinístico solo para esa verificación local
  (el script que queda en el repositorio usa `fastembed` real, sin
  sustituciones); falta que el usuario lo corra en su laptop con
  internet para ver los resultados de búsqueda con embeddings reales.
- **2026-07-24 — Interfaz de indexación y búsqueda semántica (Etapa
  4).** Se agregó una tercera sección ("RAG: indexación y búsqueda
  semántica") a `ui/ingestion/panel.py`: botón "Indexar esta fuente"
  (llama a `RagService.index_source` en segundo plano, mismo patrón
  que extraer/fragmentar), una etiqueta con el estado del índice del
  proyecto (modelo, dimensiones, cantidad de fragmentos indexados —
  se refresca en cuanto hay un proyecto activo, no solo tras indexar),
  y una búsqueda semántica (campo de texto + casilla "Solo esta
  fuente" + botón "Buscar", también en segundo plano porque embeber la
  consulta puede necesitar red la primera vez) con resultados que
  muestran score, fuente, sección y un recorte del texto. Verificado
  con un arnés de comportamiento (`ThreadJobRunner` real, embedder
  determinístico en vez de FastEmbed real para no depender de red)
  que indexa una fuente real de dos fragmentos, busca por texto sobre
  todo el proyecto y filtrando por fuente, y confirma que el estado
  del índice se limpia y se recupera correctamente al cambiar de
  proyecto; y con un arnés de regresión que confirma que extracción,
  fragmentación y el camino de falla (tipo de fuente no soportado)
  siguen funcionando igual después del cambio. Se corrigieron dos
  notas del README que habían quedado desactualizadas desde la
  iteración anterior (el VectorStore ya existía; ya hay interfaz para
  RAG) — quedaban contradiciendo el resto del documento.
- **2026-07-24 — corrección: `pyproject.toml` de la carpeta del
  usuario tenía la configuración de paquetes del entorno de
  construcción (`package-dir`/`packages.find` apuntando a `src/`),
  que no existe en esta carpeta** (aquí el código vive en la raíz).
  Se introdujo al copiar el archivo completo desde el entorno de
  construcción en la iteración anterior sin ajustar esa sección —
  `pip install -e .` fallaba con "'src' does not exist" en un entorno
  de pruebas nuevo. Se corrigió a
  `packages.find.include = ["app*", "application*", "domain*", "infrastructure*", "plugins*", "ui*", "workers*"]`,
  válido para el layout real de esta carpeta; se detectó al preparar
  un entorno de pruebas nuevo para verificar esta misma iteración, no
  por un reporte del usuario.
- **2026-07-24 — Se compartieron dos documentos reales del piloto
  (`ADMINSTRACION F.pdf`, `ADMINSTRACION V.pdf`, Universidad de León)
  para probar la Etapa 3/4 de punta a punta.** Al revisar con
  `pypdf.PdfReader.extract_text()` se confirmó que ambos son fotos de
  un plan de estudios y un volante de admisión exportadas a PDF (los
  nombres internos son `ADMINSTRACION F.jpg`/`ADMINSTRACION V.JPG`),
  sin capa de texto: solo se recupera el encabezado de impresión de
  Google Drive (111 caracteres, ni una palabra del contenido real).
  No se simuló una prueba de todas formas — se reportó el límite
  (choca con "Sin OCR", ya documentado) y, con el usuario, se decidió
  posponer la prueba con documentos reales y avanzar en su lugar con
  la interfaz de RAG (este mismo commit).
- **2026-07-24 — Etapa 4 (RAG — núcleo) completa: indexación
  vectorial + búsqueda semántica.** Dominio (`domain/rag`:
  `IndexInfo`, `VectorPoint`, `VectorSearchHit`, puertos
  `EmbeddingProvider`/`VectorStore`/`IndexInfoRepository`),
  adaptadores reales (`infrastructure/vectorstores/qdrant_local_store.py`
  sobre `qdrant-client` en modo local;
  `infrastructure/embeddings/fastembed_provider.py` sobre `fastembed`
  con modelo multilingüe local), persistencia (`index_info` vía
  migración `0004`), casos de uso (`application/rag`: `IndexSource`,
  `SemanticSearch`, `RagService`) y 30 pruebas nuevas (157 en total,
  más 2 omitidas explícitamente por falta de red hacia Hugging Face
  en este entorno — ver limitaciones): unitarias de las entidades y de
  `RagService` con dobles de prueba (`FakeEmbeddingProvider` con
  similitud de coseno real para que el orden de resultados sea
  significativo, `FakeVectorStore`, `InMemoryIndexInfoRepository`);
  de integración con `qdrant-client` real (crear colección, subir,
  buscar con y sin filtro, borrar por fuente, aislamiento entre
  proyectos, reapertura sin bloqueo de archivo); de integración con
  `fastembed` real (se omiten solo si no hay red, con motivo
  explícito, no en silencio); de punta a punta sobre un `AppContext`
  real (`ChunkRepository` y `VectorStore` de producción, embedder
  determinístico para no depender de red); y de portabilidad
  `.agentproj` (cuarta confirmación de que el empaquetador no
  necesita cambios, ahora incluyendo el directorio del índice
  vectorial). Se corrigió antes de construir: ADR-001 nombraba
  "Qdrant Edge" como adaptador por defecto; al confirmar la
  documentación oficial vigente se encontró que Qdrant Edge es un
  producto real pero distinto (beta, para dispositivos
  embebidos/IoT, con solicitud de acceso) — se corrigió hacia el
  Local Mode estándar de `qdrant-client`, confirmado con pruebas
  reales en este mismo entorno antes de escribir el adaptador
  definitivo. También se amplió `ChunkRepository` (Etapa 3) con un
  método `get(project_id, chunk_id)` — `SemanticSearch` lo necesita
  para reconstruir el `Chunk` completo a partir del id que devuelve
  el índice vectorial, y no existía antes porque Etapa 3 solo
  necesitaba listar por fuente.
- **2026-07-24 — Investigación: API vigente de Qdrant embebido/local
  para la Etapa 4.** Se confirmó en la documentación oficial
  (`qdrant.tech/documentation/quickstart` y el README de
  `github.com/qdrant/qdrant-client`, versión publicada más reciente:
  v1.18.0) que el paquete `qdrant-client` (`pip install qdrant-client`)
  soporta un **modo local sin servidor** que coincide con la decisión
  de ADR-001 ("Qdrant local"): `QdrantClient(":memory:")` para uso
  efímero (pruebas) o `QdrantClient(path="ruta/a/db")` para persistir
  en disco — este segundo es el candidato natural para RAG STUDIO,
  con un directorio Qdrant por proyecto igual que hoy existe un
  `project.db` por proyecto. La API de operaciones es la misma en modo
  local que en modo servidor (no hay una API distinta que aprender):
  `create_collection(collection_name, vectors_config=VectorParams(size=N, distance=Distance.COSINE))`
  para crear una colección; `upsert(collection_name, points=[PointStruct(id=.., vector=[...], payload={...})])`
  para insertar vectores con metadatos; `query_points(collection_name, query=vector, limit=N).points`
  para buscar (esta es la función vigente; `search()` es la forma
  antigua); y `Filter(must=[FieldCondition(key=.., match=MatchValue(value=..))])`
  o `Range(gte=..)` para filtrar por metadatos del payload al buscar.
  También existe `AsyncQdrantClient` con los mismos métodos en versión
  `async`, por si conviene más adelante. La documentación oficial
  describe el modo local como recomendado para "desarrollo,
  prototipado y pruebas", con la opción de pasar a modo servidor solo
  si se necesita escalar — consistente con el alcance actual de RAG
  STUDIO. **No se implementó nada todavía**: esta es solo la
  confirmación de API solicitada para decidir el adaptador
  `VectorStore` antes de construir la Etapa 4 (ver "Próximos pasos
  sugeridos").
- **2026-07-24 — Botón "Cancelar" en el panel de Ingesta.** Se agregó
  `IngestionPanel._btn_cancel`, habilitado únicamente mientras hay un
  trabajo en curso (se refactorizó el manejo de estado de los
  controles para distinguir "listo" —proyecto y fuente activos— de
  "ocupado" —job activo— con `_apply_button_states()`). Se verificó
  con un arnés que usa un extractor de prueba deliberadamente lento
  (para poder pulsar "Cancelar" mientras el trabajo sigue en hilo) que
  el flujo completo es honesto: el trabajo termina y persiste sus
  datos igual, el estado final se reporta como "cancelado" en vez de
  "completado", y el panel refresca la vista con el resultado real en
  vez de ocultarlo — ver limitación documentada arriba.
- **2026-07-24 — UI de Ingesta (pestaña "Ingesta", Módulos 4-5)
  construida sobre el backend de Etapa 3.** `MainWindow` pasa a tener
  4 pestañas: se agregó `ui/ingestion/panel.py` (`IngestionPanel`) con
  una sección de extracción (botón, vista previa de texto,
  advertencias) y una de fragmentación (document_type_code,
  estrategia, tokens objetivo/solapamiento/mínimo, botón "Guardar
  política", lista de fragmentos resultantes con sección y páginas).
  Ambas operaciones se envían a segundo plano con el nuevo
  `BackgroundJobs.submit_task(fn)` (genérico: envuelve cualquier
  llamada de application, no solo la tarea de demostración de
  Etapa 1), respetando la regla de no bloquear el hilo de la interfaz.
  `SourcesPanel` ganó la señal `source_selected` (mismo patrón que
  `ProjectsPanel.project_selected`) para que Ingesta sepa sobre qué
  fuente operar dentro del proyecto activo. Se agregó
  `application/ingestion/options.py` para exponer
  `FRAGMENTATION_STRATEGY_OPTIONS` sin que `ui/` importe `domain/`
  directamente. Verificado con importación real de la ventana de 4
  pestañas (PySide6 sustituido por un doble ampliado, ya que este
  entorno de construcción no tiene Qt) y con un arnés de comportamiento
  que ejercita extracción y fragmentación reales usando el
  `ThreadJobRunner` de verdad (hilos de Python reales, no un doble),
  incluyendo el camino de falla (tipo de fuente no soportado): se
  confirmó que se muestra como error, no como una excepción sin
  capturar.
- **2026-07-24 — Etapa 3 (ingesta — núcleo) completa.** Dominio
  (`domain/ingestion`: `Chunk`, `FragmentationPolicy`,
  `ExtractionRecord`, `FragmentationStrategy`, y `splitting.py` con
  las funciones puras de fragmentación), extractores de texto reales
  (`infrastructure/extraction`: TXT/Markdown directo, DOCX vía
  `python-docx` con normalización de encabezados a Markdown, PDF vía
  `pypdf` con rastreo de saltos de página), casos de uso
  (`application/ingestion`: `ExtractSourceText`, `FragmentSource`,
  `SetFragmentationPolicy`), persistencia (tablas `extraction_record`,
  `chunk`, `fragmentation_policy` vía migración `0003`) y 33 pruebas
  nuevas (128 en total): unitarias de `splitting.py` y las entidades,
  de `IngestionService` con dobles de prueba, de integración con
  archivos reales generados en la propia prueba (incluye un PDF válido
  de una página escrito a mano en sintaxis PDF cruda, sin depender de
  una librería adicional solo para la fixture), de los repositorios
  SQLAlchemy reales, de punta a punta sobre un `AppContext` real
  (`bootstrap()` completo), y de portabilidad `.agentproj` (tercera
  confirmación de que el empaquetador no necesita cambios). Fuente
  principal: `RAG STUDIO INVESTIGACION.odt` (actividades A2 y A3,
  Módulos 4-6).
- **2026-07-24 — Pulido de la UI de Metadatos: edición de campos y
  gestión completa de catálogos.** Ampliación de
  `CatalogRepository` con `list_catalogs`, `delete_catalog` y
  `delete_entry` (puerto + implementación SQLAlchemy). Nuevos casos de
  uso: `UpdateFieldDefinition` (edita etiqueta/obligatoriedad/catálogo
  de un campo; field_id y tipo de dato quedan inmutables una vez
  creado el campo), `UpdateCatalog` (renombrar), `DeleteCatalog`
  (bloqueado con `CatalogInUseError` si algún campo del esquema activo
  todavía lo referencia), `UpdateCatalogEntry` (editar etiqueta/padre
  jerárquico) y `DeleteCatalogEntry` (bloqueado con
  `CatalogEntryInUseError` si alguna fuente ya tiene ese código
  guardado como valor de metadatos — el chequeo recorre las fuentes
  del proyecto igual que el reporte de cobertura). `MetadataPanel`
  ahora tiene un selector de catálogos poblado desde `list_catalogs`
  (ya no una lista en memoria que se perdía al reabrir la app),
  botones de renombrar/eliminar catálogo y editar/eliminar entrada, y
  un botón "Editar campo" con diálogo prellenado. 13 pruebas nuevas en
  `test_metadata_service.py` (75 en total) y un arnés de
  comportamiento ampliado que ejercita cada botón nuevo contra los
  servicios reales, incluyendo los dos bloqueos de seguridad
  (catálogo en uso, entrada en uso).
- **2026-07-24 — UI de Documentos/Metadatos (Módulos 2-3) construida
  sobre Etapa 2.** `MainWindow` ahora es un `QTabWidget` con tres
  pestañas: Proyectos (`ui/projects/panel.py`, extraído del
  `main_window.py` anterior), Fuentes (`ui/sources/panel.py`) y
  Metadatos (`ui/metadata/panel.py`). `ProjectsPanel` emite la señal
  `project_selected` para que las otras dos pestañas sepan sobre qué
  proyecto operar. Se agregaron `application/documents/options.py` y
  `application/metadata/options.py` para exponer los vocabularios de
  los enums de dominio (tipos de fuente, niveles de acceso, tipos de
  dato) sin que `ui/` importe `domain/` directamente. Verificado con
  `py_compile`, con importación real de todos los módulos nuevos
  (sustituyendo PySide6 por un doble mínimo, ya que este entorno de
  construcción no tiene Qt), y con un arnés de comportamiento que
  ejercita cada botón/acción contra los servicios reales
  (`DocumentService`, `MetadataService`) con repositorios en memoria:
  registro de fuentes, transiciones de validación válidas e
  inválidas, creación de esquema y creación duplicada, alta de campo
  con catálogo obligatorio y su rechazo cuando falta, y el reporte de
  cobertura antes/después de completar los campos obligatorios de una
  fuente. Ese arnés encontró un bug real en
  `Source.transition_validation_to` (ver abajo) antes de llegar al
  usuario.
- **2026-07-24 — corrección: `transition_validation_to` fallaba con
  `AttributeError` en vez de `InvalidValidationTransitionError`
  cuando el destino llegaba como string plano** (el caso normal desde
  un combo box de la UI) **y la transición no estaba permitida.** El
  método asumía que `target` ya era un `SourceValidationStatus` y
  llamaba a `target.value` al construir el mensaje de error; con un
  string plano eso no existe. Se agregó `target =
  SourceValidationStatus(target)` al inicio del método, válido tanto
  para el enum como para su valor en string. Se añadió la prueba
  `test_transition_accepts_plain_string_target` en
  `tests/unit/domain/test_source_entity.py`. Ninguna prueba previa lo
  detectó porque todas llamaban con el enum directamente, nunca con
  string.
- **2026-07-24 — Etapa 2 (gobierno documental) completa.** Dominio
  (`domain/documents`, `domain/metadata`), casos de uso
  (`application/documents`, `application/metadata`), persistencia
  (tablas `source`, `metadata_schema`, `field_definition`, `catalog`,
  `catalog_entry`, `source_metadata_value` vía migración `0002`) y 32
  pruebas nuevas (62 en total). Verificado que las fuentes y el
  metamodelo viajan dentro de `.agentproj` sin cambios en el
  empaquetador. Fuente principal: `RAG STUDIO INVESTIGACION.odt`
  (actividad A1) y `RAG STUDIO.odt` (Módulos 2-3).
- **2026-07-24 — UI validada en máquina real.** `pytest` (31/31, sin
  omisiones) y `run_app.py` corridos en una laptop Linux con Qt
  instalado: la ventana muestra la lista de proyectos y "Simular tarea
  larga" avanza la barra de progreso sin congelar la interfaz — queda
  confirmado el criterio de no bloqueo de esta iteración.
- **2026-07-24 — corrección de ruta de migraciones.** `infrastructure/database/migrations.py`
  ubicaba `migrations/` asumiendo que el código vivía siempre bajo
  `src/` (`parents[3]` fijo). Al extraerse el esqueleto sin ese nivel
  `src/`, la ruta calculada quedaba un nivel arriba de la raíz del
  repositorio y Alembic fallaba con `Path doesn't exist`. Se cambió por
  una búsqueda hacia arriba de `pyproject.toml`, válida con o sin
  layout `src/`. Sin este cambio, cualquier extracción que perdiera el
  nivel `src/` rompía todas las pruebas de integración y de humo.

## Estructura

```
src/
├── app/            bootstrap, configuración, ciclo de vida, registros
├── ui/             interfaz PySide6 (solo llama a application)
│   ├── projects/   pestaña Proyectos (ProjectsPanel, MainWindow con pestañas)
│   ├── sources/    pestaña Fuentes (SourcesPanel)
│   ├── metadata/   pestaña Metadatos (MetadataPanel)
│   ├── ingestion/  pestaña Ingesta (IngestionPanel, con sub-pestañas):
│   │               pipeline reproducible + extracción + fragmentación +
│   │               indexación/búsqueda (semántica/textual/híbrida) +
│   │               comparador de modelos de embeddings
│   ├── conversational/ pestaña Diseño conversacional (ConversationalPanel,
│   │               con sub-pestañas): intenciones, variables, guardrails,
│   │               canalización, simulador
│   ├── quality/    pestaña Calidad (QualityPanel, con sub-pestañas):
│   │               banco de pruebas, evaluación (semáforos/regresión)
│   ├── release/    pestaña Liberación (ReleasePanel): compuertas de
│   │               avance, dictamen, historial de liberaciones
│   └── plugins/    pestaña Complementos (PluginsPanel) -- global, no
│                   depende de un proyecto activo: registrar/activar/
│                   validar plantillas, proveedores, importadores,
│                   evaluadores personalizados
├── domain/
│   ├── projects/       Etapa 1: Project, Configuration
│   ├── documents/      Etapa 2: Source (fuentes gobernadas)
│   ├── metadata/       Etapa 2: MetadataSchema, FieldDefinition, Catalog
│   ├── ingestion/      Etapa 3: Chunk, FragmentationPolicy, ExtractionRecord, splitting.py,
│   │                   normalization.py (normalize_text)
│   ├── pipeline/       Etapa 3: PipelineRun, PipelineRunItem (corrida por lote)
│   ├── rag/            Etapa 4: IndexInfo, VectorPoint, VectorSearchHit, text_search.py (BM25),
│   │                   puertos EmbeddingProvider/VectorStore
│   ├── conversational/ Etapa 5: Intent, ConversationalVariable, GuardrailRule,
│   │                   ChannelingScheme, intent_matching.py, rule_evaluation.py
│   ├── quality/         Etapa 6: TestCase, EvaluationRun, EvaluationResultItem
│   ├── release/         Etapa 7: ReleaseStatus, GateResult, ReleaseChecklist, ReleaseRecord
│   └── plugins/         Etapa 8: PluginKind, Plugin, loader.py (carga dinámica vía importlib),
│                        CustomEvaluator (contrato para evaluadores personalizados)
├── application/    casos de uso (comandos/consultas) y fachadas, un
│                   subpaquete por contexto (projects/documents/metadata/
│                   ingestion/pipeline/rag/conversational/quality/release/plugins)
├── infrastructure/
│   ├── database/       SQLAlchemy, Alembic
│   ├── filesystem/      empaquetado .agentproj
│   ├── extraction/      Etapa 3: TxtExtractor, DocxExtractor, PdfTextExtractor, ImageTextExtractor
│   ├── embeddings/      Etapa 4: FastEmbedEmbeddingProvider
│   └── vectorstores/    Etapa 4: QdrantLocalVectorStore
├── workers/        administrador de trabajos en segundo plano
└── plugins/        reservado para Etapa 8

migrations/
├── global/         línea de migración de application.db
│                    (0001 índice de proyectos, 0002 complementos -- Etapa 8)
└── project/        línea de migración de cada project.db
                     (0001 núcleo, 0002 documentos + metadatos, 0003
                      ingesta, 0004 estado del índice RAG, 0005 pipeline
                      reproducible, 0006 diseño conversacional, 0007 calidad,
                      0008 liberación)

tests/
├── unit/           dominio y casos de uso, con dobles de prueba
├── integration/    export/import real, migraciones Alembic, extractores
│                   reales, ingesta de punta a punta sobre AppContext real
└── smoke/          arranque de la app, no-bloqueo, UI (auto-omitida)
```

Ver `ADR-001_Arquitectura_Modelo_Dominio.docx` (entregable previo) para
la justificación completa de cada decisión y la regla de dependencia
entre capas.

## Próximos pasos sugeridos

1. Ejecutar `pytest` también en Windows y macOS cuando haya equipo
   disponible — en Linux ya está validado de punta a punta: 186
   pruebas, **todas verdes, cero omitidas** (ver bitácora 2026-07-26),
   incluida la UI real (PySide6, no el stub) y los dos modelos de
   `fastembed` con red real.
2. ~~Validar visualmente en una laptop real las cuatro pestañas
   (Proyectos, Fuentes, Metadatos, Ingesta): registrar una fuente real
   (PDF/DOCX/TXT/Markdown), extraer su texto, configurar una política
   de fragmentación, indexarla y probar la búsqueda semántica sobre
   contenido real — confirmar que fragmentos, páginas/secciones y
   resultados de búsqueda coinciden con el documento real.~~ — hecho
   (ver `checklist_validacion_visual.md` y bitácora 2026-07-26): las
   4 pestañas quedaron validadas con una fuente real (plan de estudios
   en PDF), incluyendo los 26 hallazgos ya corregidos y re-confirmados,
   las dos variantes de la prueba de cancelación, la búsqueda con 2+
   fuentes registradas, y el hallazgo de granularidad de fragmento
   documentado como recomendación de uso.
3. ~~Si se procesan documentos grandes o lotes, considerar hacer
   cooperativa la cancelación~~ — hecho para `FragmentSource`/
   `ExtractSourceText` (ver bitácora 2026-07-25). Sigue pendiente para
   `IndexSource`/`RagService.search`, si algún día se indexan lotes lo
   bastante grandes como para justificarlo (ver limitaciones).
4. ~~Correr `python demo_plan_estudios.py` en la laptop real~~ — hecho:
   ya se ejecutó dos veces con `fastembed` real (ver bitácora). ~~Sigue
   pendiente que las dos pruebas omitidas de
   `tests/integration/test_fastembed_provider.py` se corran en esa
   misma laptop para confirmar que también pasan ahí~~ — hecho, pasan
   (ver bitácora 2026-07-26).
5. ~~Probar si un modelo de embeddings asimétrico mejora el caso
   encontrado con el plan de estudios~~ — hecho y confirmado con datos
   reales (ver bitácora 2026-07-26): `intfloat/multilingual-e5-large`
   sí mejora, de forma clara, tanto el caso que fallaba como el que ya
   funcionaba. ~~Queda una decisión de producto pendiente~~ — decidido
   (ver bitácora 2026-07-26): se mantiene `simetrico` (MiniLM) como
   perfil por defecto de todo proyecto nuevo; `asimetrico_e5_large`
   sigue disponible como opción configurable para quien lo necesite
   (ya implementado, sin cambios de código pendientes).
6. **Pospuesto a propósito** (decisión del usuario, 2026-07-27): el
   piloto UDL con datos reales (taxonomía programa/plantel/nivel/
   modalidad, documentos reales) no es un requisito del alcance
   inicial -- la herramienta debe quedar abierta a cualquier agente
   conversacional futuro, no solo al caso UDL. Se retoma como prueba de
   uso una vez que el motor genérico esté completo; mientras tanto el
   enfoque es cerrar las etapas del documento maestro que siguen sin
   empezar (ver punto 8).
7. ~~Ampliar la cobertura de Módulo 4 (OCR para PDF escaneado)~~ --
   hecho (ver bitácora 2026-07-27): dependencia opcional, no cambia el
   comportamiento de quien no la instale. ~~Tipos documentales de
   Módulo 5 (artículo, pregunta+respuesta, tabla)~~ -- hecho (ver
   bitácora 2026-07-27): tres `FragmentationStrategy` nuevas,
   configurables por `document_type_code` igual que las existentes.
   ~~`imagen_escaneada` como fuente independiente~~ -- hecho (ver
   bitácora 2026-07-27): `ImageTextExtractor` reutiliza el mismo
   `OcrEngine` de Módulo 4, sin necesitar PyMuPDF. Sigue pendiente el
   resto de la tabla de INVESTIGACION.odt sin estrategia dedicada
   (convocatoria, procedimiento, ficha de programa, formato, página
   web) cuando haya fuentes reales que lo justifiquen.
8. ~~Cuando haya más de un modelo de embeddings en uso real, construir
   el comparador "modelo A vs modelo B"~~ — hecho (ver bitácora
   2026-07-27): comparación en memoria sobre los fragmentos existentes,
   sin índice paralelo persistido. Sigue pendiente el versionado
   completo de `EmbeddingModelConfig`/`Index` de ADR-001 (sección 5,
   múltiples índices por proyecto con historial) — esta iteración solo
   guarda el estado vigente, no el historial, y el comparador evita
   deliberadamente ese alcance mayor.
9. ~~Ampliar el comparador de resultados de búsqueda en la interfaz
   (resaltado del texto coincidente, reranking)~~ -- resaltado hecho
   (ver bitácora 2026-07-27); reranking sigue pendiente, sin uso real
   todavía que lo justifique (mismo punto que el inciso "resto" de 10).
10. **Auditoría contra el documento maestro (2026-07-27): lo que falta
    para el ciclo completo de las 8 etapas, en orden de prioridad
    acordado con el usuario** (Ubuntu primero; Windows/macOS después;
    sin piloto UDL todavía, ver punto 6):
    1. ~~Corregir que `IndexSource`/`SemanticSearch` no respetaban
       `validation_status`/vigencia~~ -- hecho (ver bitácora
       2026-07-27): filtro opt-in `only_usable_sources` en
       `RagService.search`.
    2. ~~Etapa 4, resto: búsqueda textual, búsqueda híbrida,
       reranking~~ -- hecho (ver bitácora 2026-07-27): BM25 (textual) y
       Reciprocal Rank Fusion (híbrida + reranking, sin cross-encoder/
       LLM dedicado). Etapa 4 queda funcionalmente completa salvo
       métricas más finas (precisión/recall contra un banco de pruebas
       con respuestas esperadas), que en realidad pertenecen a Etapa 6
       (Calidad).
    3. ~~Etapa 3: "pipeline reproducible" como entidad propia (corrida
       por lote sobre todo el proyecto, con su reporte de errores/
       advertencias/tiempos, reanudación e incrementalidad real)~~ --
       hecho (ver bitácora 2026-07-27): `PipelineRun`/`RunPipeline`,
       incrementalidad por hash real de archivo, reanudación gratis por
       el mismo mecanismo, historial persistido, sección nueva en la UI.
       Queda pendiente (alcance acotado, no bloqueante): `document_type_code`
       por fuente en vez de uno solo por corrida.
    4. ~~Etapa 5 (diseño conversacional), sin empezar: intenciones,
       variables, preguntas aclaratorias, catálogo de reglas y
       guardrails, esquema de canalización, simulador~~ -- hecho (ver
       bitácora 2026-07-27): contexto `domain/conversational/` +
       `application/conversational/` completo (Intent, Conversational
       Variable, GuardrailRule, ChannelingScheme + SimulateConversation),
       persistido en SQLite (migración `0006`), con una pestaña nueva
       "Diseño conversacional" en la UI. Alcance acotado documentado
       más abajo (CRUD sin edición completa, canalización simulada, sin
       LLM/NLU real para emparejar intención).
    5. ~~Etapa 6 (calidad), sin empezar: banco de pruebas, centro de
       evaluación, regresión, comparación entre corridas, semáforos,
       bloqueos automáticos por hallazgos críticos~~ -- hecho (ver
       bitácora 2026-07-27): `TestCase`/`EvaluationRun`/`RunEvaluation`,
       semáforos verde/amarillo/rojo/gris, regresión contra la corrida
       anterior, `has_blocking_failures` como señal de bloqueo, sección
       nueva en la UI. Queda pendiente (alcance acotado, no bloqueante):
       comparación entre modelos/índices/reglas/prompts a nivel de todo
       el banco de pruebas.
    6. ~~Etapa 7 (documentación y liberación), sin empezar: compuertas
       de avance, dictamen, entregables formales~~ -- hecho (ver
       bitácora 2026-07-27): `domain/release/` + `application/release/`
       completo (`ReleaseChecklist`/`ReleaseRecord` + `EvaluateRelease
       Gates`/`RequestRelease`/`GenerateDeliverablesReport`), persistido
       en SQLite (migración `0008`), con una pestaña nueva "Liberación"
       en la UI. Alcance acotado documentado más abajo (sin compuerta de
       Etapa 1, sin bloqueo preventivo retrofitado en pantallas
       anteriores, entregables como dict inline en vez de paquete
       exportable de 8 archivos).
    7. ~~Etapa 8 (extensibilidad/plugins), sin empezar: SDK y contrato
       de extensión sobre la carpeta `plugins/` ya reservada~~ -- hecho
       (ver bitácora 2026-07-27): `domain/plugins/` + `application/
       plugins/` completo (`Plugin`/`PluginKind` + `RegisterPlugin`/
       `SetPluginEnabled`/`ValidatePlugin` + un cargador dinámico real
       vía `importlib` que valida contra `EmbeddingProvider`/
       `TextExtractor`/`CustomEvaluator` según el tipo), persistido en
       `application.db` (migración global `0002`, no en `project.db`:
       un complemento no pertenece a un proyecto), con una pestaña
       nueva "Complementos" en la UI. Con esto se cierra el ciclo
       completo de las 8 etapas del documento maestro. Alcance acotado
       documentado más abajo (el mecanismo de registro y carga está
       completo; los complementos reales de terceros y su invocación
       automática desde `RagService`/`RunEvaluation`/creación de
       proyectos quedan para cuando exista un caso real que lo
       justifique).
    8. Transversal: mecanismo de compuertas -- hecho parcialmente (ver
       punto 6): `ReleaseService.evaluate_gates` cubre las Etapas 2-6
       como verificación previa a una liberación. Sigue sin existir un
       bloqueo preventivo dentro de cada pantalla anterior (p. ej.
       impedir indexar sin metadatos aprobados en el momento mismo de
       indexar, no solo al liberar) -- alcance deliberadamente pospuesto,
       ver "Limitaciones conocidas".
# RAG-STUDIO
# RAG-STUDIO
