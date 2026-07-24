"""Comando que procesa un evento individual.

Toma un evento crudo, lo normaliza usando la estrategia
de normalizacion y lo encola en el gestor de colas para
su transmision o almacenamiento offline.

Soporta output dual del normalizador: eventos parciales
(``evento_llamada`` con ``datos.subtipo``) y consolidados
(``llamada_completa``). Hangup produce ambos en una lista.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# Interfaz base para el patron Command
from src.commands.base import ComandoBase
# Contexto de ejecucion singleton para metricas
from src.core.contexto import ContextoEjecucion
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Estrategia de normalizacion que consolida llamadas completas
from src.strategies.normalization import NormalizadorAMI

# Eventos de llamada que pasan por el normalizador
# Cualquier evento fuera de este conjunto se considera evento del sistema
# y se encola directamente sin normalizar.
TIPOS_LLAMADA = {"NewChannel", "Dial", "Answer", "Hangup", "RTCPReceived", "Cdr"}

# Severidad por tipo de evento del sistema
# Los tipos no listados aqui heredan "INFO" por defecto
MAPA_SEVERIDAD = {
    "Alarm": "CRITICAL",
    "AlarmClear": "WARNING",
    "Shutdown": "CRITICAL",
    "ContactStatus": "WARNING",
}


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
        self._evento_normalizado: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None

    async def ejecutar(self) -> bool:
        """Ejecuta el pipeline de procesamiento del evento.

        El normalizador ahora retorna:
        - ``None``: evento no pertenece a una llamada (los eventos del
          sistema se encolan antes del normalizador).
        - ``Dict`` ``evento_llamada``: evento parcial (NewChannel, Dial,
          Answer, RTCPReceived) — se encola individualmente.
        - ``List[Dict]``: Hangup produce dos outputs — el parcial
          (``evento_llamada.subtipo=hangup``) y el consolidado
          (``llamada_completa``) — ambos se encolan.

        Returns:
            True si el evento fue procesado exitosamente.
        """
        try:
            tipo = self.evento_crudo.get("tipo", "")

            # --- EVENTOS DEL SISTEMA ---
            # Los eventos que NO son de llamada bypassan el normalizador
            # y se encolan directamente como eventos del sistema.
            # Inyectan agent_id y pbx_id del contexto de ejecucion.
            if tipo not in TIPOS_LLAMADA:
                evento_sistema = {
                    "tipo": "sistema",
                    "event_type": tipo,
                    "subtype": None,
                    "severity": MAPA_SEVERIDAD.get(tipo, "INFO"),
                    "payload": {k: v for k, v in self.evento_crudo.items() if k != "tipo"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "agent_id": self.contexto.agente_id,
                    "pbx_id": self.contexto.pbx_id,
                }
                if self.gestor_colas is not None:
                    await self.gestor_colas.encolar(evento_sistema)
                    self.contexto.metricas.eventos_encolados += 1
                self.contexto.metricas.eventos_procesados += 1
                return True

            # Actualizar contador de llamadas activas
            if tipo == "NewChannel":
                self.contexto.metricas.llamadas_activas += 1
            elif tipo == "Hangup":
                self.contexto.metricas.llamadas_activas = max(
                    0, self.contexto.metricas.llamadas_activas - 1
                )

            # Normalizar el evento crudo
            self._evento_normalizado = self.normalizador.normalizar(
                self.evento_crudo
            )

            # Incrementar contador de eventos procesados
            self.contexto.metricas.eventos_procesados += 1

            # None = evento no pertenece a llamada (Queue, SIP, etc.)
            # Nota: eventos del sistema se manejan arriba; esto es seguridad
            # para eventos inesperados que no son de llamada.
            if self._evento_normalizado is None:
                return True

            # Lista = Hangup (parcial + consolidado) — iterar y encolar cada uno
            if isinstance(self._evento_normalizado, list):
                for item in self._evento_normalizado:
                    if self.gestor_colas is not None:
                        await self.gestor_colas.encolar(item)
                        self.contexto.metricas.eventos_encolados += 1
                self.logger.info(
                    "Llamada completada (parcial + consolidado)",
                    contexto={
                        "id_unico": self.evento_crudo.get("id_unico"),
                        "origen": self.evento_crudo.get("origen"),
                        "duracion": self.evento_crudo.get("duracion"),
                    }
                )
                return True

            # Dict = evento_llamada parcial — encolar individualmente
            if self.gestor_colas is not None:
                await self.gestor_colas.encolar(self._evento_normalizado)
                self.contexto.metricas.eventos_encolados += 1

            subtipo = self._evento_normalizado.get("datos", {}).get("subtipo", "")
            self.logger.info(
                "Evento parcial emitido",
                contexto={
                    "subtipo": subtipo,
                    "id_unico": self.evento_crudo.get("id_unico"),
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
