"""Cliente WebSocket asincrono para eventos en tiempo real.

Mantiene una conexion persistente con el backend para
transmitir eventos de llamadas con latencia menor a 500ms.
Implementa reconexion automatica con backoff exponencial.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Serializacion de diccionarios a JSON para transmision
import json
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Libreria websockets para conexiones WebSocket asincronas
import websockets

# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Estrategias de reintento con backoff exponencial
from src.strategies.retry_policy import BackoffExponencial, EstrategiaReintento


class ClienteWebSocket:
    """Cliente WebSocket asincrono con reconexion automatica.

    Mantiene una conexion persistente al backend para
    transmision en tiempo real de eventos. Implementa
    heartbeat y reconexion con backoff exponencial.

    Args:
        url_destino: URL del endpoint WebSocket del backend.
        max_intentos_conexion: Maximo de intentos de reconexion.
        intervalo_ping: Intervalo de keepalive en segundos.
        estrategia_reintento: Estrategia de reintento.
    """

    def __init__(
        self,
        url_destino: str = "",
        max_intentos_conexion: int = 10,
        intervalo_ping: float = 30.0,
        estrategia_reintento: Optional[EstrategiaReintento] = None,
    ) -> None:
        # URL del endpoint WebSocket del backend
        self.url = url_destino
        # Numero maximo de intentos de conexion antes de fallar
        self.max_intentos = max_intentos_conexion
        # Intervalo de ping keepalive en segundos
        self.intervalo_ping = intervalo_ping
        # Estrategia de backoff para demora entre reintentos
        self.estrategia = estrategia_reintento or BackoffExponencial()
        # Conexion WebSocket activa (None si no hay conexion)
        self._conexion: Optional[Any] = None
        # Bandera de estado de conexion
        self._conectado = False
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    @property
    def esta_conectado(self) -> bool:
        """Indica si hay una conexion WebSocket activa."""
        return self._conectado

    async def conectar(self, agente_id: str) -> bool:
        """Establece conexion WebSocket con el backend.

        Args:
            agente_id: UUID del agente para autenticacion.

        Returns:
            True si la conexion fue exitosa.
        """
        if not self.url:
            self.logger.advertencia("URL WebSocket no configurada")
            return False

        # Intentar conexion con reintentos y backoff exponencial
        for intento in range(1, self.max_intentos + 1):
            try:
                # Cabecera con identificador del agente
                cabeceras = {"X-Agent-ID": agente_id}
                # Establecer conexion WebSocket
                self._conexion = await websockets.connect(
                    self.url,
                    additional_headers=cabeceras,
                    ping_interval=self.intervalo_ping,
                )
                self._conectado = True
                self.logger.info(
                    "Conexion WebSocket establecida",
                    contexto={"url": self.url}
                )
                return True

            except Exception as error:
                self.logger.advertencia(
                    f"Fallo conexion WebSocket ({intento}/{self.max_intentos})",
                    contexto={"error": str(error)}
                )

                # Esperar con backoff antes del siguiente intento
                if intento < self.max_intentos:
                    demora = self.estrategia.calcular_demora(intento)
                    import asyncio
                    await asyncio.sleep(demora)

        self.logger.error("No se pudo establecer conexion WebSocket")
        return False

    async def cerrar(self) -> None:
        """Cierra la conexion WebSocket de forma segura."""
        self._conectado = False
        if self._conexion is not None:
            try:
                await self._conexion.close()
            except Exception:
                pass
            self._conexion = None
            self.logger.info("Conexion WebSocket cerrada")

    async def enviar_evento(
        self,
        evento: Dict[str, Any],
        agente_id: str,
    ) -> bool:
        """Envia un evento individual por WebSocket.

        Args:
            evento: Evento normalizado a enviar.
            agente_id: UUID del agente.

        Returns:
            True si el envio fue exitoso.
        """
        # Si no hay conexion activa, intentar reconectar
        if not self._conectado or self._conexion is None:
            exito = await self.reconectar(agente_id)
            if not exito:
                return False

        try:
            # Serializar evento a JSON para transmision
            mensaje = json.dumps(evento, ensure_ascii=False, default=str)
            # Enviar mensaje por el socket WebSocket
            await self._conexion.send(mensaje)
            return True

        except Exception as error:
            self.logger.error(
                "Error enviando evento por WebSocket",
                contexto={"error": str(error)}
            )
            self._conectado = False
            return False

    async def reconectar(self, agente_id: str) -> bool:
        """Reintenta la conexion WebSocket.

        Args:
            agente_id: UUID del agente.

        Returns:
            True si la reconexion fue exitosa.
        """
        await self.cerrar()
        return await self.conectar(agente_id)
