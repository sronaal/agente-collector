"""Modulos de estrategias para comportamiento intercambiable.

Las estrategias implementan algoritmos intercambiables para
normalizacion, reintentos y transmision, permitiendo cambiar
el comportamiento sin modificar el codigo del pipeline.
"""

# Exportar estrategias para acceso publico desde el paquete
from src.strategies.normalization import NormalizadorAMI
from src.strategies.retry_policy import BackoffExponencial, SinReintento
from src.strategies.transmission import EstrategiaHTTPBatch, EstrategiaWSRealtime

# Lista de simbolos publicos del modulo
__all__ = [
    "NormalizadorAMI",
    "BackoffExponencial",
    "SinReintento",
    "EstrategiaHTTPBatch",
    "EstrategiaWSRealtime",
]
