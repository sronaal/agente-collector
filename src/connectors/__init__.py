"""Modulos de conectores para captura de eventos telefonicos.

Cada conector implementa la logica especifica para leer
datos desde una fuente particular (AMI, CDR, CEL, sistema).
"""

# Exportar ConectorAMI para acceso publico desde el paquete
from src.connectors.ami_connector import ConectorAMI

# Lista de simbolos publicos del modulo
__all__ = ["ConectorAMI"]
