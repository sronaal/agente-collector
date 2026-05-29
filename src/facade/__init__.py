"""Modulos de la fachada del motor de ingestion.

La fachada expone una API simple (iniciar, detener, estado)
que oculta la complejidad interna de la arquitectura
de patrones del agente.
"""

# Exportar fachada principal para acceso publico
from src.facade.ingestion_engine import MotorIngestion

# Lista de simbolos publicos del modulo
__all__ = ["MotorIngestion"]
