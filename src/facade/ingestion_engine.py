"""Implementacion del patron Facade: IngestionEngine.

Orquesta todos los componentes del agente exponiendo
una API simple con los metodos iniciar, detener y estado.
Oculta la complejidad interna de conectores, estrategias,
comandos y buffer.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para manejo de tareas asincronas (asyncio.Task, CancelledError)
import asyncio
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Gestor de colas con backpressure y buffer offline
from src.buffer.queue_manager import GestorColas
# Almacen SQLite para buffer offline
from src.buffer.sqlite_store import AlmacenSQLite
# Comando para sincronizar buffer con backend
from src.commands.flush_buffer import ComandoVaciarBuffer
# Comando para normalizar y encolar eventos del stream
from src.commands.process_event import ComandoProcesarEvento
# Comando para enviar heartbeat al backend
from src.commands.send_heartbeat import ComandoEnviarHeartbeat
# Conector AMI para capturar eventos de Asterisk
from src.connectors.ami_connector import ConectorAMI
# Configuracion singleton del agente
from src.core.config import ConfiguracionAgente
# Contexto de ejecucion singleton y estados del agente
from src.core.contexto import ContextoEjecucion, EstadoAgente
# Logger estructurado singleton
from src.core.logger import LoggerEstructurado
# Fabrica de conectores (Factory Method pattern)
from src.factories.event_source_factory import FabricaFuenteEventos
# Gestor de heartbeat periodico
from src.health.heartbeat import HeartbeatManager
# Auto-monitoreo de metricas del agente
from src.health.self_monitor import AutoMonitor
# Iterador asincrono sobre eventos AMI
from src.iterators.ami_stream import StreamAMI
# Estrategia de normalizacion de eventos AMI
from src.strategies.normalization import NormalizadorAMI, NormalizadorQueue, NormalizadorCDR, NormalizadorSIP, NormalizadorLogSIP
# Estrategias de transmision HTTP y WebSocket
from src.strategies.transmission import EstrategiaHTTPBatch, EstrategiaWSRealtime
# Cliente HTTP asincrono con reintentos
from src.transmitters.http_client import ClienteHTTP
# Cliente WebSocket asincrono con reconexion
from src.transmitters.ws_client import ClienteWebSocket
# Reporter de CDR historicos desde MySQL de Asterisk
from src.cdr_reporter import ReporterCDR


class MotorIngestion:
    """Fachada principal que orquesta todos los componentes del agente.

    Expone una API simple (iniciar, detener, estado) que
    oculta la complejidad de la arquitectura interna de
    conectores, estrategias, comandos y buffer.

    Uso:
        motor = MotorIngestion()
        await motor.iniciar()
        await motor.detener()

    Args:
        config: Configuracion del agente (opcional, usa singleton por defecto).
    """

    def __init__(
        self,
        config: Optional[ConfiguracionAgente] = None,
    ) -> None:
        # Usar configuracion proporcionada o la singleton por defecto
        self.config = config or ConfiguracionAgente.obtener_instancia()
        # Contexto de ejecucion singleton (estado, metricas)
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Logger estructurado singleton
        self.logger = LoggerEstructurado.obtener_instancia()

        # Fabrica para crear conectores segun el tipo de fuente
        self.fabrica = FabricaFuenteEventos()
        # Conector AMI (None hasta iniciar())
        self.conector: Optional[ConectorAMI] = None
        # Stream iterador sobre eventos del conector
        self.stream: Optional[StreamAMI] = None
        # Normalizador que consolida llamadas parciales en registros completos
        self.normalizador = NormalizadorAMI()
        # Normalizador de eventos Queue (call center)
        self.normalizador_queue = NormalizadorQueue()
        # Normalizador de eventos CDR
        self.normalizador_cdr = NormalizadorCDR()
        # Normalizador de eventos SIP (PeerStatus, Registry)
        self.normalizador_sip = NormalizadorSIP()
        # Normalizador de logs SIP para logs_sip
        self.normalizador_log_sip = NormalizadorLogSIP()
        # Almacen SQLite para buffer offline de eventos
        self.almacen = AlmacenSQLite(
            ruta_base=self.config.buffer.ruta,
            tamano_maximo=self.config.buffer.tamano_maximo,
        )
        # MVP: TLS deshabilitado para desarrollo local sin certificados
        self.cliente_http = ClienteHTTP(
            verificar_tls=False,
        )
        # Cliente WebSocket para transmision en tiempo real
        self.cliente_ws = ClienteWebSocket()
        # Estrategia HTTP batch para envio por lotes
        self.estrategia_http = EstrategiaHTTPBatch(
            cliente_http=self.cliente_http,
            url_destino=f"{self.config.backend.url}/api/v1/agent/events",
        )
        # Estrategia WebSocket para eventos en tiempo real
        self.estrategia_ws = EstrategiaWSRealtime(
            cliente_ws=self.cliente_ws,
            url_destino=f"{self.config.backend.url}/ws/agent/realtime",
        )
        # Gestor de colas que decide entre transmision online o buffer offline
        self.gestor_colas = GestorColas(
            almacen_buffer=self.almacen,
            estrategia_transmision=self.estrategia_http,
            intervalo_flush=self.config.buffer.intervalo_flush,
        )

        # Dependencia circular: heartbeat necesita el CallManager del conector
        # pero el conector aun no existe. Se asigna en iniciar() tras crearlo.
        comando_heartbeat = ComandoEnviarHeartbeat(
            gestor_llamadas=None,
            cliente_http=self.cliente_http,
            intervalo=self.config.intervalo_heartbeat,
        )
        # Gestor que ejecuta el heartbeat en un bucle periodico
        self.heartbeat = HeartbeatManager(
            comando_heartbeat=comando_heartbeat,
            intervalo=self.config.intervalo_heartbeat,
        )
        # Reporter de CDR historicos (desde MySQL de Asterisk)
        if self.config.cdr.activo:
            self.reporter_cdr = ReporterCDR(
                config=self.config,
                cliente_http=self.cliente_http,
                contexto=self.contexto,
            )
        else:
            self.reporter_cdr = None

        # Monitor que recolecta metricas internas del agente
        self.auto_monitor = AutoMonitor(
            almacen_buffer=self.almacen,
            gestor_colas=self.gestor_colas,
        )

        # Tarea asincrona del bucle de procesamiento (None hasta iniciar())
        self._tarea_procesamiento: Optional[asyncio.Task] = None

    async def iniciar(self) -> None:
        """Inicia todos los componentes del agente.

        El orden importa:
        1. Buffer y HTTP primero (dependencias base)
        2. Conector AMI (fuente de eventos)
        3. Stream y cola (pipeline)
        4. Heartbeat y monitoreo (solo cuando todo lo demas funciona)
        """
        self.logger.info("Iniciando motor de ingestion...")

        # Inicializar contexto con identificador del agente y host de PBX
        self.contexto.inicializar(
            agente_id=self.config.agente_id,
            pbx_host=self.config.ami.host,
        )

        # Paso 1: Inicializar almacenamiento SQLite y cliente HTTP
        await self.almacen.inicializar()
        await self.cliente_http.iniciar()

        # Paso 2: Crear conector AMI via Factory Method y conectar a Asterisk
        self.conector = await self.fabrica.crear_conector(
            tipo_fuente="ami",
            host=self.config.ami.host,
            puerto=self.config.ami.puerto,
            usuario=self.config.ami.usuario,
            secreto=self.config.ami.secreto,
            timeout_accion=self.config.ami.timeout_accion,
        )
        await self.conector.conectar()

        # Paso 3: Inicializar pipeline de procesamiento (stream + cola)
        self.stream = StreamAMI(fuente_eventos=self.conector)
        await self.gestor_colas.iniciar()

        # Paso 4: Resolver dependencia circular: asignar CallManager al heartbeat
        self.heartbeat.comando.gestor = self.conector.gestor_llamadas

        # Paso 5: Iniciar tareas periodicas de monitoreo
        await self.heartbeat.iniciar()
        await self.auto_monitor.iniciar()
        if self.reporter_cdr is not None:
            await self.reporter_cdr.iniciar()

        # Paso 6: Marcar agente como activo y arrancar bucle de procesamiento
        self.contexto.estado = EstadoAgente.ACTIVO
        self._tarea_procesamiento = asyncio.create_task(
            self._bucle_procesamiento_eventos()
        )

        # Registrar que el motor se inicio correctamente
        self.logger.info(
            "Motor de ingestion iniciado exitosamente",
            contexto={
                "agente_id": self.contexto.agente_id,
                "pbx_host": self.contexto.pbx_host,
            }
        )

    async def detener(self) -> None:
        """Detiene todos los componentes del agente de forma segura.

        Orden inverso al inicio: primero matar tareas activas,
        luego detener pipeline, finalmente cerrar conexiones.
        """
        self.logger.info("Deteniendo motor de ingestion...")
        self.contexto.estado = EstadoAgente.DETENIENDOSE

        # Paso 1: Cancelar bucle de procesamiento de eventos (primero en morir)
        if self._tarea_procesamiento is not None:
            self._tarea_procesamiento.cancel()
            try:
                await self._tarea_procesamiento
            except asyncio.CancelledError:
                pass

        # Paso 2: Detener heartbeat y auto-monitoreo
        await self.heartbeat.detener()
        await self.auto_monitor.detener()
        if self.reporter_cdr is not None:
            await self.reporter_cdr.detener()

        # Paso 3: Detener gestor de colas (vacia pendientes al buffer antes de salir)
        await self.gestor_colas.detener()

        # Paso 4: Desconectar de Asterisk AMI
        if self.conector is not None:
            await self.conector.desconectar()

        # Paso 5: Cerrar clientes de red y buffer SQLite
        await self.cliente_http.cerrar()
        await self.cliente_ws.cerrar()
        await self.almacen.cerrar()

        # Marcar estado final como detenido
        self.contexto.estado = EstadoAgente.DETENIDO
        self.logger.info("Motor de ingestion detenido")

    async def obtener_estado(self) -> Dict[str, Any]:
        """Retorna el estado actual del agente.

        Returns:
            Diccionario con estado, metricas y configuracion.
        """
        # Inicializar contador de buffer pendientes
        buffer_pendientes = 0
        try:
            # Consultar al almacen SQLite cuantos eventos estan pendientes
            buffer_pendientes = await self.almacen.contar_pendientes()
        except Exception:
            pass

        # Construir diccionario completo con estado del agente
        return {
            "estado": self.contexto.estado.value,
            "agente_id": self.contexto.agente_id,
            "pbx_host": self.contexto.pbx_host,
            "tiempo_activo": f"{self.contexto.tiempo_activo():.0f}s",
            "metricas": {
                "eventos_procesados": self.contexto.metricas.eventos_procesados,
                "eventos_transmitidos": self.contexto.metricas.eventos_transmitidos,
                "eventos_encolados": self.contexto.metricas.eventos_encolados,
                "eventos_perdidos": self.contexto.metricas.eventos_perdidos,
                "errores_conexion": self.contexto.metricas.errores_conexion,
            },
            "buffer_pendientes": buffer_pendientes,
        }

    async def _bucle_procesamiento_eventos(self) -> None:
        """Bucle principal que procesa eventos del stream AMI.

        Lee eventos del stream, los normaliza y los encola
        para transmision o almacenamiento offline.
        En caso de perdida de conexion AMI, reintenta
        la reconexion automaticamente.
        """
        self.logger.info("Iniciando procesamiento continuo de eventos")

        while self.contexto.estado not in (EstadoAgente.DETENIENDOSE, EstadoAgente.DETENIDO):
            try:
                async for evento_crudo in self.stream.iterar():
                    tipo = evento_crudo.get("tipo", "")

                    if tipo in NormalizadorQueue.EVENTOS_INMEDIATOS | NormalizadorQueue.EVENTOS_ACUMULABLES:
                        resultado = self.normalizador_queue.normalizar(evento_crudo)
                        if resultado is not None:
                            await self.gestor_colas.encolar(resultado)
                            self.contexto.metricas.eventos_encolados += 1
                        continue

                    if tipo == "Cdr":
                        resultado = self.normalizador_cdr.normalizar(evento_crudo)
                        if resultado is not None:
                            await self.gestor_colas.encolar(resultado)
                            self.contexto.metricas.eventos_encolados += 1
                        continue

                    if tipo in NormalizadorSIP.EVENTOS_SIP:
                        resultado = self.normalizador_sip.normalizar(evento_crudo)
                        if resultado is not None:
                            await self.gestor_colas.encolar(resultado)
                            self.contexto.metricas.eventos_encolados += 1
                        resultado_log = self.normalizador_log_sip.normalizar(evento_crudo)
                        if resultado_log is not None:
                            await self.gestor_colas.encolar(resultado_log)
                            self.contexto.metricas.eventos_encolados += 1
                        continue

                    comando = ComandoProcesarEvento(
                        evento_crudo=evento_crudo,
                        normalizador=self.normalizador,
                        gestor_colas=self.gestor_colas,
                    )
                    await comando.ejecutar()

            except ConnectionError:
                self.contexto.metricas.errores_conexion += 1
                self.logger.advertencia(
                    "Conexion AMI perdida, iniciando reconexion..."
                )
                try:
                    if self.conector is not None:
                        try:
                            await self.conector.desconectar()
                        except Exception:
                            pass
                    self.conector = await self.fabrica.crear_conector(
                        tipo_fuente="ami",
                        host=self.config.ami.host,
                        puerto=self.config.ami.puerto,
                        usuario=self.config.ami.usuario,
                        secreto=self.config.ami.secreto,
                        timeout_accion=self.config.ami.timeout_accion,
                    )
                    await self.conector.conectar_con_reintentos()
                    self.stream = StreamAMI(fuente_eventos=self.conector)
                    self.heartbeat.comando.gestor = self.conector.gestor_llamadas
                    self.logger.info("Reconexion AMI exitosa, reanudando procesamiento")
                except ConnectionError as e:
                    self.logger.error(
                        "Reconexion AMI agotada, deteniendo procesamiento",
                        contexto={"error": str(e)}
                    )
                    break

            except asyncio.CancelledError:
                self.logger.info("Procesamiento de eventos cancelado")
                break

            except Exception as error:
                self.logger.error(
                    "Error en bucle de procesamiento",
                    contexto={"error": str(error)}
                )
                self.contexto.metricas.errores_conexion += 1
                break
