"""Capa workers: ejecución en segundo plano (hilos, procesos, colas).

La UI nunca ejecuta trabajo pesado en su propio hilo; siempre delega
aquí a través de application. Ver ADR-001, sección 10.
"""
