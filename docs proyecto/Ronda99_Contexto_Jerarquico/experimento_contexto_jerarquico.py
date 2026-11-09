"""Ronda 99 -- experimento de recuperación densa con y sin la ruta de
encabezados (ver Analisis_Contexto_Jerarquico.md). Se ejecuta desde la raíz
del repositorio, sin red, con el modelo ya descargado en data/models:

    python3 "docs proyecto/Ronda99_Contexto_Jerarquico/experimento_contexto_jerarquico.py"
"""
import sys

import numpy as np

sys.path.insert(0, ".")
from fastembed import TextEmbedding

from domain.ingestion.heading_context import heading_outline, heading_path_at
from domain.ingestion.splitting import split_by_headings

T="""# Bachillerato — Plantel Torres Landa
## Plan de estudios
### 3er. semestre
* Matemáticas III
* Biología I
* Física I
* Historia de México I
* Literatura I
* Inglés III
* Emprendimiento y Empresa
* Proceso Administrativo
### 4to. semestre
* Matemáticas IV
* Biología II
* Física II
* Historia de México II
* Literatura II
* Inglés IV
* Legalidad Empresarial
* Mercadotecnia
## Área Económico-Administrativa y Humanidades
### 5.º semestre
* Geografía
* Estructura Socioeconómica de México
* Economía I
* Matemáticas Financieras I
* Derecho I
* Ciencias de la Comunicación I
* Finanzas
* Ventas y Difusión
### 6.º semestre
* Filosofía
* Ecología y Medio Ambiente
* Historia Universal Contemporánea
* Economía II
* Matemáticas Financieras II
* Derecho II
* Ciencias de la Comunicación II
* Comunicación de la Empresa
* Proyecto Emprendedor
## Área Físico-Matemática y Químico-Biológicas
### 5.º semestre
* Geografía
* Estructura Socioeconómica de México
* Temas Selectos de Química I
* Temas Selectos de Física I
* Temas Selectos de Biología I
* Cálculo diferencial
* Finanzas
* Ventas y Difusión
### 6.º semestre
* Filosofía
* Ecología y Medio Ambiente
* Historia Universal Contemporánea
* Temas Selectos de Química II
* Temas Selectos de Física II
* Temas Selectos de Biología II
* Cálculo Integral
* Comunicación de la Empresa
* Proyecto Emprendedor
"""
MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PREGUNTAS = [
    "¿Qué materias se cursan en quinto semestre del área Económico-Administrativa en Torres Landa?",
    "materias de quinto semestre del área económico administrativa",
    "¿Qué materias lleva el 5.º semestre del área Físico-Matemática?",
    "materias del sexto semestre área químico biológicas",
]


def fragmentos():
    """Fragmentos indexables de por_encabezado: (ruta, texto, ruta+texto)."""
    esquema = heading_outline(T)
    salida = []
    for titulo, span in split_by_headings(T):
        texto = span.text.strip()
        if texto.lstrip("#").strip() == titulo:
            continue  # solo encabezado: RAG Studio no lo indexa
        ruta = " > ".join(e.title for e in heading_path_at(esquema, span.char_start))
        salida.append((ruta.split(" > ", 1)[1], texto, f"{ruta}\n{texto}"))
    return salida


def unit(matriz):
    return matriz / np.linalg.norm(matriz, axis=-1, keepdims=True)


def main():
    modelo = TextEmbedding(MODELO, cache_dir="data/models", local_files_only=True)
    docs = fragmentos()
    for nombre, idx in (("A) texto actual del fragmento", 1), ("B) ruta de encabezados + texto", 2)):
        vectores = unit(np.array(list(modelo.embed([d[idx] for d in docs]))))
        print(nombre)
        for pregunta in PREGUNTAS:
            consulta = unit(np.array(list(modelo.embed([pregunta])))[0])
            puntajes = vectores @ consulta
            print("  Q:", pregunta)
            for k, i in enumerate(np.argsort(-puntajes)[:3]):
                print(f"    {k + 1}. {puntajes[i]:.3f} {docs[i][0]}")


if __name__ == "__main__":
    main()
