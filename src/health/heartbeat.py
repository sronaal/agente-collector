"""Modulo que gestiona el heartbeat periodico del agente.

Envia senales de vida al backend segun el intervalo
configurado y verifica que el agente siga siendo valido.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para tareas asincronas (creacion y cancelacion de Tasks)
import asyncio
# Tipos para firmas de metodos con type hints
from typing import Any, Optional

# Contexto de ejecucion singleton con estado del agente
from src.core.contexto import ContextoEjecucion, EstadoAgente
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado


class HeartbeatManager:
    """Gestiona el envio periodico de heartbeats al backend.

    Ejecuta el comando de heartbeat en un bucle con el
    intervalo configurado. Si el heartbeat falla,
    incrementa el contador de errores.

    Args:
        comando_heartbeat: Comando que ejecuta el heartbeat.
        intervalo: Segundos entre heartbeats.
    """

    def __init__(
        self,
        comando_heartbeat: Any,
        intervalo: int = 30,
    ) -> None:
        # Comando que ejecuta la logica del heartbeat
        self.comando = comando_heartbeat
        # Intervalo en segundos entre heartbeats
        self.intervalo = intervalo
        # Contexto singleton para actualizar metricas
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()
        # Tarea asincrona del bucle (None hasta iniciar())
        self._tarea: Optional[asyncio.Task] = None
        # Bandera de actividad del heartbeat
        self._activo = False

    async def iniciar(self) -> None:
        """Inicia el bucle de heartbeats periodicos."""
        self._activo = True
        self._tarea = asyncio.create_task(self._bucle_heartbeat())
        self.logger.info(
            "Heartbeat iniciado",
            contexto={"intervalo": self.intervalo}
        )

    async def detener(self) -> None:
        """Detiene el bucle de heartbeats."""
        self._activo = False
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass
        self.logger.info("Heartbeat detenido")

    async def _bucle_heartbeat(self) -> None:
        """Bucle principal que envia heartbeats en intervalos regulares."""
        while self._activo:
            try:
                # Ejecutar comando de heartbeat (Ping AMI + notificar backend)
                exito = await self.comando.ejecutar()

                if not exito:
                    self.contexto.metricas.errores_conexion += 1
                    self.logger.advertencia(
                        "Heartbeat fallido",
                        contexto={
                            "errores_consecutivos": self.contexto.metricas.errores_conexion
                        }
                    )

                # Esperar el intervalo antes del proximo heartbeat
                await asyncio.sleep(self.intervalo)

            except asyncio.CancelledError:
                break

            except Exception as error:
                self.logger.error(
                    "Error en bucle de heartbeat",
                    contexto={"error": str(error)}
                )
                await asyncio.sleep(self.intervalo)
