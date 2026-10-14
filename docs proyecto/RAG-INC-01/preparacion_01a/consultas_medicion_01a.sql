-- ============================================================================
-- RAG-INC-01, hito 01a — Consultas de medición (SOLO LECTURA)
-- ============================================================================
-- Estado: PREPARADAS, NO EJECUTADAS. Se ejecutan únicamente tras el inicio
-- formal de 01a (PASS de la importación de humo del Runtime), sobre COPIAS
-- respaldadas de project.db y abiertas en modo solo lectura:
--
--   python3 -c "import sqlite3; c = sqlite3.connect('file:COPIA/project.db?mode=ro&immutable=1', uri=True); ..."
--
-- `immutable=1` es obligatorio, pero SOLO sobre una copia inmóvil y
-- consistente, nunca sobre una base viva: indica a SQLite que el archivo no
-- cambiará y puede hacer que ignore el WAL. La copia se obtiene según
-- Congelamiento_Corpus_UDL.md, sección 2.1. Con solo `mode=ro`, SQLite crea o
-- actualiza los archivos auxiliares `-shm`/`-wal` aunque no escriba en
-- `project.db` (observado el 2026-09-24 en el candidato A).
--
-- Ninguna consulta modifica datos. Esquema de referencia: migración 0020
-- (tablas `source` y `chunk`, infrastructure/database/models.py).
-- ============================================================================

-- 0. Versión de esquema de la copia: debe ser '0020' antes de aplicar 0021.
SELECT version_num FROM alembic_version;

-- ----------------------------------------------------------------------------
-- INC01-R6 — chunks no imagen con texto vacío (condiciona el inicio de 01b)
-- ----------------------------------------------------------------------------
-- 1a. Recuento que viola chunk.schema.json (texto de longitud 0).
SELECT COUNT(*) AS chunks_no_imagen_texto_vacio
FROM chunk
WHERE chunk_type <> 'imagen' AND length(text) = 0;

-- 1b. Detalle para el informe de la puerta de 01a.
SELECT c.id AS chunk_id, c.source_id, s.title, c.chunk_index, c.chunk_type
FROM chunk c LEFT JOIN source s ON s.id = c.source_id
WHERE c.chunk_type <> 'imagen' AND length(c.text) = 0
ORDER BY s.title, c.chunk_index;

-- 1c. Informativo: texto solo con espacios. El schema lo admite (minLength 1),
--     pero se reporta por calidad y no bloquea.
SELECT COUNT(*) AS chunks_no_imagen_solo_espacios
FROM chunk
WHERE chunk_type <> 'imagen' AND length(text) > 0
  AND length(trim(text, ' ' || char(9) || char(10) || char(13))) = 0;

-- ----------------------------------------------------------------------------
-- INC01-R1 — fuentes sin content_hash (version_key depende de updated_at)
-- ----------------------------------------------------------------------------
SELECT COUNT(*) AS fuentes_sin_content_hash FROM source WHERE content_hash IS NULL;

-- ----------------------------------------------------------------------------
-- Cadenas de supersesión (entrada del relleno de lineage_id)
-- ----------------------------------------------------------------------------
-- 2a. Totales: fuentes, raíces (no superseden a nadie) y fuentes que superseden.
SELECT COUNT(*) AS fuentes,
       SUM(supersedes_source_id IS NULL) AS raices,
       SUM(supersedes_source_id IS NOT NULL) AS con_supersesion
FROM source;

-- 2b. Referencias rotas: supersedes_source_id apunta a un id inexistente.
--     En 0021 cada una se tratará como raíz de su propia cadena y quedará
--     registrada en el log de la migración.
SELECT s.id, s.title, s.supersedes_source_id
FROM source s
WHERE s.supersedes_source_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM source p WHERE p.id = s.supersedes_source_id);

-- 2c. Ramificaciones: una fuente superseded por más de una fuente. Todas las
--     sucesoras heredarían el mismo lineage_id. Se reporta en la puerta de 01a
--     porque produce dos versiones "vigentes" del mismo logical_id.
SELECT supersedes_source_id AS fuente_superseded, COUNT(*) AS sucesoras
FROM source
WHERE supersedes_source_id IS NOT NULL
GROUP BY supersedes_source_id
HAVING COUNT(*) > 1;

-- 2d. Ciclos (incluidos los auto-ciclos). Si aparece alguno, 0021 debe abortar.
WITH RECURSIVE walk(start_id, next_id, depth, path) AS (
    SELECT id, supersedes_source_id, 1, '|' || id || '|'
    FROM source
    WHERE supersedes_source_id IS NOT NULL
    UNION ALL
    SELECT w.start_id, s.supersedes_source_id, w.depth + 1, w.path || s.id || '|'
    FROM walk w
    JOIN source s ON s.id = w.next_id
    WHERE s.supersedes_source_id IS NOT NULL
      AND instr(w.path, '|' || s.id || '|') = 0
      AND w.depth < 10000
)
SELECT DISTINCT start_id
FROM walk
WHERE next_id IS NOT NULL AND instr(path, '|' || next_id || '|') > 0;

-- 2e. Profundidad máxima de cadena (dimensiona las pruebas).
WITH RECURSIVE chain(id, depth, path) AS (
    SELECT id, 1, '|' || id || '|' FROM source WHERE supersedes_source_id IS NULL
    UNION ALL
    SELECT s.id, c.depth + 1, c.path || s.id || '|'
    FROM chain c JOIN source s ON s.supersedes_source_id = c.id
    WHERE instr(c.path, '|' || s.id || '|') = 0 AND c.depth < 10000
)
SELECT MAX(depth) AS profundidad_maxima FROM chain;

-- ----------------------------------------------------------------------------
-- Linajes no lineales (decisión de NEXOM del 2026-09-24). Correr solo si 2d
-- no reporta ciclos: 2h recorre hacia arriba y un ciclo agotaría el límite de
-- profundidad.
-- ----------------------------------------------------------------------------
-- 2f. Sucesora con el MISMO content_hash que la fuente que supersede.
--     RegisterSource lo permite (register_source.py: solo lanza
--     DuplicateSourceError si existing.id != supersedes_source_id). Como
--     comparten lineage_id y version_key, producirían el MISMO source.id
--     portable. Política aprobada por NEXOM (2026-09-24): la exportación
--     rechaza siempre las colisiones (PortableIdentityCollisionError). Cada
--     fila de esta consulta bloquea 01b hasta que se corrijan los datos.
SELECT s.id AS sucesora, p.id AS predecesora, s.content_hash,
       s.title AS titulo_sucesora, p.title AS titulo_predecesora,
       s.access_level AS acceso_sucesora, p.access_level AS acceso_predecesora
FROM source s JOIN source p ON p.id = s.supersedes_source_id
WHERE s.content_hash IS NOT NULL AND s.content_hash = p.content_hash;

-- 2g. Hermanas (misma predecesora) con igual content_hash, o ambas sin
--     content_hash, título y tipo iguales: candidatas a colisión de version_key.
SELECT a.supersedes_source_id AS predecesora, a.id AS hermana_1, b.id AS hermana_2,
       a.content_hash, a.title, a.source_type
FROM source a JOIN source b
  ON a.supersedes_source_id = b.supersedes_source_id AND a.id < b.id
WHERE a.supersedes_source_id IS NOT NULL
  AND (a.content_hash = b.content_hash
       OR (a.content_hash IS NULL AND b.content_hash IS NULL
           AND a.title = b.title AND a.source_type = b.source_type));

-- 2h. Familias (misma raíz) con más de una cabeza, es decir, fuentes que
--     nadie supersede. Se reportan como advertencia de calidad; no se
--     elige ninguna como "actual".
WITH RECURSIVE up(id, cur, depth) AS (
    SELECT id, id, 0 FROM source
    UNION ALL
    SELECT u.id, s.supersedes_source_id, u.depth + 1
    FROM up u JOIN source s ON s.id = u.cur
    WHERE s.supersedes_source_id IS NOT NULL
      AND EXISTS (SELECT 1 FROM source p WHERE p.id = s.supersedes_source_id)
      AND u.depth < 10000
),
root AS (
    SELECT u.id, u.cur AS root_id FROM up u
    WHERE u.depth = (SELECT MAX(depth) FROM up u2 WHERE u2.id = u.id)
),
heads AS (
    SELECT s.id, s.validation_status FROM source s
    WHERE NOT EXISTS (SELECT 1 FROM source c WHERE c.supersedes_source_id = s.id)
)
SELECT r.root_id AS raiz, COUNT(*) AS cabezas,
       SUM(h.validation_status = 'validado') AS cabezas_validadas
FROM root r JOIN heads h ON h.id = r.id
GROUP BY r.root_id
HAVING COUNT(*) > 1;
