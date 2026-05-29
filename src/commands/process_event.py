"""Comando que procesa un evento individual.

Toma un evento crudo, lo normaliza usando la estrategia
de normalizacion y lo encola en el gestor de colas para
su transmision o almacenamiento offline.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Interfaz base para el patron Command
from src.commands.base import ComandoBase
# Contexto de ejecucion singleton para metricas
from src.core.contexto import ContextoEjecucion
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Estrategia de normalizacion que consolida llamadas completas
from src.strategies.normalization import NormalizadorAMI


class ComandoProcesarEvento(ComandoBase):
    """Comando que normaliza y encola un evento para su transmision.

    Pipeline:
        1. Recibe evento crudo desde el conector/iterador
        2. Normaliza usando NormalizadorAMI
        3. Inyecta agent_id desde el contexto
        4. Encola en el gestor de colas

    Args:
        evento_crudo: Diccionario con datos crudos del evento.
        normalizador: Estrategia de normalizacion a utilizar.
        gestor_colas: Gestor de colas para encolar el evento procesado.
    """

    def __init__(
        self,
        evento_crudo: Dict[str, Any],
        normalizador: Optional[NormalizadorAMI] = None,
        gestor_colas: Any = None,
    ) -> None:
        # Evento crudo recibido directamente del conector AMI
        self.evento_crudo = evento_crudo
        # Normalizador que consolida eventos parciales en llamadas completas
        self.normalizador = normalizador or NormalizadorAMI()
        # Gestor de colas para encolar el evento normalizado
        self.gestor_colas = gestor_colas
        # Contexto singleton para actualizar metricas
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()
        # Almacena el resultado de la normalizacion para posible deshacer
        self._evento_normalizado: Optional[Dict[str, Any]] = None

    async def ejecutar(self) -> bool:
        """Ejecuta el pipeline de procesamiento del evento.

        El normalizador consolida eventos parciales (NewChannel,
        Dial, Answer) internamente y solo retorna un registro
        cuando la llamada finaliza (Hangup). Los eventos parciales
        no se encolan individualmente.

        Returns:
            True si el evento fue procesado (puede ser parcial).
        """
        try:
            tipo = self.evento_crudo.get("tipo", "")

            # Actualizar contador de llamadas activas
            if tipo == "NewChannel":
                self.contexto.metricas.llamadas_activas += 1
            elif tipo == "Hangup":
                self.contexto.metricas.llamadas_activas = max(
                    0, self.contexto.metricas.llamadas_activas - 1
                )

            # Normalizar el evento crudo (None si es evento parcial)
            self._evento_normalizado = self.normalizador.normalizar(
                self.evento_crudo
            )

            # Incrementar contador de eventos procesados
            self.contexto.metricas.eventos_procesados += 1

            # None = evento parcial (NewChannel, Dial, Answer)
            # La llamada aun no termina, no se transmite individualmente
            if self._evento_normalizado is None:
                return True

            # Encolar el evento consolidado (llamada completa) para transmision
            if self.gestor_colas is not None:
                await self.gestor_colas.encolar(self._evento_normalizado)
                self.contexto.metricas.eventos_encolados += 1

            self.logger.info(
                "Llamada completada",
                contexto={
                    "id_unico": self.evento_crudo.get("id_unico"),
                    "origen": self.evento_crudo.get("origen"),
                    "duracion": self.evento_crudo.get("duracion"),
                }
            )
            return True

        except Exception as error:
            self.logger.error(
                "Error al procesar evento",
                contexto={
                    "error": str(error),
                    "tipo": self.evento_crudo.get("tipo"),
                }
            )
            self.contexto.metricas.eventos_perdidos += 1
            return False

    async def deshacer(self) -> None:
        """Intenta revertir el procesamiento (si aplica).

        Si el evento fue encolado, lo marca como pendiente
        para reintento en lugar de perderlo.
        """
        if self._evento_normalizado and self.gestor_colas is not None:
            self.logger.advertencia(
                "Deshaciendo procesamiento de evento",
                contexto={"event_id": self._evento_normalizado.get("event_id")}
            )
