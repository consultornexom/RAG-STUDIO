"""Contexto RAG (Etapa 4 -- nucleo): embeddings + indice vectorial +
busqueda semantica sobre los Chunk que produce la Etapa 3.

Alcance de esta iteracion (acordado explicitamente con el usuario,
igual que se acoto la Etapa 3): indexacion de fragmentos + busqueda
semantica basica con filtro de metadatos. Sin comparacion de
configuraciones de embeddings, sin reranking, sin orquestacion
conversacional ni UI todavia -- eso es trabajo de iteraciones
posteriores (Intent, RetrievalConfig, Rule/Guardrail de ADR-001,
seccion 5).
"""
