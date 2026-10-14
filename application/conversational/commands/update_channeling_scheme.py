"""Caso de uso: editar un esquema de canalización (Ronda 4, punto 1 de
Validacion_observaciones_RAG_STUDIO.md).

Antes de esto, Canalización era el único de los cuatro catálogos de
Conversacional que quedó sin su edición básica al corregir el mismo
problema en intenciones, variables y reglas (Ronda 3, punto 13): solo
se podía Crear y Activar/Desactivar. Aquí se permite editar todos los
atributos descriptivos -- a diferencia de intenciones/variables/reglas
(donde solo se tocó nombre/descripción para no alterar lógica de
negocio), un ChannelingScheme es en sí mismo una ficha de
configuración completa (motivo, condición, área destino, datos
requeridos/permitidos/prohibidos, plantilla, medio, mensaje...), no
tiene una parte "lógica" separada de una parte "descriptiva" como sí
la tiene una GuardrailRule (condiciones+acción) -- por eso aquí la
edición cubre la ficha completa.

`code` no es editable: es la clave que usa
`Intent.fallback_channeling_code` para referenciar un esquema --
cambiarlo silenciosamente rompería esas referencias, mismo criterio ya
aplicado a `FieldDefinition.field_id` y `ConversationalVariable.code`."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from domain.conversational.entities import ChannelingMedium, ChannelingScheme
from domain.conversational.exceptions import ChannelingSchemeNotFoundError
from domain.conversational.ports import ChannelingSchemeRepository


class UpdateChannelingScheme:
    def __init__(self, repository: ChannelingSchemeRepository):
        self._repository = repository

    def execute(
        self,
        project_id: str,
        scheme_id: str,
        name: str,
        reason: Optional[str] = None,
        condition: Optional[str] = None,
        target_area: Optional[str] = None,
        priority: Optional[int] = None,
        required_data: Optional[list[str]] = None,
        allowed_data: Optional[list[str]] = None,
        forbidden_data: Optional[list[str]] = None,
        summary_template: Optional[str] = None,
        medium: Optional[ChannelingMedium] = None,
        user_message: Optional[str] = None,
        alternative_action: Optional[str] = None,
    ) -> ChannelingScheme:
        scheme = self._repository.get(project_id, scheme_id)
        if scheme is None:
            raise ChannelingSchemeNotFoundError(project_id, scheme_id)

        update: dict = {"name": name, "updated_at": datetime.now(timezone.utc)}
        if reason is not None:
            update["reason"] = reason
        if condition is not None:
            update["condition"] = condition
        if target_area is not None:
            update["target_area"] = target_area
        if priority is not None:
            update["priority"] = priority
        if required_data is not None:
            update["required_data"] = list(required_data)
        if allowed_data is not None:
            update["allowed_data"] = list(allowed_data)
        if forbidden_data is not None:
            update["forbidden_data"] = list(forbidden_data)
        if summary_template is not None:
            update["summary_template"] = summary_template
        if medium is not None:
            update["medium"] = medium
        if user_message is not None:
            update["user_message"] = user_message
        if alternative_action is not None:
            update["alternative_action"] = alternative_action

        # Ronda 87 (2026-10-02, hallazgo real de usuario: "Al intentar
        # modificar una canalización no permite guardarlo" -- "'str'
        # object has no attribute 'value'"): antes se usaba
        # scheme.model_copy(update=update), que NUNCA valida ni convierte
        # tipos. El diálogo de edición manda `medium` como texto
        # ("correo", de QComboBox.currentText()), así que el esquema
        # quedaba con un str donde se esperaba ChannelingMedium y
        # SqlAlchemyChannelingSchemeRepository.save() fallaba en
        # `scheme.medium.value`. Toda edición desde la interfaz fallaba,
        # cambiara o no el medio. Ahora se reconstruye el modelo completo
        # (mismo criterio que UpdateTestCase), de modo que cualquier
        # campo se valida igual que al crear: "correo" -> ChannelingMedium,
        # y un medio inexistente se rechaza con un error claro en vez de
        # guardarse.
        data = scheme.model_dump()
        data.update(update)
        updated = ChannelingScheme(**data)
        self._repository.save(updated)
        return updated
