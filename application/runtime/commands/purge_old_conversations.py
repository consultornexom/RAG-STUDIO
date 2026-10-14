"""Caso de uso: purgar la bitácora de conversaciones reales más
antigua que una ventana de retención (Ronda 12, ver
Validacion_observaciones_RAG_STUDIO.md -- brecha de retención de
datos identificada en el análisis de "grado profesional" del
entregable al cliente).

`runtime.db` (ConversationLogRepository) crecía sin ningún mecanismo
de purga: si un proyecto maneja datos personales de quien le escribe
al agente (nombres, matrículas, lo que sea que el visitante escriba),
guardarlos indefinidamente es un riesgo de cumplimiento real, no solo
un detalle de almacenamiento. Este comando NO decide una política por
sí solo (cuántos días retener es una decisión del operador/cliente,
no de RAG STUDIO) -- solo ejecuta la purga dado un número de días,
para que quien opere el runtime pueda automatizarla (cron, tarea
programada) con la política que corresponda.

Cifrado en reposo de `runtime.db` queda deliberadamente fuera de este
comando: es responsabilidad de la capa de hospedaje (volumen/disco
cifrado), el mismo criterio que ya aplica a TLS -- ver
GUIA_DESPLIEGUE.md, sección "Hospedaje" del informe de entrega."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from domain.runtime.ports import ConversationLogRepository


class InvalidRetentionWindowError(Exception):
    def __init__(self, retention_days: int):
        super().__init__(f"retention_days debe ser mayor que cero (recibido: {retention_days}).")
        self.retention_days = retention_days


class PurgeOldConversations:
    def __init__(self, log_repository: ConversationLogRepository):
        self._log_repository = log_repository

    @staticmethod
    def _cutoff(retention_days: int) -> datetime:
        if retention_days <= 0:
            raise InvalidRetentionWindowError(retention_days)
        return datetime.now(timezone.utc) - timedelta(days=retention_days)

    def count_eligible(self, retention_days: int) -> int:
        """Cuántas conversaciones se borrarían con esta ventana de
        retención, sin borrar nada todavía -- para un "dry run" antes
        de ejecutar la purga de verdad."""
        return self._log_repository.count_older_than(self._cutoff(retention_days))

    def execute(self, retention_days: int) -> int:
        """Ejecuta la purga y devuelve cuántas filas se borraron."""
        return self._log_repository.delete_older_than(self._cutoff(retention_days))
