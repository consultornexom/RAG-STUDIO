def test_bootstrap_creates_expected_layout(app_context):
    context = app_context
    assert context.paths.application_db_path().exists()
    assert (context.paths.logs_dir() / "ragstudio.log").exists()
    assert context.paths.settings_dir().exists()
    assert context.paths.models_dir().exists()
    assert context.paths.plugins_dir().exists()


def test_bootstrap_allows_full_project_cycle(app_context):
    context = app_context
    project = context.project_service.create_project("Agente de humo")
    assert context.paths.project_db_path(project.id).exists()

    archived = context.project_service.archive_project(project.id)
    assert archived.is_archived()

    listado = context.project_service.list_projects()
    assert any(p.id == project.id for p in listado)


def test_log_file_does_not_contain_plaintext_secret(app_context, tmp_path):
    context = app_context
    context.logger.info("probando con password=NoDeberiaQuedarAsi")
    log_content = (context.paths.logs_dir() / "ragstudio.log").read_text(encoding="utf-8")
    assert "NoDeberiaQuedarAsi" not in log_content
    assert "[REDACTADO]" in log_content


def test_bootstrap_wires_a_working_diagnostics_exporter(app_context, tmp_path):
    context = app_context
    destination = tmp_path / "diagnostico.zip"
    result_path = context.diagnostics.export_diagnostics_package(str(destination))
    assert destination.exists()
    assert result_path == str(destination)
