"""Modulos de buffer para resiliencia offline.

El buffer garantiza que ningun evento se pierda ante
caidas de red o del backend, almacenando localmente
hasta que pueda ser transmitido.
"""

# Exportar componentes del buffer para acceso publico
from src.buffer.sqlite_store import AlmacenSQLite
from src.buffer.queue_manager import GestorColas

# Lista de simbolos publicos del modulo
__all__ = ["AlmacenSQLite", "GestorColas"]
