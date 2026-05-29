"""Iterador asincrono que consume eventos desde el conector AMI.

Implementa el patron Iterator para exponer los eventos AMI
como un flujo continuo de datos, permitiendo procesamiento
uno a uno sin acumular en memoria.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from typing import Any, AsyncIterator, Dict

# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Interfaz abstracta que esta clase implementa
from src.iterators.base import IteradorBase


class StreamAMI(IteradorBase):
    """Iterador que consume eventos del conector AMI.

    Toma eventos de la cola del conector y los entrega
    uno por uno al pipeline de procesamiento.

    Args:
        fuente_eventos: Conector AMI del cual leer eventos.
    """

    def __init__(self, fuente_eventos: Any) -> None:
        # Fuente de eventos (debe implementar leer_eventos())
        self.fuente = fuente_eventos
        # Bandera de actividad del stream
        self._activo = False
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def iterar(self) -> AsyncIterator[Dict[str, Any]]:
        """Itera sobre los eventos del conector AMI.

        Lee eventos de la cola interna del conector y los
        entrega al pipeline para normalizacion y encolado.

        Yields:
            Diccionario con los datos del evento recibido.
        """
        self._activo = True

        # Delegar en el metodo leer_eventos() del conector
        async for evento in self.fuente.leer_eventos():
            if not self._activo:
                break
            yield evento

    async def detener(self) -> None:
        """Detiene la iteracion de eventos de forma segura."""
        self._activo = False
        self.logger.info("Stream AMI detenido")
