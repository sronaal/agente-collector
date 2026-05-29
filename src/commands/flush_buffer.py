"""Comando que vacia el buffer offline y sincroniza con el backend.

Lee los eventos almacenados en el buffer SQLite y los
transmite al backend usando la estrategia de transmision
configurada. Implementa idempotencia para evitar duplicados.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from typing import Any, Optional

# Interfaz base para el patron Command
from src.commands.base import ComandoBase
# Contexto de ejecucion singleton para metricas
from src.core.contexto import ContextoEjecucion
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado


class ComandoVaciarBuffer(ComandoBase):
    """Comando que sincroniza el buffer local con el backend.

    Lee lotes de eventos del buffer SQLite y los transmite
    usando la estrategia configurada. Solo elimina del buffer
    aquellos eventos que reciben confirmacion (ACK) del backend.

    Args:
        almacen_buffer: Instancia del almacen SQLite.
        estrategia_transmision: Estrategia para enviar eventos.
        gestor_colas: Gestor de colas para re-encolar fallidos.
        tamano_lote: Cantidad de eventos a enviar por lote.
    """

    def __init__(
        self,
        almacen_buffer: Any,
        estrategia_transmision: Any,
        gestor_colas: Any = None,
        tamano_lote: int = 50,
    ) -> None:
        # Referencia al almacen SQLite para leer eventos pendientes
        self.almacen = almacen_buffer
        # Estrategia de transmision (HTTP batch o WebSocket)
        self.estrategia = estrategia_transmision
        # Gestor de colas para re-encolar eventos si falla la transmision
        self.gestor_colas = gestor_colas
        # Cantidad de eventos a leer y transmitir por iteracion
        self.tamano_lote = tamano_lote
        # Contexto singleton para actualizar metricas
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def ejecutar(self) -> bool:
        """Ejecuta la sincronizacion del buffer con el backend.

        Itera en lotes. Si un lote falla, detiene la
        sincronizacion y reintenta en el proximo ciclo.

        Returns:
            True si todos los lotes fueron sincronizados.
        """
        try:
            # Consultar cuantos eventos estan pendientes en el buffer
            total_eventos = await self.almacen.contar_pendientes()

            if total_eventos == 0:
                return True

            self.logger.info(
                "Iniciando sincronizacion de buffer",
                contexto={"pendientes": total_eventos}
            )

            # Iterar hasta que no queden mas eventos pendientes
            while True:
                # Obtener siguiente lote de eventos del buffer
                eventos = await self.almacen.obtener_lote(self.tamano_lote)

                if not eventos:
                    break

                # Transmitir el lote completo al backend
                exito = await self.estrategia.transmitir(
                    eventos=eventos,
                    agente_id=self.contexto.agente_id,
                )

                if exito:
                    # Extraer IDs de eventos que se enviaron correctamente
                    ids_exitosos = [e.get("event_id") for e in eventos if e.get("event_id")]
                    # Marcar como enviados en el buffer (no se reenviaran)
                    await self.almacen.marcar_como_enviados(ids_exitosos)
                    # Actualizar contador de eventos transmitidos
                    self.contexto.metricas.eventos_transmitidos += len(ids_exitosos)

                    self.logger.info(
                        "Lote sincronizado",
                        contexto={"cantidad": len(eventos)}
                    )
                else:
                    # Fallo la transmision: detener y reintentar en el proximo ciclo
                    self.logger.advertencia(
                        "Fallo sincronizacion de lote, se reintentara despues",
                        contexto={"cantidad": len(eventos)}
                    )
                    return False

            return True

        except Exception as error:
            self.logger.error(
                "Error al vaciar buffer",
                contexto={"error": str(error)}
            )
            return False
