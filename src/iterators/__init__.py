"""Modulos de iteradores para procesamiento de streams.

Los iteradores permiten consumir datos de diferentes fuentes
de forma eficiente, sin cargar todo en memoria y con soporte
para pausas y reanudacion.
"""

# Exportar iterador AMI para acceso publico
from src.iterators.ami_stream import StreamAMI

# Lista de simbolos publicos del modulo
__all__ = ["StreamAMI"]
