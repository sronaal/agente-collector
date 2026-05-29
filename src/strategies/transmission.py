"""Estrategias de transmision de eventos al backend.

Implementa dos modos de transmision: HTTP para lotes de
eventos historicos y WebSocket para eventos en tiempo real.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Serializacion de diccionarios a JSON para el cuerpo de peticiones
import json
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, List, Optional

# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Interfaz abstracta que estas clases implementan
from src.strategies.base import EstrategiaTransmision


class EstrategiaHTTPBatch(EstrategiaTransmision):
    """Transmite eventos al backend mediante HTTP POST por lotes.

    Envia los eventos acumulados en lotes utilizando el cliente
    HTTP configurado. Soporta compresion y reintentos.

    Args:
        cliente_http: Cliente HTTP para realizar las peticiones.
        url_destino: URL del endpoint de ingesta de eventos.
        timeout: Timeout de la peticion en segundos.
    """

    def __init__(
        self,
        cliente_http: Any,
        url_destino: str = "",
        timeout: float = 30.0,
    ) -> None:
        # Cliente HTTP asincrono con reintentos incorporados
        self.cliente = cliente_http
        # URL del endpoint donde se enviaran los eventos
        self.url = url_destino
        # Timeout maximo para la peticion HTTP
        self.timeout = timeout
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def transmitir(
        self,
        eventos: List[Dict[str, Any]],
        agente_id: str,
    ) -> bool:
        """Transmite un lote de eventos via HTTP POST.

        Args:
            eventos: Lista de eventos normalizados a enviar.
            agente_id: UUID del agente para el header X-Agent-ID.

        Returns:
            True si la transmision fue exitosa, False en caso contrario.
        """
        if not eventos:
            return True

        if not self.url:
            self.logger.advertencia("URL de backend no configurada, simulando envio")
            self._registrar_envio_simulado(eventos, agente_id)
            return True

        try:
            # Serializar todos los eventos como un unico JSON
            payload = json.dumps(eventos, ensure_ascii=False, default=str)
            # Cabeceras HTTP estandar + identificador del agente
            cabeceras = {
                "Content-Type": "application/json",
                "X-Agent-ID": agente_id,
            }

            # Enviar lote via POST al endpoint de eventos
            respuesta = await self.cliente.enviar_peticion(
                metodo="POST",
                url=self.url,
                datos=payload,
                cabeceras=cabeceras,
                timeout=self.timeout,
            )

            if respuesta:
                self.logger.info(
                    "Lote transmitido exitosamente",
                    contexto={"cantidad": len(eventos)}
                )
                return True

            self.logger.error("Fallio la transmision del lote")
            return False

        except Exception as error:
            self.logger.error(
                "Error en transmision HTTP",
                contexto={"error": str(error), "cantidad": len(eventos)}
            )
            return False

    def _registrar_envio_simulado(
        self,
        eventos: List[Dict[str, Any]],
        agente_id: str,
    ) -> None:
        """Registra en log el envio simulado cuando no hay backend.

        Args:
            eventos: Lista de eventos que se enviarian.
            agente_id: UUID del agente.
        """
        for evento in eventos:
            self.logger.info(
                f"[SIMULACION] Evento transmitido: {evento.get('tipo')}",
                contexto={
                    "event_id": evento.get("event_id"),
                    "agente_id": agente_id,
                    "timestamp": evento.get("timestamp"),
                }
            )


class EstrategiaWSRealtime(EstrategiaTransmision):
    """Transmite eventos al backend en tiempo real via WebSocket.

    Util para eventos que requieren latencia menor a 500ms.
    Mantiene una conexion persistente y reutiliza el socket.

    Args:
        cliente_ws: Cliente WebSocket para la conexion persistente.
        url_destino: URL del endpoint WebSocket.
    """

    def __init__(
        self,
        cliente_ws: Any,
        url_destino: str = "",
    ) -> None:
        # Cliente WebSocket asincrono con reconexion automatica
        self.cliente = cliente_ws
        # URL del endpoint WebSocket del backend
        self.url = url_destino
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def transmitir(
        self,
        eventos: List[Dict[str, Any]],
        agente_id: str,
    ) -> bool:
        """Transmite eventos en tiempo real via WebSocket.

        Args:
            eventos: Lista de eventos normalizados.
            agente_id: UUID del agente.

        Returns:
            True si la transmision fue exitosa.
        """
        if not eventos:
            return True

        # Enviar cada evento individualmente por WebSocket
        for evento in eventos:
            try:
                exito = await self.cliente.enviar_evento(evento, agente_id)
                if not exito:
                    self.logger.error(
                        "Fallio transmision WebSocket",
                        contexto={"event_id": evento.get("event_id")}
                    )
                    return False
            except Exception as error:
                self.logger.error(
                    "Error en transmision WebSocket",
                    contexto={
                        "error": str(error),
                        "event_id": evento.get("event_id"),
                    }
                )
                return False

        return True
