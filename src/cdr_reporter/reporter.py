"""Modulo ReporterCDR - consulta la base MySQL de Asterisk y envia
reportes historicos CDR al backend de CallMetric.

Se conecta a la base de datos asteriskcdrdb donde residen las vistas
SQL de reportes (vw_llamadas_normalizadas, vw_colas_estadisticas, etc.)
y las envia periodicamente via HTTP al backend.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional

import aiomysql

from src.core.config import ConfiguracionAgente
from src.core.contexto import ContextoEjecucion
from src.core.logger import LoggerEstructurado
from src.transmitters.http_client import ClienteHTTP
from src.cdr_reporter import queries


class ReporterCDR:
    """Consultor de vistas CDR en MySQL de Asterisk.

    Se ejecuta como tarea asincrona periodica. Cada INTERVALO_CDR
    consulta las 5 vistas y envia los datos al backend via REST.

    Args:
        config: Configuracion del agente (con .cdr.*).
        cliente_http: Cliente HTTP para enviar datos al backend.
        contexto: Contexto de ejecucion del agente.
    """

    def __init__(
        self,
        config: ConfiguracionAgente,
        cliente_http: ClienteHTTP,
        contexto: ContextoEjecucion,
    ) -> None:
        self.config = config
        self.cliente_http = cliente_http
        self.contexto = contexto
        self.logger = LoggerEstructurado.obtener_instancia()

        self._pool: Optional[aiomysql.Pool] = None
        self._tarea: Optional[asyncio.Task] = None
        self._activo = False
        self._ultima_consulta: Optional[str] = None
        self._url_cdr = f"{config.backend.url}/api/v1/agent/cdr"

    async def iniciar(self) -> None:
        """Crea el pool MySQL e inicia el bucle de reportes."""
        if not self.config.cdr.activo:
            self.logger.info("Reporter CDR desactivado (CDR_REPORT_ACTIVE=false)")
            return

        try:
            self._pool = await aiomysql.create_pool(
                host=self.config.cdr.db_host,
                port=self.config.cdr.db_port,
                db=self.config.cdr.db_name,
                user=self.config.cdr.db_user,
                password=self.config.cdr.db_password,
                autocommit=True,
                maxsize=2,
            )
            self.logger.info(
                "Reporter CDR conectado a MySQL",
                contexto={
                    "host": self.config.cdr.db_host,
                    "db": self.config.cdr.db_name,
                },
            )
        except Exception as error:
            self.logger.error(
                "Error conectando a MySQL para CDR",
                contexto={"error": str(error)},
            )
            return

        self._activo = True
        self._tarea = asyncio.create_task(self._bucle_reporte())
        self.logger.info(
            "Reporter CDR iniciado",
            contexto={"intervalo": self.config.cdr.intervalo_reporte},
        )

    async def _bucle_reporte(self) -> None:
        """Bucle principal: consulta vistas y envia al backend."""
        while self._activo:
            try:
                await self._ejecutar_reporte()
            except asyncio.CancelledError:
                break
            except Exception as error:
                self.logger.error(
                    "Error en ciclo de reporte CDR",
                    contexto={"error": str(error)},
                )
            await asyncio.sleep(self.config.cdr.intervalo_reporte)

    async def _ejecutar_reporte(self) -> None:
        """Consulta las 5 vistas y envia el payload al backend."""
        if self._pool is None:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                # Parametro de filtro incremental
                desde = self._ultima_consulta or (
                    datetime.now().strftime("%Y-%m-%d 00:00:00")
                )

                try:
                    await cursor.execute(queries.QUERY_LLAMADAS_NORMALIZADAS, (desde,))
                    llamadas = await cursor.fetchall()
                except Exception:
                    llamadas = []

                try:
                    await cursor.execute(queries.QUERY_COLAS_RESUMEN)
                    colas_resumen = await cursor.fetchall()
                except Exception:
                    colas_resumen = []

                try:
                    await cursor.execute(queries.QUERY_AGENTES_RESUMEN)
                    agentes_resumen = await cursor.fetchall()
                except Exception:
                    agentes_resumen = []

                try:
                    await cursor.execute(queries.QUERY_ESTADISTICAS_COLAS, (desde,))
                    est_colas = await cursor.fetchall()
                except Exception:
                    est_colas = []

                try:
                    await cursor.execute(queries.QUERY_LLAMADAS_REAL, (desde,))
                    llamadas_real = await cursor.fetchall()
                except Exception:
                    llamadas_real = []

        self._ultima_consulta = timestamp

        payload = {
            "agenteId": self.contexto.agente_id,
            "timestamp": timestamp,
            "empresaId": self.contexto.empresa_id,
            "ultimaConsulta": desde,
            "datos": {
                "llamadasNormalizadas": self._serializar(llamadas),
                "colasResumen": self._serializar(colas_resumen),
                "agentesResumen": self._serializar(agentes_resumen),
                "estadisticasColas": self._serializar(est_colas),
                "llamadasReal": self._serializar(llamadas_real),
            },
        }

        total = (
            len(llamadas) + len(colas_resumen) + len(agentes_resumen)
            + len(est_colas) + len(llamadas_real)
        )
        if total == 0:
            return

        exito = await self.cliente_http.enviar_peticion(
            metodo="POST",
            url=self._url_cdr,
            datos=json.dumps(payload, ensure_ascii=False, default=str),
            cabeceras={
                "Content-Type": "application/json",
                "X-Agent-ID": self.contexto.agente_id,
            },
        )

        if exito:
            self.logger.info(
                "Reporte CDR enviado",
                contexto={
                    "llamadas": len(llamadas),
                    "colas": len(colas_resumen),
                    "agentes": len(agentes_resumen),
                    "est_colas": len(est_colas),
                    "llamadas_real": len(llamadas_real),
                },
            )

    def _serializar(self, filas: Any) -> list:
        """Convierte filas MySQL a lista de dicts serializable."""
        if not filas:
            return []
        result = []
        for fila in filas:
            if isinstance(fila, dict):
                item = {}
                for k, v in fila.items():
                    if isinstance(v, (datetime, time.struct_time)):
                        item[k] = v.isoformat() if hasattr(v, 'isoformat') else str(v)
                    elif isinstance(v, (int, float, str, bool)):
                        item[k] = v
                    elif v is None:
                        item[k] = None
                    else:
                        item[k] = str(v)
                result.append(item)
            elif isinstance(fila, (list, tuple)):
                result.append([str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v for v in fila])
            else:
                result.append(str(fila))
        return result

    async def detener(self) -> None:
        """Detiene el bucle y cierra el pool MySQL."""
        self._activo = False
        if self._tarea is not None:
            self._tarea.cancel()
            try:
                await self._tarea
            except (asyncio.CancelledError, Exception):
                pass
            self._tarea = None
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
        self.logger.info("Reporter CDR detenido")
