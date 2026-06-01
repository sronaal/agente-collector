"""Cliente WebSocket asincrono para eventos en tiempo real.

Mantiene una conexion persistente con el backend para
transmitir eventos de llamadas con latencia menor a 500ms.
Implementa reconexion automatica con backoff exponencial
y un bucle de fondo que mantiene la conexion viva.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

import websockets

from src.core.logger import LoggerEstructurado
from src.strategies.retry_policy import BackoffExponencial, EstrategiaReintento


class ClienteWebSocket:
    """Cliente WebSocket asincrono con reconexion automatica.

    Mantiene una conexion persistente al backend para
    transmision en tiempo real de eventos. Ejecuta un
    bucle de reconexion en background que asegura que
    la conexion siempre este activa.

    Args:
        url_destino: URL del endpoint WebSocket del backend.
        max_intentos_conexion: Maximo de intentos de reconexion.
        intervalo_ping: Intervalo de keepalive en segundos.
        intervalo_reconexion: Segundos entre reintentos de reconexion.
        estrategia_reintento: Estrategia de reintento.
    """

    def __init__(
        self,
        url_destino: str = "",
        max_intentos_conexion: int = 10,
        intervalo_ping: float = 30.0,
        intervalo_reconexion: float = 5.0,
        estrategia_reintento: Optional[EstrategiaReintento] = None,
    ) -> None:
        self.url = url_destino
        self.max_intentos = max_intentos_conexion
        self.intervalo_ping = intervalo_ping
        self.intervalo_reconexion = intervalo_reconexion
        self.estrategia = estrategia_reintento or BackoffExponencial()
        self._conexion: Optional[Any] = None
        self._conectado = False
        self._agente_id: str = ""
        self._activo = False
        self._tarea_reconexion: Optional[asyncio.Task] = None
        self.logger = LoggerEstructurado.obtener_instancia()

    @property
    def esta_conectado(self) -> bool:
        return self._conectado

    async def conectar(self, agente_id: str) -> bool:
        """Establece conexion WebSocket con el backend.

        Inicia el bucle de reconexion en background.

        Args:
            agente_id: UUID del agente para autenticacion.

        Returns:
            True si la conexion fue exitosa.
        """
        self._agente_id = agente_id

        if not self.url:
            self.logger.advertencia("URL WebSocket no configurada")
            return False

        self._activo = True
        exito = await self._conectar_intentar()
        self._tarea_reconexion = asyncio.create_task(self._bucle_reconexion())
        return exito

    async def _conectar_intentar(self) -> bool:
        """Intenta establecer conexion con reintentos."""
        for intento in range(1, self.max_intentos + 1):
            try:
                cabeceras = {"X-Agent-ID": self._agente_id}
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
                if intento < self.max_intentos:
                    demora = self.estrategia.calcular_demora(intento)
                    await asyncio.sleep(demora)

        self.logger.error("No se pudo establecer conexion WebSocket")
        return False

    async def _bucle_reconexion(self) -> None:
        """Bucle de fondo que mantiene la conexion activa.

        Verifica periodicamente el estado de la conexion.
        Si se pierde, reintenta la conexion automaticamente.
        """
        while self._activo:
            try:
                if not self._conectado or self._conexion is None:
                    self.logger.info("Reconectando WebSocket...")
                    await self._conectar_intentar()
                elif self._conexion is not None:
                    try:
                        pong = await asyncio.wait_for(
                            self._conexion.ping(),
                            timeout=5.0
                        )
                        await asyncio.wait_for(pong, timeout=5.0)
                    except Exception:
                        self._conectado = False
                        self.logger.advertencia("WebSocket ping fallido, reconectando...")
                        await self._conectar_intentar()

                await asyncio.sleep(self.intervalo_reconexion)

            except asyncio.CancelledError:
                break
            except Exception as error:
                self.logger.error(
                    "Error en bucle de reconexion WebSocket",
                    contexto={"error": str(error)}
                )
                await asyncio.sleep(self.intervalo_reconexion)

    async def cerrar(self) -> None:
        """Cierra la conexion WebSocket de forma segura."""
        self._activo = False

        if self._tarea_reconexion is not None:
            self._tarea_reconexion.cancel()
            try:
                await self._tarea_reconexion
            except (asyncio.CancelledError, Exception):
                pass
            self._tarea_reconexion = None

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

        Si no hay conexion activa, reintenta conectarse.

        Args:
            evento: Evento normalizado a enviar.
            agente_id: UUID del agente.

        Returns:
            True si el envio fue exitoso.
        """
        if not self._conectado or self._conexion is None:
            exito = await self._conectar_intentar()
            if not exito:
                return False

        try:
            mensaje = json.dumps(evento, ensure_ascii=False, default=str)
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
        """Reintenta la conexion WebSocket."""
        await self.cerrar()
        return await self.conectar(agente_id)
