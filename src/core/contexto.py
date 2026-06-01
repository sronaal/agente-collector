"""Modulo Singleton para el contexto de ejecucion del agente.

Mantiene el estado global del runtime: identificador del agente,
metadatos de la PBX, estado de conexion y metricas internas.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para timestamps Unix y calculo de tiempo activo
import time
# Decorador para data class de metricas internas
from dataclasses import dataclass
# Enumeracion de estados posibles del ciclo de vida
from enum import Enum
# Tipos para firmas de metodos con type hints
from typing import Dict, Optional


class EstadoAgente(Enum):
    """Estados posibles del ciclo de vida del agente."""
    DETENIDO = "detenido"
    INICIANDO = "iniciando"
    ACTIVO = "activo"
    MODO_SEGURO = "modo_seguro"
    ERROR = "error"
    DETENIENDOSE = "deteniendose"


@dataclass
class MetricasInternas:
    """Metricas de rendimiento y salud del agente."""
    eventos_procesados: int = 0
    eventos_transmitidos: int = 0
    eventos_encolados: int = 0
    eventos_perdidos: int = 0
    errores_conexion: int = 0
    intentos_reconexion: int = 0
    ultimo_heartbeat: float = 0.0
    inicio_agente: float = 0.0
    llamadas_activas: int = 0


class ContextoEjecucion:
    """Singleton que mantiene el estado global del agente.

    Almacena informacion compartida entre todos los modulos:
    identificador, estado, metadatos de la PBX y metricas.

    Uso:
        contexto = ContextoEjecucion.obtener_instancia()
        contexto.estado = EstadoAgente.ACTIVO
        contexto.metricas.eventos_procesados += 1
    """

    _instancia: Optional[ContextoEjecucion] = None

    def __init__(self) -> None:
        # UUID del agente asignado por el backend
        self.agente_id: str = ""
        self.empresa_id: str = ""
        self.estado: EstadoAgente = EstadoAgente.DETENIDO
        self.pbx_host: str = ""
        self.pbx_version: str = ""
        # Contadores y metricas internas del agente
        self.metricas: MetricasInternas = MetricasInternas()
        # Diccionario para datos adicionales arbitrarios
        self._datos_adicionales: Dict[str, str] = {}

    @classmethod
    def obtener_instancia(cls) -> ContextoEjecucion:
        """Retorna la instancia unica del singleton.

        Returns:
            Instancia unica del contexto de ejecucion.
        """
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    def inicializar(self, agente_id: str, pbx_host: str, empresa_id: str = "") -> None:
        """Inicializa el contexto con los datos del agente.

        Args:
            agente_id: UUID unico del agente.
            pbx_host: Direccion IP o hostname de la PBX.
            empresa_id: UUID de la empresa (tenant) opcional.
        """
        self.agente_id = agente_id
        self.empresa_id = empresa_id
        self.pbx_host = pbx_host
        self.metricas.inicio_agente = time.time()
        self.estado = EstadoAgente.INICIANDO

    def esta_activo(self) -> bool:
        """Verifica si el agente esta en estado activo.

        Returns:
            True si el estado es ACTIVO.
        """
        return self.estado == EstadoAgente.ACTIVO

    def esta_en_modo_seguro(self) -> bool:
        """Verifica si el agente esta en modo seguro.

        En modo seguro se captura pero no se transmite.

        Returns:
            True si el estado es MODO_SEGURO.
        """
        return self.estado == EstadoAgente.MODO_SEGURO

    def activar_modo_seguro(self) -> None:
        """Activa el modo seguro del agente.

        Se activa cuando el backend rechaza la conexion (401/403).
        """
        self.estado = EstadoAgente.MODO_SEGURO

    def tiempo_activo(self) -> float:
        """Calcula el tiempo transcurrido desde el inicio.

        Returns:
            Segundos desde que se inicio el agente.
        """
        if self.metricas.inicio_agente == 0:
            return 0.0
        return time.time() - self.metricas.inicio_agente
