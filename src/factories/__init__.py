"""Modulos de fabricas para creacion de componentes.

Implementan el patron Factory Method para desacoplar
la creacion de objetos de su uso en el pipeline.
"""

# Exportar fabrica de conectores para acceso publico
from src.factories.event_source_factory import FabricaFuenteEventos

# Lista de simbolos publicos del modulo
__all__ = ["FabricaFuenteEventos"]
