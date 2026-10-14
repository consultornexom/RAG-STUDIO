from sqlalchemy import inspect, create_engine

from infrastructure.database import migrations as mig
from infrastructure.filesystem.paths import InstallationPaths


def test_global_migration_upgrade_and_downgrade(tmp_path):
    db_path = tmp_path / "application.db"
    mig.upgrade_global(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    assert "project_index" in tables

    mig.downgrade_global(db_path, "base")
    tables_after = inspect(engine).get_table_names()
    assert "project_index" not in tables_after


def test_project_migration_upgrade_and_downgrade(tmp_path):
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    assert {"project", "configuration"}.issubset(tables)

    mig.downgrade_project(db_path, "base")
    tables_after = inspect(engine).get_table_names()
    assert "project" not in tables_after
    assert "configuration" not in tables_after


def test_global_and_project_schemas_are_independent(tmp_path):
    """Ninguna de las dos líneas de migración debe crear tablas de la otra."""
    global_db = tmp_path / "application.db"
    project_db = tmp_path / "project.db"
    mig.upgrade_global(global_db)
    mig.upgrade_project(project_db)

    global_tables = inspect(create_engine(f"sqlite:///{global_db}")).get_table_names()
    project_tables = inspect(create_engine(f"sqlite:///{project_db}")).get_table_names()

    assert "project" not in global_tables
    assert "project_index" not in project_tables


def test_project_migration_0002_adds_documents_and_metadata_tables(tmp_path):
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)  # aplica 0001 y 0002 (head)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    for expected in ("source", "metadata_schema", "field_definition", "catalog", "catalog_entry",
                     "source_metadata_value"):
        assert expected in tables

    mig.downgrade_project(db_path, "0001")
    tables_after = inspect(engine).get_table_names()
    for removed in ("source", "metadata_schema", "field_definition", "catalog", "catalog_entry",
                     "source_metadata_value"):
        assert removed not in tables_after
    # 0001 debe seguir intacto
    assert "project" in tables_after
    assert "configuration" in tables_after


def test_project_migration_0003_adds_ingestion_tables(tmp_path):
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)  # aplica 0001, 0002 y 0003 (head)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    for expected in ("extraction_record", "chunk", "fragmentation_policy"):
        assert expected in tables

    mig.downgrade_project(db_path, "0002")
    tables_after = inspect(engine).get_table_names()
    for removed in ("extraction_record", "chunk", "fragmentation_policy"):
        assert removed not in tables_after
    # 0001 y 0002 deben seguir intactos
    assert "project" in tables_after
    assert "source" in tables_after
    assert "metadata_schema" in tables_after


def test_project_migration_0004_adds_index_info_table(tmp_path):
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)  # aplica 0001-0004 (head)

    engine = create_engine(f"sqlite:///{db_path}")
    tables = inspect(engine).get_table_names()
    assert "index_info" in tables

    mig.downgrade_project(db_path, "0003")
    tables_after = inspect(engine).get_table_names()
    assert "index_info" not in tables_after
    # 0001-0003 deben seguir intactos
    assert "project" in tables_after
    assert "source" in tables_after
    assert "chunk" in tables_after


def test_ensure_project_db_upgrades_a_project_created_before_a_newer_migration(tmp_path):
    """Reproduce el bug real reportado por el usuario: un proyecto cuyo
    project.db fue creado (y quedó en disco) cuando el código todavía
    no conocía la migración 0004_index_info -- es decir, en su momento
    "no hacía falta" upgrade_project() porque el archivo ya existía --
    debe recibir igualmente esa migración la primera vez que se abre
    con el código actual, vía ensure_project_db().

    Antes del fix, cada repositorio solo llamaba a upgrade_project()
    cuando `db_path.exists()` era False, así que un project.db que ya
    existía en la revisión 0003 se quedaba atascado ahí para siempre
    y `SqlAlchemyIndexInfoRepository.get()` fallaba con
    `sqlite3.OperationalError: no such table: index_info`.
    """
    paths = InstallationPaths(tmp_path)
    project_id = "proyecto-viejo"
    paths.ensure_project_layout(project_id)
    db_path = paths.project_db_path(project_id)

    # Simula el estado "viejo": el project.db ya existe, pero solo
    # tiene aplicadas las migraciones 0001-0003 (pre-Etapa 4).
    mig.upgrade_project(db_path, "0003")
    tables_before = inspect(create_engine(f"sqlite:///{db_path}")).get_table_names()
    assert "index_info" not in tables_before

    # El código actual (ya con 0004 en el repo) abre ese mismo
    # project.db -- no lo crea de nuevo, el archivo ya existía.
    returned_path = mig.ensure_project_db(paths, project_id)
    assert returned_path == db_path

    tables_after = inspect(create_engine(f"sqlite:///{db_path}")).get_table_names()
    assert "index_info" in tables_after
    # Las tablas viejas no se pierden en el camino.
    assert "project" in tables_after
    assert "chunk" in tables_after


def test_ensure_project_db_only_runs_the_real_upgrade_once_per_process(tmp_path, monkeypatch):
    # Auditoría Ronda 46, hallazgo #148 (costo de Alembic por llamada
    # en importaciones de lote grandes), corregido en la Ronda 51:
    # cada repositorio llama a ensure_project_db() en cada método, no
    # solo al abrir el proyecto -- sin la caché de esta ronda, importar
    # muchas fuentes corría upgrade_project() (bajo el lock global de
    # Alembic) una vez por cada llamada, aunque el esquema ya estuviera
    # al día desde la primera.
    paths = InstallationPaths(tmp_path)
    project_id = "proyecto-cacheado"

    real_upgrade_project = mig.upgrade_project
    calls = []

    def spy_upgrade_project(db_path, revision="head"):
        calls.append(db_path)
        return real_upgrade_project(db_path, revision)

    monkeypatch.setattr(mig, "upgrade_project", spy_upgrade_project)

    first = mig.ensure_project_db(paths, project_id)
    second = mig.ensure_project_db(paths, project_id)
    third = mig.ensure_project_db(paths, project_id)

    assert first == second == third
    assert len(calls) == 1  # solo la primera llamada corrió el upgrade real

    mig.forget_ensured_project_db(first)
    mig.ensure_project_db(paths, project_id)
    assert len(calls) == 2  # tras olvidarla, la siguiente llamada vuelve a verificar de verdad


def test_ensure_project_db_re_verifies_when_the_code_gains_a_new_migration_mid_process(tmp_path, monkeypatch):
    """Ronda 54 -- reproduce el fallo real reportado por el consultor:
    RAG STUDIO es una aplicación de escritorio de proceso largo, no un
    servidor que se reinicia con cada despliegue. La versión de la
    caché de la Ronda 51 (indexada solo por ruta) nunca detectaba que
    se hubiera agregado una migración nueva al código en disco MIENTRAS
    el proceso seguía corriendo -- el project.db real de "AGENTE UDL"
    quedó confirmado en la revisión 0016 (de una apertura anterior del
    mismo proceso) y nunca recibió las migraciones 0017-0019, aunque el
    código ya las conocía, produciendo
    `sqlite3.OperationalError: no such column: project.quality_regression_threshold`
    sin que nadie llamara a forget_ensured_project_db() -- nadie sabía
    que había que hacerlo. Esta prueba simula exactamente ese
    escenario: la revisión head "cambia" entre dos llamadas (como
    pasaría de verdad si se agrega un archivo de migración nuevo al
    código en disco) sin ningún forget_ensured_project_db() explícito,
    y confirma que la segunda llamada sí vuelve a verificar de verdad."""
    paths = InstallationPaths(tmp_path)
    project_id = "proyecto-cacheado-2"

    real_upgrade_project = mig.upgrade_project
    calls = []

    def spy_upgrade_project(db_path, revision="head"):
        calls.append(db_path)
        return real_upgrade_project(db_path, revision)

    monkeypatch.setattr(mig, "upgrade_project", spy_upgrade_project)

    heads = iter(["0016", "0016", "0019"])
    monkeypatch.setattr(mig, "_project_migrations_head", lambda: next(heads))

    mig.ensure_project_db(paths, project_id)
    mig.ensure_project_db(paths, project_id)
    assert len(calls) == 1  # mismo head ("0016") las dos primeras veces -- sigue cacheado

    mig.ensure_project_db(paths, project_id)
    assert len(calls) == 2  # el head "cambió" a "0019" -- se vuelve a verificar de verdad,
    # sin que nadie haya llamado a forget_ensured_project_db()


def test_ensure_project_db_cache_is_scoped_by_resolved_path(tmp_path, monkeypatch):
    # Dos proyectos distintos (rutas distintas) no deben compartir la
    # entrada de la caché -- cada archivo real se verifica al menos
    # una vez, sin importar cuántos otros ya se verificaron antes.
    paths = InstallationPaths(tmp_path)
    real_upgrade_project = mig.upgrade_project
    calls = []
    monkeypatch.setattr(
        mig, "upgrade_project",
        lambda db_path, revision="head": (calls.append(db_path), real_upgrade_project(db_path, revision)),
    )

    mig.ensure_project_db(paths, "proyecto-a")
    mig.ensure_project_db(paths, "proyecto-b")
    mig.ensure_project_db(paths, "proyecto-a")  # ya cacheado, no debe volver a correr

    assert len(calls) == 2


def test_project_migration_0014_adds_chunk_canonical_columns(tmp_path):
    # Pista B.1 del ADR-003 -- migración puramente aditiva sobre una
    # tabla (chunk) que ya existe desde la migración 0003.
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)  # aplica 0001-0014 (head)

    engine = create_engine(f"sqlite:///{db_path}")
    columns = {c["name"] for c in inspect(engine).get_columns("chunk")}
    assert {"parent_chunk_id", "structured_content"}.issubset(columns)

    mig.downgrade_project(db_path, "0013")
    columns_after = {c["name"] for c in inspect(engine).get_columns("chunk")}
    assert "parent_chunk_id" not in columns_after
    assert "structured_content" not in columns_after
    # El resto de la tabla chunk (y del esquema) debe seguir intacto.
    assert "text" in columns_after
    assert "chunk" in inspect(engine).get_table_names()


def test_project_migration_0015_adds_extraction_structured_blocks_columns(tmp_path):
    # Pista B.2 del ADR-003 -- migración puramente aditiva sobre dos
    # tablas (extraction_record, extraction_record_history) que ya
    # existen desde la migración 0003.
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)  # aplica 0001-0015 (head)

    engine = create_engine(f"sqlite:///{db_path}")
    for table in ("extraction_record", "extraction_record_history"):
        columns = {c["name"] for c in inspect(engine).get_columns(table)}
        assert "structured_blocks" in columns

    mig.downgrade_project(db_path, "0014")
    for table in ("extraction_record", "extraction_record_history"):
        columns_after = {c["name"] for c in inspect(engine).get_columns(table)}
        assert "structured_blocks" not in columns_after
        assert "text" in columns_after
    assert "extraction_record" in inspect(engine).get_table_names()


def test_project_migration_0016_adds_intent_resolution_mode_and_variable_structured_column(tmp_path):
    # Pista B.4 del ADR-003 -- migración aditiva sobre `intent` (nueva
    # columna resolution_mode, NOT NULL con server_default 'semantico'
    # para que toda intención existente conserve el comportamiento de
    # siempre) y `conversational_variable` (structured_column,
    # NULLABLE, mismo criterio que metadata_field_id).
    db_path = tmp_path / "project.db"
    mig.upgrade_project(db_path)  # aplica 0001-0016 (head)

    engine = create_engine(f"sqlite:///{db_path}")
    intent_columns = {c["name"] for c in inspect(engine).get_columns("intent")}
    assert "resolution_mode" in intent_columns
    variable_columns = {c["name"] for c in inspect(engine).get_columns("conversational_variable")}
    assert "structured_column" in variable_columns

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO intent (id, project_id, name, description, positive_examples, negative_examples, "
            "priority, risk_level, required_variables, optional_variables, clarifying_questions, "
            "response_rule, fallback_channeling_code, active, created_at, updated_at) VALUES "
            "('i1', 'p1', 'Intención previa a B.4', '', '[]', '[]', 0, 'bajo', '[]', '[]', '{}', '', "
            "NULL, 1, '2026-01-01', '2026-01-01')"
        )
        row = conn.exec_driver_sql("SELECT resolution_mode FROM intent WHERE id = 'i1'").fetchone()
    assert row[0] == "semantico"  # backfill vía server_default -- ninguna intención existente cambia de vía

    mig.downgrade_project(db_path, "0015")
    intent_columns_after = {c["name"] for c in inspect(engine).get_columns("intent")}
    assert "resolution_mode" not in intent_columns_after
    variable_columns_after = {c["name"] for c in inspect(engine).get_columns("conversational_variable")}
    assert "structured_column" not in variable_columns_after
    assert "intent" in inspect(engine).get_table_names()


def test_index_info_repository_get_does_not_fail_on_a_pre_etapa4_project(tmp_path):
    """Mismo escenario que la prueba anterior, pero ejercitando
    directamente SqlAlchemyIndexInfoRepository.get() -- la llamada
    exacta que fallaba en la GUI real del usuario (ui/ingestion/panel.py
    -> set_active_project -> _refresh_index_info ->
    rag_service.get_index_info -> SqlAlchemyIndexInfoRepository.get)
    con `sqlite3.OperationalError: no such table: index_info` al
    seleccionar un proyecto creado antes de la Etapa 4."""
    from infrastructure.database.rag_repositories import SqlAlchemyIndexInfoRepository

    paths = InstallationPaths(tmp_path)
    project_id = "proyecto-viejo-2"
    paths.ensure_project_layout(project_id)
    mig.upgrade_project(paths.project_db_path(project_id), "0003")

    repo = SqlAlchemyIndexInfoRepository(paths)
    # Antes del fix, esta línea lanzaba OperationalError. Ahora debe
    # simplemente devolver None (todavía no se ha indexado nada), tras
    # aplicar 0004 de forma transparente.
    assert repo.get(project_id) is None
