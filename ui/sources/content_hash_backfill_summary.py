"""Textos de la acción "Completar huellas de contenido…" (pestaña Fuentes;
RAG-INC-01, relleno de content_hash). Sin Qt, para poder probarlos."""
from __future__ import annotations

from application.documents.content_hash_backfill import BackfillStatus, ContentHashBackfillReport

TITULO = "Completar huellas de contenido"

CONFIRMACION = (
    "Se calculará la huella de contenido (SHA-256) de las fuentes que todavía no la tienen, "
    "a partir de la copia del archivo original guardada en el proyecto (sources/original/). "
    "No se usa la ubicación externa del archivo.\n\n"
    "- Nunca se modifica una huella existente.\n"
    "- Si dos versiones de una misma fuente tienen el mismo contenido, no se completa ninguna "
    "y se reporta para revisión.\n"
    "- Las instantáneas ya publicadas no cambian: después hay que publicar una nueva antes de "
    "exportar un NEXOM Knowledge Package.\n\n"
    "¿Continuar?"
)

TOOLTIP = (
    "Completa la huella de contenido (SHA-256) de las fuentes heredadas desde la copia del original "
    "del proyecto. Se puede repetir sin riesgo: solo completa las que faltan y deja un informe en "
    "reports/."
)

_ETIQUETAS = {
    BackfillStatus.RELLENADA: "Completadas",
    BackfillStatus.CONTENIDO_COMPARTIDO_ENTRE_LINAJES: "Completadas con contenido compartido entre fuentes distintas",
    BackfillStatus.YA_TENIA: "Ya tenían huella",
    BackfillStatus.NO_APLICA: "No aplica (fuente sin archivo)",
    BackfillStatus.SIN_COPIA_ORIGINAL: "Sin copia del original",
    BackfillStatus.ILEGIBLE: "Copia ilegible",
    BackfillStatus.COLISION_MISMO_LINAJE: "Colisión: mismo contenido en versiones de la misma fuente",
}

_REQUIEREN_ATENCION = (
    BackfillStatus.SIN_COPIA_ORIGINAL, BackfillStatus.ILEGIBLE, BackfillStatus.COLISION_MISMO_LINAJE,
)


def resumen(informe: ContentHashBackfillReport) -> str:
    conteos = informe.counts()
    lineas = [f"Fuentes sin huella: {informe.missing_before} antes → {informe.missing_after} después.", ""]
    for estado, etiqueta in _ETIQUETAS.items():
        if conteos[estado.value]:
            lineas.append(f"{etiqueta}: {conteos[estado.value]}")
    revisar = [r for r in informe.results if r.status in _REQUIEREN_ATENCION]
    if revisar:
        lineas += ["", "Requieren revisión:"]
        for r in revisar[:15]:
            lineas.append(f"- {r.title} ({r.status.value})")
        if len(revisar) > 15:
            lineas.append(f"- … y {len(revisar) - 15} más (ver informe)")
    if informe.missing_after == 0 and informe.missing_before:
        lineas += ["", "Recuerde publicar una instantánea nueva antes de exportar un NEXOM Knowledge Package."]
    lineas += ["", f"Informe: {informe.report_path}" if informe.report_path else "No se pudo guardar el informe (ver log)."]
    return "\n".join(lineas)
