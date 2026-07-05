"""Comando que envia heartbeat periodico al backend.

Mantiene viva la conexion con el backend y verifica
que el agente siga siendo valido. Si recibe 401/403,
activa el modo seguro.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Interfaz base para el patron Command
from src.commands.base import ComandoBase
# Contexto de ejecucion singleton con estado del agente
from src.core.contexto import ContextoEjecucion, EstadoAgente
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado


class ComandoEnviarHeartbeat(ComandoBase):
    """Comando que envia una senal de vida al backend.

    El heartbeat cumple dos funciones:
    1. Mantiene la conexion activa
    2. Verifica que el agente no haya sido revocado

    Args:
        gestor_llamadas: CallManager para enviar Ping AMI.
        cliente_http: Cliente HTTP para heartbeat al backend.
        intervalo: Intervalo entre heartbeats en segundos.
    """

    def __init__(
        self,
        gestor_llamadas: Any = None,
        cliente_http: Any = None,
        intervalo: int = 30,
    ) -> None:
        # CallManager de asyncio-manager para enviar Ping a Asterisk
        self.gestor = gestor_llamadas
        # Cliente HTTP para notificar al backend
        self.cliente = cliente_http
        # Intervalo entre heartbeats en segundos
        self.intervalo = intervalo
        # Contexto singleton del agente
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def ejecutar(self) -> bool:
        """Ejecuta el envio de heartbeat.

        Verifica salud del AMI con un Ping, notifica al
        backend, y si el backend rechaza (401/403) activa
        modo seguro.

        Returns:
            True si el heartbeat fue exitoso.
        """
        try:
            # Verificar que la conexion AMI responda a Ping
            estado_ami = await self._verificar_salud_ami()

            # Si hay cliente HTTP, notificar al backend
            if self.cliente is not None:
                estado_backend = await self._notificar_backend(estado_ami)
                if not estado_backend:
                    # Backend rechazo la conexion (401/403)
                    self.contexto.activar_modo_seguro()
                    return False

                # Recuperar de modo seguro si el heartbeat vuelve a funcionar
                if self.contexto.esta_en_modo_seguro():
                    self.contexto.estado = EstadoAgente.ACTIVO
                    self.logger.info(
                        "Agente recuperado del modo seguro",
                        contexto={
                            "tiempo_activo": f"{self.contexto.tiempo_activo():.0f}s"
                        }
                    )

            # Actualizar timestamp del ultimo heartbeat exitoso
            self.contexto.metricas.ultimo_heartbeat = __import__("time").time()
            self.logger.info(
                "Heartbeat enviado",
                contexto={
                    "tiempo_activo": f"{self.contexto.tiempo_activo():.0f}s",
                    "estado": self.contexto.estado.value,
                }
            )
            return True

        except Exception as error:
            self.logger.error(
                "Error al enviar heartbeat",
                contexto={"error": str(error)}
            )
            return False

    async def _verificar_salud_ami(self) -> Dict[str, Any]:
        """Verifica la salud de la conexion AMI mediante un Ping.

        Envia una accion Ping a Asterisk y verifica la respuesta.

        Returns:
            Diccionario con el estado de la conexion AMI.
        """
        estado: Dict[str, Any] = {
            "conectado": False,
            "ping_exitoso": False,
        }

        if self.gestor is None:
            return estado

        try:
            # Verificar que el socket TCP este conectado
            if self.gestor._manager.is_connected:
                estado["conectado"] = True
                # Enviar accion Ping al AMI de Asterisk
                respuesta = await self.gestor._manager.send_action(
                    {"Action": "Ping"}
                )
                estado["ping_exitoso"] = respuesta.is_success
        except Exception:
            estado["conectado"] = False

        return estado

    async def _notificar_backend(self, estado_ami: Dict[str, Any]) -> bool:
        """Notifica al backend sobre el estado del agente.

        Envia un POST con metricas y estado de la conexion
        AMI. 401/403 indican que el agente fue revocado.

        Args:
            estado_ami: Estado actual de la conexion AMI.

        Returns:
            True si el backend respondio correctamente.
        """
        if self.cliente is None:
            return True

        try:
            # Obtener configuracion para construir URL del heartbeat
            from src.core.config import ConfiguracionAgente
            config = ConfiguracionAgente.obtener_instancia()
            url_heartbeat = f"{config.backend.url}/api/v1/agent/heartbeat"

            # Cabeceras HTTP incluyendo identificador del agente
            cabeceras = {
                "Content-Type": "application/json",
                "X-Agent-ID": self.contexto.agente_id,
            }

            # Recolectar metricas del sistema via psutil
            try:
                from src.health.self_monitor import AutoMonitor
                sistema = AutoMonitor.recolectar_metricas_sistema()
            except Exception:
                sistema = {}

            # Datos del heartbeat: estado, metricas, conexion AMI, sistema
            datos = {
                "agente_id": self.contexto.agente_id,
                "pbx_id": self.contexto.pbx_id,
                "estado": self.contexto.estado.value,
                "tiempo_activo": self.contexto.tiempo_activo(),
                "active_calls": self.contexto.metricas.llamadas_activas,
                "conexion_ami": estado_ami,
                "metricas": {
                    "eventos_procesados": self.contexto.metricas.eventos_procesados,
                    "eventos_transmitidos": self.contexto.metricas.eventos_transmitidos,
                    "eventos_encolados": self.contexto.metricas.eventos_encolados,
                },
                "sistema": sistema,
            }

            # Serializar datos a JSON para el cuerpo de la peticion
            import json
            payload = json.dumps(datos, default=str)

            # Enviar peticion POST al endpoint de heartbeat
            return await self.cliente.enviar_peticion(
                metodo="POST",
                url=url_heartbeat,
                datos=payload,
                cabeceras=cabeceras,
                timeout=10.0,
            )

        except Exception as error:
            self.logger.error(
                "Error notificando heartbeat al backend",
                contexto={"error": str(error)}
            )
            return False
