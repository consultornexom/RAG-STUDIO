"""RAG STUDIO — código fuente del núcleo (Etapa 1).

Ver ADR-001 (Arquitectura y modelo de dominio) para la regla de
dependencia entre capas. Resumen:

    ui -> application -> domain <- infrastructure (implementa puertos)
    workers -> application, infrastructure
    plugins -> domain (solo puertos)

domain no depende de ninguna otra capa ni de SDKs de proveedores.
"""
