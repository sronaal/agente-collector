"""Modulos de monitoreo de salud del agente.

Gestionan el heartbeat periodico y la recoleccion de
metricas internas del agente (CPU, RAM, cola, buffer).
"""

# Exportar componentes de salud para acceso publico
from src.health.heartbeat import HeartbeatManager
from src.health.self_monitor import AutoMonitor

# Lista de simbolos publicos del modulo
__all__ = ["HeartbeatManager", "AutoMonitor"]
