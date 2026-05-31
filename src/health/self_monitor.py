"""Modulo de auto-monitoreo del agente.

Recolecta metricas internas del agente como uso de CPU,
memoria RAM, tamanio de cola y buffer, y las registra
en el log para diagnostico.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para tareas asincronas (creacion y cancelacion de Tasks)
import asyncio
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Contexto de ejecucion singleton con estado y metricas
from src.core.contexto import ContextoEjecucion
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado


class AutoMonitor:
    """Recolecta y registra metricas internas del agente.

    Monitorea el rendimiento del agente: eventos procesados,
    estado de la cola, buffer, errores de conexion y
    metricas del sistema (CPU, RAM).

    Args:
        intervalo: Segundos entre recolecciones de metricas.
        almacen_buffer: Referencia al buffer para consultar tamanio.
        gestor_colas: Referencia al gestor de colas.
    """

    def __init__(
        self,
        intervalo: int = 60,
        almacen_buffer: Any = None,
        gestor_colas: Any = None,
    ) -> None:
        # Intervalo en segundos entre recolecciones de metricas
        self.intervalo = intervalo
        # Referencia al almacen SQLite para consultar pendientes
        self.almacen = almacen_buffer
        # Referencia al gestor de colas (no usado actualmente)
        self.gestor_colas = gestor_colas
        # Contexto singleton con metricas del agente
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()
        # Tarea asincrona del bucle (None hasta iniciar())
        self._tarea: Optional[asyncio.Task] = None
        # Bandera de actividad del monitoreo
        self._activo = False

    async def iniciar(self) -> None:
        """Inicia la recoleccion periodica de metricas."""
        self._activo = True
        self._tarea = asyncio.create_task(self._bucle_metricas())
        self.logger.info(
            "Auto-monitoreo iniciado",
            contexto={"intervalo": self.intervalo}
        )

    async def detener(self) -> None:
        """Detiene la recoleccion de metricas."""
        self._activo = False
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except asyncio.CancelledError:
                pass

    async def _bucle_metricas(self) -> None:
        """Bucle que recolecta metricas en intervalos regulares."""
        while self._activo:
            try:
                # Recolectar y registrar metricas actuales
                await self._recolectar_metricas()
                await asyncio.sleep(self.intervalo)

            except asyncio.CancelledError:
                break

            except Exception as error:
                self.logger.error(
                    "Error recolectando metricas",
                    contexto={"error": str(error)}
                )
                await asyncio.sleep(self.intervalo)

    @staticmethod
    def recolectar_metricas_sistema() -> Dict[str, Any]:
        """Recolecta metricas del sistema (CPU, RAM, disco, red).

        Metodo estatico reutilizable desde el heartbeat y el
        auto-monitoreo. Retorna 0.0 si psutil no esta disponible.

        Returns:
            Diccionario con metricas del sistema.
        """
        try:
            import psutil
            import socket
            proceso = psutil.Process()
            disco = psutil.disk_usage('/')
            interfaces = []
            for nombre, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        interfaces.append({
                            "nombre": nombre,
                            "ip": addr.address,
                            "mascara": addr.netmask,
                        })
            hostname = socket.gethostname()
            ip_servidor = socket.gethostbyname(hostname)
            return {
                "cpu_porcentaje": psutil.cpu_percent(interval=0.3),
                "ram_mb": round(psutil.virtual_memory().used / 1024 / 1024, 1),
                "ram_porcentaje": psutil.virtual_memory().percent,
                "disco_porcentaje": disco.percent,
                "disco_total_gb": round(disco.total / 1024 / 1024 / 1024, 1),
                "disco_usado_gb": round(disco.used / 1024 / 1024 / 1024, 1),
                "proceso_cpu": proceso.cpu_percent(),
                "proceso_ram_mb": round(proceso.memory_info().rss / 1024 / 1024, 1),
                "hostname": hostname,
                "ip_servidor": ip_servidor,
                "interfaces_red": interfaces,
            }
        except ImportError:
            return {
                "cpu_porcentaje": 0.0,
                "ram_mb": 0.0,
                "ram_porcentaje": 0.0,
                "disco_porcentaje": 0.0,
                "disco_total_gb": 0.0,
                "disco_usado_gb": 0.0,
                "proceso_cpu": 0.0,
                "proceso_ram_mb": 0.0,
                "hostname": "",
                "ip_servidor": "",
                "interfaces_red": [],
            }

    async def _recolectar_metricas(self) -> Dict[str, Any]:
        """Recolecta todas las metricas disponibles del agente.

        Returns:
            Diccionario con las metricas recolectadas.
        """
        # Metricas base del contexto de ejecucion
        metricas = {
            "estado": self.contexto.estado.value,
            "tiempo_activo": f"{self.contexto.tiempo_activo():.0f}s",
            "eventos_procesados": self.contexto.metricas.eventos_procesados,
            "eventos_transmitidos": self.contexto.metricas.eventos_transmitidos,
            "eventos_encolados": self.contexto.metricas.eventos_encolados,
            "eventos_perdidos": self.contexto.metricas.eventos_perdidos,
            "errores_conexion": self.contexto.metricas.errores_conexion,
        }

        # Agregar cantidad de eventos pendientes en buffer SQLite
        if self.almacen is not None:
            try:
                pendientes = await self.almacen.contar_pendientes()
                metricas["buffer_pendientes"] = pendientes
            except Exception:
                metricas["buffer_pendientes"] = -1

        # Metricas del sistema via metodo estatico reutilizable
        metricas.update(self.recolectar_metricas_sistema())

        # Registrar todas las metricas en una sola linea JSON
        self.logger.info(
            "Metricas del agente",
            contexto=metricas
        )

        return metricas
