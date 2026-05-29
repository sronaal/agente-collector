"""Define las interfaces abstractas para las estrategias.

Las estrategias son algoritmos intercambiables que permiten
modificar el comportamiento del agente sin cambiar su
estructura: normalizacion, reintentos y transmision.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para definir clases abstractas con metodos abstractos
from abc import ABC, abstractmethod
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, List, Optional


class EstrategiaNormalizacion(ABC):
    """Interfaz para estrategias de normalizacion de eventos.

    Transforma eventos crudos de diferentes fuentes (AMI, CDR, CEL)
    a un esquema interno unificado.
    """

    @abstractmethod
    def normalizar(self, evento_crudo: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza un evento crudo a esquema unificado.

        Args:
            evento_crudo: Diccionario con datos originales del evento.

        Returns:
            Diccionario con datos normalizados segun esquema CallMetric.
        """
        ...


class EstrategiaReintento(ABC):
    """Interfaz para estrategias de reintento de operaciones.

    Define como y cuando reintentar operaciones fallidas
    (transmisiones, conexiones, etc.).
    """

    @abstractmethod
    def calcular_demora(self, intento: int) -> float:
        """Calcula el tiempo de espera antes del siguiente intento.

        Args:
            intento: Numero de intento actual (1-based).

        Returns:
            Tiempo en segundos a esperar.
        """
        ...


class EstrategiaTransmision(ABC):
    """Interfaz para estrategias de transmision de eventos.

    Define como se envian los eventos al backend:
    por lotes via HTTP o en tiempo real via WebSocket.
    """

    @abstractmethod
    async def transmitir(
        self,
        eventos: List[Dict[str, Any]],
        agente_id: str,
    ) -> bool:
        """Transmite una lista de eventos al backend.

        Args:
            eventos: Lista de eventos normalizados a enviar.
            agente_id: Identificador unico del agente.

        Returns:
            True si la transmision fue exitosa.
        """
        ...
