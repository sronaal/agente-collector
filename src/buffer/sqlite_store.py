"""Almacen persistente usando SQLite asincrono (aiosqlite).

Implementa el buffer offline del agente: almacena eventos
localmente cuando no hay conexion con el backend y los
recupera cuando la conexion se restablece.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Serializacion de diccionarios a JSON para almacenar en SQLite
import json
# Acceso a row_factory para consultas por nombre de columna
import sqlite3
# Manejo de rutas de archivos del sistema operativo
from pathlib import Path
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, List, Optional

# Logger estructurado para registro de eventos
from src.core.logger import LoggerEstructurado


class AlmacenSQLite:
    """Almacen persistente basado en SQLite para buffer offline.

    Guarda eventos normalizados en una base de datos SQLite
    local. Cada evento tiene un estado (pendiente, enviado)
    y se marca como enviado solo tras confirmacion del backend.

    Args:
        ruta_base: Ruta al archivo de base de datos SQLite.
        tamano_maximo: Numero maximo de eventos en el buffer.
    """

    def __init__(
        self,
        ruta_base: str = "/tmp/callmetric/buffer.db",
        tamano_maximo: int = 10000,
    ) -> None:
        # Ruta completa al archivo de base de datos SQLite
        self.ruta = ruta_base
        # Numero maximo de eventos permitidos en el buffer
        self.tamano_maximo = tamano_maximo
        # Conexion asincrona a SQLite (None hasta inicializar())
        self._conexion: Optional[Any] = None
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def inicializar(self) -> None:
        """Inicializa la base de datos y crea tablas si no existen.

        Crea el directorio padre si es necesario y establece
        la conexion asincrona con SQLite.
        """
        # Convertir la ruta string a objeto Path para manipular
        ruta_archivo = Path(self.ruta)
        # Crear el directorio padre si no existe (mkdir -p)
        ruta_archivo.parent.mkdir(parents=True, exist_ok=True)

        # Importar aiosqlite (dependencia externa)
        import aiosqlite
        # Establecer conexion asincrona con la base de datos
        self._conexion = await aiosqlite.connect(str(ruta_archivo))
        # Configurar row_factory para acceso por nombre de columna
        self._conexion.row_factory = sqlite3.Row

        # Crear tabla de eventos si no existe (esquema fijo)
        await self._conexion.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                tipo TEXT NOT NULL,
                datos TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                creado_en REAL NOT NULL,
                enviado_en REAL
            )
        """)

        # Crear indice sobre el campo estado para consultas rapidas
        await self._conexion.execute("""
            CREATE INDEX IF NOT EXISTS idx_eventos_estado
            ON eventos(estado)
        """)

        # Confirmar los cambios (commmit automatico de SQLite)
        await self._conexion.commit()
        # Registrar que el buffer se inicializo correctamente
        self.logger.info(
            "Buffer SQLite inicializado",
            contexto={"ruta": self.ruta}
        )

    async def guardar(self, evento: Dict[str, Any]) -> bool:
        """Guarda un evento en el buffer.

        Si el buffer esta lleno, elimina los eventos mas
        antiguos antes de insertar el nuevo.

        Args:
            evento: Diccionario con el evento normalizado.

        Returns:
            True si se guardo exitosamente.
        """
        # Verificar que la conexion este inicializada
        if self._conexion is None:
            self.logger.error("Buffer no inicializado")
            return False

        try:
            # Verificar si el buffer alcanzo su capacidad maxima
            total = await self.contar_pendientes()
            if total >= self.tamano_maximo:
                self.logger.advertencia(
                    "Buffer lleno, eliminando eventos mas antiguos",
                    contexto={"total": total, "maximo": self.tamano_maximo}
                )
                # Eliminar los eventos mas antiguos para hacer espacio
                await self._eliminar_mas_antiguos()

            # Importar time para obtener timestamp de creacion
            import time
            # Insertar o reemplazar el evento en la tabla
            await self._conexion.execute(
                """
                INSERT OR REPLACE INTO eventos
                    (event_id, timestamp, tipo, datos, estado, creado_en)
                VALUES (?, ?, ?, ?, 'pendiente', ?)
                """,
                (
                    evento.get("event_id", ""),
                    evento.get("timestamp", ""),
                    evento.get("tipo", ""),
                    # Serializar el evento completo a JSON para almacenamiento
                    json.dumps(evento, ensure_ascii=False, default=str),
                    # Timestamp Unix del momento de insercion
                    time.time(),
                )
            )
            # Confirmar la insercion en la base de datos
            await self._conexion.commit()
            return True

        except Exception as error:
            # Loggear el error con contexto del evento fallido
            self.logger.error(
                "Error guardando evento en buffer",
                contexto={"error": str(error), "event_id": evento.get("event_id")}
            )
            return False

    async def obtener_lote(self, cantidad: int = 50) -> List[Dict[str, Any]]:
        """Obtiene un lote de eventos pendientes para transmision.

        Los eventos se ordenan por antiguedad (FIFO) para
        garantizar que los mas antiguos se envien primero.

        Args:
            cantidad: Numero maximo de eventos a obtener.

        Returns:
            Lista de eventos pendientes como diccionarios.
        """
        # Verificar que la conexion este inicializada
        if self._conexion is None:
            return []

        try:
            # Consultar eventos pendientes ordenados por creacion (FIFO)
            cursor = await self._conexion.execute(
                """
                SELECT event_id, timestamp, tipo, datos
                FROM eventos
                WHERE estado = 'pendiente'
                ORDER BY creado_en ASC
                LIMIT ?
                """,
                (cantidad,)
            )
            # Obtener todas las filas del resultado
            filas = await cursor.fetchall()

            # Deserializar cada fila de JSON a diccionario Python
            eventos = []
            for fila in filas:
                evento = json.loads(fila["datos"])
                eventos.append(evento)

            return eventos

        except Exception as error:
            # Loggear error en la consulta
            self.logger.error(
                "Error obteniendo lote del buffer",
                contexto={"error": str(error)}
            )
            return []

    async def marcar_como_enviados(self, ids_eventos: List[str]) -> None:
        """Marca una lista de eventos como enviados (ACK del backend).

        Args:
            ids_eventos: Lista de event_id a marcar como enviados.
        """
        # Verificar que hay conexion y lista de IDs a marcar
        if self._conexion is None or not ids_eventos:
            return

        try:
            # Obtener timestamp actual para el campo enviado_en
            import time
            ahora = time.time()

            # Marcar cada evento individualmente para evitar inyeccion SQL
            for event_id in ids_eventos:
                await self._conexion.execute(
                    """
                    UPDATE eventos
                    SET estado = 'enviado', enviado_en = ?
                    WHERE event_id = ?
                    """,
                    (ahora, event_id)
                )

            # Confirmar todas las actualizaciones
            await self._conexion.commit()

        except Exception as error:
            self.logger.error(
                "Error marcando eventos como enviados",
                contexto={"error": str(error)}
            )

    async def contar_pendientes(self) -> int:
        """Cuenta los eventos pendientes de transmision.

        Returns:
            Numero de eventos en estado 'pendiente'.
        """
        # Verificar que la conexion este inicializada
        if self._conexion is None:
            return 0

        try:
            # Consultar el total de eventos pendientes
            cursor = await self._conexion.execute(
                "SELECT COUNT(*) as total FROM eventos WHERE estado = 'pendiente'"
            )
            fila = await cursor.fetchone()
            # Retornar el total o 0 si no hay resultados
            return fila["total"] if fila else 0

        except Exception:
            # En caso de error, retornar 0 para no interrumpir el flujo
            return 0

    async def limpiar_enviados(self, max_dias: int = 7) -> int:
        """Elimina eventos enviados mas antiguos que max_dias.

        Tarea de mantenimiento para evitar que el buffer
        crezca indefinidamente con datos historicos.

        Args:
            max_dias: Antiguedad maxima en dias antes de eliminar.

        Returns:
            Numero de eventos eliminados.
        """
        # Verificar que la conexion este inicializada
        if self._conexion is None:
            return 0

        try:
            import time
            # Calcular timestamp de corte (now - max_dias en segundos)
            corte = time.time() - (max_dias * 86400)

            # Eliminar eventos enviados cuyo enviado_en sea anterior al corte
            cursor = await self._conexion.execute(
                "DELETE FROM eventos WHERE estado = 'enviado' AND enviado_en < ?",
                (corte,)
            )
            await self._conexion.commit()
            # Retornar cantidad de filas eliminadas
            return cursor.rowcount

        except Exception as error:
            self.logger.error(
                "Error limpiando buffer",
                contexto={"error": str(error)}
            )
            return 0

    async def cerrar(self) -> None:
        """Cierra la conexion con la base de datos."""
        # Solo cerrar si hay una conexion activa
        if self._conexion is not None:
            # Cerrar la conexion asincrona
            await self._conexion.close()
            # Marcar la conexion como nula
            self._conexion = None
            self.logger.info("Buffer SQLite cerrado")

    async def _eliminar_mas_antiguos(self) -> None:
        """Elimina los eventos mas antiguos cuando el buffer esta lleno.

        Estrategia FIFO: borra los eventos pendientes mas viejos
        hasta liberar espacio (100 slots por debajo del maximo).
        """
        # Verificar que la conexion este inicializada
        if self._conexion is None:
            return

        try:
            # Calcular cuantos eventos exceden el limite (mas 100 de margen)
            exceso = (await self.contar_pendientes()) - self.tamano_maximo + 100
            if exceso > 0:
                # Eliminar los eventos pendientes mas antiguos
                await self._conexion.execute(
                    """
                    DELETE FROM eventos
                    WHERE event_id IN (
                        SELECT event_id FROM eventos
                        WHERE estado = 'pendiente'
                        ORDER BY creado_en ASC
                        LIMIT ?
                    )
                    """,
                    (exceso,)
                )
                await self._conexion.commit()
        except Exception as error:
            self.logger.error(
                "Error eliminando eventos antiguos",
                contexto={"error": str(error)}
            )
