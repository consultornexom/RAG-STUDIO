from datetime import date

import pytest

from domain.documents.entities import (
    TERMINAL_VALIDATION_STATUSES, AccessLevel, Source, SourceType, SourceValidationStatus,
    is_within_access_level,
)
from domain.documents.exceptions import InvalidValidationTransitionError


def _source(**overrides) -> Source:
    defaults = dict(project_id="p1", title="Reglamento", source_type=SourceType.PDF)
    defaults.update(overrides)
    return Source(**defaults)


def test_new_source_starts_in_borrador():
    s = _source()
    assert s.validation_status == SourceValidationStatus.BORRADOR
    assert not s.is_usable_for_responses()


def test_title_cannot_be_empty():
    with pytest.raises(ValueError):
        _source(title="   ")


def test_full_validation_path_makes_source_usable():
    s = _source()
    s = s.transition_validation_to(SourceValidationStatus.EN_REVISION)
    s = s.transition_validation_to(SourceValidationStatus.VALIDADO)
    assert s.is_usable_for_responses()


def test_cannot_skip_en_revision():
    s = _source()
    with pytest.raises(InvalidValidationTransitionError):
        s.transition_validation_to(SourceValidationStatus.VALIDADO)


def test_validated_but_expired_is_not_usable():
    s = _source(
        valid_from=date(2020, 1, 1), valid_to=date(2021, 1, 1),
        validation_status=SourceValidationStatus.VALIDADO,
    )
    assert not s.is_usable_for_responses(as_of=date(2026, 7, 24))


def test_current_but_not_validated_is_not_usable():
    s = _source(validation_status=SourceValidationStatus.EN_REVISION)
    assert s.is_current()
    assert not s.is_usable_for_responses()


def test_sustituido_and_rechazado_are_terminal():
    validado = _source().transition_validation_to(SourceValidationStatus.EN_REVISION).transition_validation_to(
        SourceValidationStatus.VALIDADO
    )
    sustituido = validado.transition_validation_to(SourceValidationStatus.SUSTITUIDO)
    with pytest.raises(InvalidValidationTransitionError):
        sustituido.transition_validation_to(SourceValidationStatus.VALIDADO)

    rechazado = _source().transition_validation_to(SourceValidationStatus.RECHAZADO)
    with pytest.raises(InvalidValidationTransitionError):
        rechazado.transition_validation_to(SourceValidationStatus.BORRADOR)


def test_terminal_validation_statuses_matches_states_with_no_allowed_targets():
    # Ronda 5 (hallazgo real de usuario): la UI usa esta constante para
    # advertir antes de aplicar una transición sin retorno -- si algún
    # día se agregara un estado terminal nuevo (o se le abriera una
    # salida a uno de estos), este test debe fallar para forzar a
    # revisar también el aviso de ui.sources.panel.
    assert TERMINAL_VALIDATION_STATUSES == {
        SourceValidationStatus.SUSTITUIDO, SourceValidationStatus.VENCIDO, SourceValidationStatus.RECHAZADO,
    }
    for status in TERMINAL_VALIDATION_STATUSES:
        source = _source(validation_status=status)
        for target in SourceValidationStatus:
            with pytest.raises(InvalidValidationTransitionError):
                source.transition_validation_to(target)


def test_access_level_default_is_interno():
    assert _source().access_level == AccessLevel.INTERNO


# ---------- is_within_access_level (Pista B.3 del ADR-003) ----------

def test_is_within_access_level_true_when_level_is_less_or_equally_restrictive():
    assert is_within_access_level(AccessLevel.PUBLICO, AccessLevel.INTERNO)
    assert is_within_access_level(AccessLevel.INTERNO, AccessLevel.INTERNO)


def test_is_within_access_level_false_when_level_exceeds_the_ceiling():
    assert not is_within_access_level(AccessLevel.CONFIDENCIAL, AccessLevel.INTERNO)
    assert not is_within_access_level(AccessLevel.RESTRINGIDO, AccessLevel.PUBLICO)


def test_is_within_access_level_restringido_ceiling_lets_everything_through():
    # RESTRINGIDO es, a propósito, el techo MENOS restrictivo (rango
    # más alto) -- "restringido" describe al canal, no a la fuente: un
    # token sin ninguna restricción declarada usa este techo (ver
    # domain.runtime.entities.WidgetToken.max_access_level) y por eso
    # debe dejar pasar cualquier nivel de fuente, incluido el propio
    # RESTRINGIDO.
    for level in AccessLevel:
        assert is_within_access_level(level, AccessLevel.RESTRINGIDO)


def test_is_within_access_level_publico_ceiling_only_lets_publico_through():
    assert is_within_access_level(AccessLevel.PUBLICO, AccessLevel.PUBLICO)
    for level in (AccessLevel.INTERNO, AccessLevel.CONFIDENCIAL, AccessLevel.RESTRINGIDO):
        assert not is_within_access_level(level, AccessLevel.PUBLICO)


def test_transition_accepts_plain_string_target():
    # La UI (combo box / QInputDialog) entrega el destino como string
    # plano, no como SourceValidationStatus; debe funcionar igual que
    # con el enum, incluyendo el mensaje de error si la transición no
    # está permitida (antes fallaba con AttributeError: 'str' object
    # has no attribute 'value' en vez de InvalidValidationTransitionError).
    s = _source()
    s = s.transition_validation_to("en_revision")
    s = s.transition_validation_to("validado")
    assert s.validation_status == SourceValidationStatus.VALIDADO

    with pytest.raises(InvalidValidationTransitionError) as excinfo:
        s.transition_validation_to("en_revision")
    assert excinfo.value.target == "en_revision"


# ---------- document_type_code (punto 10 de Validacion_observaciones_RAG_STUDIO.md) ----------

def test_document_type_code_defaults_to_default():
    assert _source().document_type_code == "default"


def test_with_updated_details_can_change_document_type_code():
    s = _source()
    updated = s.with_updated_details(
        title=s.title, owner_area=None, access_level=s.access_level,
        location=s.location, source_type=s.source_type, document_type_code="contactos",
    )
    assert updated.document_type_code == "contactos"


def test_with_updated_details_defaults_document_type_code_when_not_passed():
    # with_updated_details siempre manda un valor definitivo (mismo
    # criterio que valid_from/valid_to/source_authority) -- si quien
    # llama no lo pasa, se usa "default", no el valor que ya tenía la
    # fuente (evita que un olvido en la UI deje un valor "pegado" sin
    # que el usuario lo haya confirmado).
    s = _source(document_type_code="contactos")
    updated = s.with_updated_details(
        title=s.title, owner_area=None, access_level=s.access_level,
        location=s.location, source_type=s.source_type,
    )
    assert updated.document_type_code == "default"


# ---------- language (análisis de brechas dominio/UI, ver nota de
# "valor múltiple" del Manual del Usuario, sección 6.1) ----------

def test_language_defaults_to_es():
    assert _source().language == "es"


def test_with_updated_details_can_change_language():
    s = _source()
    updated = s.with_updated_details(
        title=s.title, owner_area=None, access_level=s.access_level,
        location=s.location, source_type=s.source_type, language="en",
    )
    assert updated.language == "en"


def test_with_updated_details_defaults_language_when_not_passed():
    # Mismo criterio que document_type_code (ver test arriba): un
    # olvido en la UI no debe dejar "pegado" el idioma anterior sin
    # que el usuario lo haya confirmado explícitamente en el diálogo.
    s = _source(language="en")
    updated = s.with_updated_details(
        title=s.title, owner_area=None, access_level=s.access_level,
        location=s.location, source_type=s.source_type,
    )
    assert updated.language == "es"
