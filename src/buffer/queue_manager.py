"""Gestor de colas con soporte para backpressure y buffer offline.

Administra una cola interna de eventos pendientes y decide
si transmitirlos inmediatamente o almacenarlos en el buffer
SQLite segun la disponibilidad de la red.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para manejo de tareas asincronas y colas (asyncio.Queue)
import asyncio
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, List, Optional

# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado


class GestorColas:
    """Gestiona la cola de eventos y decide su ruta de salida.

    Mantiene una cola asincrona de eventos normalizados.
    Cuando hay conexion con el backend, los transmite
    inmediatamente. Cuando no, los almacena en el buffer
    SQLite para transmision posterior.

    Args:
        almacen_buffer: Instancia de AlmacenSQLite para persistencia.
        estrategia_transmision: Estrategia para enviar eventos online.
        tamano_maximo_cola: Maximo de eventos en cola antes de backpressure.
        intervalo_flush: Segundos entre intentos de vaciar buffer.
    """

    def __init__(
        self,
        almacen_buffer: Any,
        estrategia_transmision: Any = None,
        tamano_maximo_cola: int = 1000,
        intervalo_flush: int = 60,
    ) -> None:
        # Referencia al almacen SQLite para buffer offline
        self.almacen = almacen_buffer
        # Estrategia de transmision (HTTP batch o WebSocket realtime)
        self.estrategia = estrategia_transmision
        # Capacidad maxima de la cola en memoria (backpressure threshold)
        self.tamano_maximo = tamano_maximo_cola
        # Intervalo en segundos entre intentos de vaciar buffer SQLite
        self.intervalo_flush = intervalo_flush
        # Cola asincrona acotada: si se llena, backpressure redirige a buffer
        self._cola: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(
            maxsize=tamano_maximo_cola
        )
        # Bandera de actividad del gestor
        self._activo = False
        # Tarea asincrona del bucle de procesamiento
        self._tarea_procesamiento: Optional[asyncio.Task] = None
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def iniciar(self) -> None:
        """Inicia el procesamiento continuo de la cola.

        Crea una tarea asincrona que procesa los eventos
        de la cola en segundo plano.
        """
        # Marcar como activo antes de crear la tarea
        self._activo = True
        # Crear tarea asincrona que ejecuta el bucle de procesamiento
        self._tarea_procesamiento = asyncio.create_task(self._procesar_cola())
        self.logger.info("Gestor de colas iniciado")

    async def detener(self) -> None:
        """Detiene el procesamiento de la cola de forma segura.

        Cancela la tarea y el bucle de procesamiento ejecuta
        un vaciado final al recibir CancelledError.
        """
        # Marcar como inactivo para que el bucle termine
        self._activo = False

        # Cancelar la tarea de procesamiento si existe
        if self._tarea_procesamiento is not None:
            self._tarea_procesamiento.cancel()
            try:
                await self._tarea_procesamiento
            except asyncio.CancelledError:
                pass

        self.logger.info("Gestor de colas detenido")

    async def encolar(self, evento: Dict[str, Any]) -> bool:
        """Encola un evento para su procesamiento.

        Si la cola esta llena (backpressure), almacena
        directamente en el buffer SQLite para evitar
        bloqueos en el pipeline.

        Args:
            evento: Evento normalizado a encolar.

        Returns:
            True si se encolo exitosamente.
        """
        try:
            # Verificar si la cola alcanzo su capacidad maxima
            if self._cola.full():
                self.logger.advertencia(
                    "Cola llena, almacenando directamente en buffer",
                    contexto={"event_id": evento.get("event_id")}
                )
                # Backpressure: redirigir directamente al buffer SQLite
                return await self.almacen.guardar(evento)

            # Cola tiene espacio: encolar el evento para procesamiento
            await self._cola.put(evento)
            return True

        except Exception as error:
            self.logger.error(
                "Error al encolar evento",
                contexto={"error": str(error)}
            )
            # Fallback seguro: guardar en buffer SQLite
            return await self.almacen.guardar(evento)

    async def _procesar_cola(self) -> None:
        """Bucle principal que procesa eventos de la cola.

        Lee eventos de la cola con timeout configurable.
        Si no hay eventos durante `intervalo_flush` segundos,
        aprovecha para intentar vaciar el buffer SQLite.
        Al recibir cancelacion, ejecuta un vaciado final.
        """
        while self._activo:
            try:
                # Esperar evento con timeout para verificar _activo periodicamente
                evento = await asyncio.wait_for(
                    self._cola.get(),
                    timeout=self.intervalo_flush
                )
                # Procesar el evento (transmitir o bufferizar)
                await self._procesar_evento(evento)

            except asyncio.TimeoutError:
                # No llegaron eventos en este intervalo
                # Aprovechar para vaciar buffer SQLite si hay conexion
                await self._intentar_vaciar_buffer()

            except asyncio.CancelledError:
                # Tarea cancelada, salir del bucle
                break

            except Exception as error:
                self.logger.error(
                    "Error en procesamiento de cola",
                    contexto={"error": str(error)}
                )

        # Al salir del bucle, guardar eventos restantes en buffer
        await self._vaciado_final()

    async def _procesar_evento(self, evento: Dict[str, Any]) -> None:
        """Procesa un evento individual de la cola.

        Intenta transmitir en tiempo real si hay conexion.
        Si la transmision falla o no hay conexion, redirige
        al buffer offline para envio posterior.

        Args:
            evento: Evento a procesar.
        """
        # Intentar transmision solo si hay estrategia configurada y conexion
        if self.estrategia is not None and self._hay_conexion():
            try:
                exito = await self.estrategia.transmitir(
                    eventos=[evento],
                    agente_id=evento.get("agente_id", ""),
                )
                if exito:
                    # Incrementar contador de eventos transmitidos
                    from src.core.contexto import ContextoEjecucion
                    ctx = ContextoEjecucion.obtener_instancia()
                    ctx.metricas.eventos_transmitidos += 1
                    return
            except Exception:
                pass

        # Fallback: almacenar en buffer offline para transmision posterior
        await self.almacen.guardar(evento)

    def _hay_conexion(self) -> bool:
        """Verifica si hay conexion activa con el backend.

        Returns:
            True si el agente esta en estado ACTIVO.
        """
        from src.core.contexto import ContextoEjecucion, EstadoAgente
        ctx = ContextoEjecucion.obtener_instancia()
        # Solo transmitir si el agente esta en estado ACTIVO
        return ctx.estado == EstadoAgente.ACTIVO

    async def _intentar_vaciar_buffer(self) -> None:
        """Intenta vaciar el buffer SQLite cuando hay eventos pendientes y conexion."""
        try:
            # Consultar cantidad de eventos pendientes en buffer
            pendientes = await self.almacen.contar_pendientes()
            # Solo vaciar si hay pendientes y hay conexion con el backend
            if pendientes > 0 and self._hay_conexion():
                from src.commands.flush_buffer import ComandoVaciarBuffer
                # Crear comando para sincronizar buffer con backend
                comando = ComandoVaciarBuffer(
                    almacen_buffer=self.almacen,
                    estrategia_transmision=self.estrategia,
                    gestor_colas=self,
                    tamano_lote=50,
                )
                await comando.ejecutar()
        except Exception as error:
            self.logger.error(
                "Error al vaciar buffer",
                contexto={"error": str(error)}
            )

    async def _vaciado_final(self) -> None:
        """Vacia la cola al detener el gestor.

        Garantiza que ningun evento en memoria se pierda
        cuando el agente se detiene. Todos los eventos
        pendientes se guardan en el buffer SQLite.
        """
        while not self._cola.empty():
            try:
                # Obtener evento sin esperar (non-blocking)
                evento = self._cola.get_nowait()
                # Guardar directamente en buffer offline
                await self.almacen.guardar(evento)
            except asyncio.QueueEmpty:
                break
