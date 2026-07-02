"""Conector AMI que envuelve la libreria asyncio-manager.

Implementa la interfaz ConectorBase utilizando CallManager
de asyncio-manager para establecer conexion persistente con
el Asterisk Manager Interface y capturar eventos de llamadas.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para manejo de tareas asincronas y colas
import asyncio
# Modulo para jitter en backoff de reconexion
import random
# Tipos para firmas de metodos con type hints
from typing import Any, AsyncIterator, Callable, Dict, Optional

# Libreria asyncio-manager: CallManager gestiona la conexion AMI
from asyncio_manager import CallManager, Message

# Interfaz abstracta que esta clase implementa (patron Strategy)
from src.connectors.base import ConectorBase
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado


class ConectorAMI(ConectorBase):
    """Conector que captura eventos AMI usando asyncio-manager.

    Envuelve CallManager para gestionar la conexion AMI,
    registrar callbacks por tipo de evento y exponer los
    eventos como un stream asincrono iterable.

    Args:
        host: Direccion IP del servidor Asterisk.
        puerto: Puerto TCP del AMI.
        usuario: Usuario de autenticacion AMI.
        secreto: Contrasena de autenticacion AMI.
        timeout_accion: Timeout para acciones AMI en segundos.
        procesar_evento: Callback opcional para procesar cada evento recibido.
    """

    def __init__(
        self,
        host: str,
        puerto: int = 5038,
        usuario: str = "",
        secreto: str = "",
        timeout_accion: float = 5.0,
        procesar_evento: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        # Direccion IP del servidor Asterisk
        self.host = host
        # Puerto TCP del AMI (5038 es el default de Asterisk)
        self.puerto = puerto
        # Nombre de usuario para autenticacion AMI
        self.usuario = usuario
        # Contrasena para autenticacion AMI (MD5 en el protocolo)
        self.secreto = secreto
        # Timeout maximo para esperar respuesta a acciones AMI
        self.timeout_accion = timeout_accion
        # Callback opcional para pipeline externo
        self.procesar_evento = procesar_evento
        # Instancia de CallManager de asyncio-manager (None hasta conectar)
        self.gestor_llamadas: Optional[CallManager] = None
        # Cola asincrona que actua como buffer entre callbacks AMI y pipeline
        self._cola_eventos: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=5000)
        # Bandera de estado de conexion
        self._conectado = False
        # Parametros de reconexion con backoff exponencial
        self._max_intentos_reconexion = 10
        self._demora_inicial_reconexion = 1.0
        self._demora_maxima_reconexion = 30.0
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()
        # Mapa Channel→Uniqueid para correlacionar RTCPReceived sin Uniqueid
        self._channel_to_uniqueid: Dict[str, str] = {}

    @property
    def esta_conectado(self) -> bool:
        """Indica si hay una conexion activa con Asterisk AMI."""
        return self._conectado

    async def conectar(self) -> None:
        """Establece conexion con Asterisk AMI via CallManager.

        Configura los manejadores de eventos de llamada y
        las notificaciones de reconexion/desconexion.

        Raises:
            ConnectionError: Si no se puede establecer la conexion.
        """
        # Registrar intento de conexion con datos del servidor
        self.logger.info(
            "Conectando a Asterisk AMI",
            contexto={"host": self.host, "puerto": self.puerto, "usuario": self.usuario}
        )

        # Crear instancia de CallManager con parametros de conexion
        self.gestor_llamadas = CallManager(
            host=self.host,
            port=self.puerto,
            username=self.usuario,
            secret=self.secreto,
        )

        try:
            # __aenter__ llama internamente a connect() + login()
            # Establece el socket TCP y envia credenciales AMI
            await self.gestor_llamadas.__aenter__()
            # Marcar como conectado solo si __aenter__ fue exitoso
            self._conectado = True
            # Registrar los callbacks de eventos AMI
            self._registrar_manejadores_eventos()
            await self._solicitar_queue_status()
            self.logger.info("Conexion AMI establecida exitosamente")
        except Exception as error:
            # Marcar como desconectado en caso de error
            self._conectado = False
            self.logger.error(
                "Error al conectar con Asterisk AMI",
                contexto={"error": str(error)}
            )
            # Relanzar como ConnectionError con mensaje descriptivo
            raise ConnectionError(f"No se pudo conectar a {self.host}:{self.puerto}") from error

    async def conectar_con_reintentos(self) -> None:
        """Intenta conectar con backoff exponencial y jitter.

        Reintenta la conexion hasta _max_intentos_reconexion veces
        con demora exponencial creciente y jitter aleatorio.

        Raises:
            ConnectionError: Si se agotan todos los intentos.
        """
        intento = 0
        while intento < self._max_intentos_reconexion:
            try:
                await self.conectar()
                self.logger.info(
                    "Reconexion AMI exitosa",
                    contexto={"intentos_realizados": intento + 1}
                )
                return
            except ConnectionError as e:
                intento += 1
                if intento >= self._max_intentos_reconexion:
                    self.logger.error(
                        "Reconexion AMI agotada",
                        contexto={"max_intentos": self._max_intentos_reconexion}
                    )
                    raise
                demora = self._demora_inicial_reconexion * (2 ** (intento - 1))
                demora = min(demora, self._demora_maxima_reconexion)
                # Jitter ±25% para evitar tormenta de reconexiones
                demora *= 0.75 + (random.random() * 0.5)
                self.logger.advertencia(
                    "Reintentando conexion AMI",
                    contexto={
                        "intento": intento,
                        "max_intentos": self._max_intentos_reconexion,
                        "demora_seg": round(demora, 1),
                    }
                )
                await asyncio.sleep(demora)

    async def desconectar(self) -> None:
        """Cierra la conexion con Asterisk AMI de forma segura."""
        # Marcar como desconectado inmediatamente (previene nuevos envios)
        self._conectado = False

        # Solo cerrar si hay un gestor de llamadas activo
        if self.gestor_llamadas is not None:
            try:
                # __aexit__ envia comando Logoff y cierra el socket TCP
                await self.gestor_llamadas.__aexit__(None, None, None)
                self.logger.info("Conexion AMI cerrada correctamente")
            except Exception as error:
                self.logger.error(
                    "Error al cerrar conexion AMI",
                    contexto={"error": str(error)}
                )
                raise

    async def _solicitar_queue_status(self) -> None:
        """Solicita el estado actual de las colas via AMI QueueStatus.

        Asterisk responde con eventos QueueParams (uno por cola),
        QueueEntry (llamadas esperando), QueueMember (agentes).
        Es necesario invocarlo explicitamente porque QueueParams
        solo se envian en respuesta a esta accion o al recargar colas.
        """
        if self.gestor_llamadas is None:
            return
        try:
            self.logger.info("Solicitando estado de colas (QueueStatus)")
            await self.gestor_llamadas._manager.send_action(
                {"Action": "QueueStatus"}
            )
        except Exception as error:
            self.logger.error(
                "Error al solicitar QueueStatus",
                contexto={"error": str(error)}
            )

    async def leer_eventos(self) -> AsyncIterator[Dict[str, Any]]:
        """Itera sobre los eventos AMI entrantes de forma asincrona.

        Los eventos se obtienen de la cola interna que es
        alimentada por los callbacks registrados en AMI.

        Yields:
            Diccionario con los datos normalizados del evento.

        Raises:
            ConnectionError: Si la conexion se pierde.
        """
        while self._conectado:
            try:
                evento = await asyncio.wait_for(
                    self._cola_eventos.get(),
                    timeout=1.0
                )
                yield evento
            except asyncio.TimeoutError:
                continue
            except asyncio.QueueEmpty:
                continue
            except Exception as error:
                self.logger.error(
                    "Error en lectura de eventos",
                    contexto={"error": str(error)}
                )
                self._conectado = False
                raise ConnectionError("Conexion perdida durante lectura de eventos") from error

        raise ConnectionError("Conexion AMI finalizada")

    def _registrar_manejadores_eventos(self) -> None:
        """Registra callbacks para eventos de ciclo de vida de llamadas,
        colas (Queue), CDR y calidad de voz (RTCP).

        Eventos de llamada: NewChannel, Dial, Answer, Hangup.
        Eventos de cola: QueueParams, QueueEntry, QueueMember,
            QueueCallerAbandon, AgentConnect, AgentComplete,
            AgentRingNoAnswer, QueueMemberStatus, QueueMemberPaused.
        Eventos CDR: Cdr.
        Eventos QoS: RTCPReceived.
        """
        # No hacer nada si no hay gestor de llamadas
        if self.gestor_llamadas is None:
            return

        # Referencia local al gestor para evitar accesos repetidos
        gestor = self.gestor_llamadas

        # NewChannel: Asterisk crea un canal (nueva llamada entrante/saliente)
        @gestor._manager.register_event("NewChannel")
        async def _manejar_nuevo_canal(mensaje: Message) -> None:
            # Extraer campos basicos del mensaje AMI
            # CallerIDNum = quien llama, Exten = a quien llama
            # Channel = nombre del canal, Context = contexto del dialplan
            canal = mensaje.get("Channel", "")
            uniqueid = mensaje.get("Uniqueid", "")
            # Poblar mapa Channel→Uniqueid para correlacion futura (RTCPReceived sin id)
            if canal and uniqueid:
                self._channel_to_uniqueid[canal] = uniqueid
            self._encolar_evento({
                "tipo": "NewChannel",
                "id_unico": uniqueid,
                "canal": canal,
                "origen": mensaje.get("CallerIDNum", ""),
                "destino": mensaje.get("Exten", ""),
                "contexto": mensaje.get("Context", ""),
                "estado": mensaje.get("ChannelStateDesc", ""),
            })

        # Dial: Asterisk esta marcando el destino
        @gestor._manager.register_event("Dial")
        async def _manejar_dial(mensaje: Message) -> None:
            # Incluir canal_origen (quien marca) y canal_destino (quien recibe)
            # DestUniqueid permite correlacionar ambos lados de la llamada
            canal_origen = mensaje.get("Channel", "")
            canal_destino = mensaje.get("Destination", "")
            id_unico = mensaje.get("Uniqueid", "")
            destino_id_unico = mensaje.get("DestUniqueid", "")
            # Poblar mapa para ambos canales involucrados en el dial
            if canal_origen and id_unico:
                self._channel_to_uniqueid[canal_origen] = id_unico
            if canal_destino and destino_id_unico:
                self._channel_to_uniqueid[canal_destino] = destino_id_unico
            self._encolar_evento({
                "tipo": "Dial",
                "id_unico": id_unico,
                "origen": mensaje.get("CallerIDNum", ""),
                "destino": mensaje.get("Exten", ""),
                "canal_origen": canal_origen,
                "canal_destino": canal_destino,
                "destino_id_unico": destino_id_unico,
            })

        # Answer: alguien respondio la llamada
        @gestor._manager.register_event("Answer")
        async def _manejar_respuesta(mensaje: Message) -> None:
            # Registrar que la llamada fue respondida
            # CallerIDNum en Answer es quien responde (no necesariamente quien llama)
            self._encolar_evento({
                "tipo": "Answer",
                "id_unico": mensaje.get("Uniqueid", ""),
                "canal": mensaje.get("Channel", ""),
                "origen": mensaje.get("CallerIDNum", ""),
            })

        # Hangup: la llamada termino (quien sea que haya colgado)
        @gestor._manager.register_event("Hangup")
        async def _manejar_cuelgue(mensaje: Message) -> None:
            # Duration = segundos desde NewChannel hasta Hangup
            # Cause-txt = descripcion legible de la causa de cuelgue
            canal = mensaje.get("Channel", "")
            # Limpiar entrada del mapa Channel→Uniqueid al finalizar la llamada
            if canal and canal in self._channel_to_uniqueid:
                del self._channel_to_uniqueid[canal]
            self._encolar_evento({
                "tipo": "Hangup",
                "id_unico": mensaje.get("Uniqueid", ""),
                "canal": canal,
                "origen": mensaje.get("CallerIDNum", ""),
                "duracion": mensaje.get("Duration", "0"),
                "causa": mensaje.get("Cause-txt", ""),
                "codigo_causa": mensaje.get("Cause", ""),
            })

        # --- EVENTOS DE COLA (QUEUE) ---

        # QueueParams: parametros y estado actual de una cola
        @gestor._manager.register_event("QueueParams")
        async def _manejar_queue_params(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "QueueParams",
                "cola": mensaje.get("Queue", ""),
                "max": mensaje.get("Max", "0"),
                "estrategia": mensaje.get("Strategy", ""),
                "llamadas_en_cola": mensaje.get("CallsInQueue", "0"),
                "nivel_servicio": mensaje.get("ServiceLevel", "0"),
                "llamadas_nivel_servicio": mensaje.get("ServiceLevelPerf", "0"),
                "tiempo_espera_mas_antiguo": mensaje.get("Holdtime", "0"),
            })

        # QueueEntry: una llamada entra a la cola
        @gestor._manager.register_event("QueueEntry")
        async def _manejar_queue_entry(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "QueueEntry",
                "cola": mensaje.get("Queue", ""),
                "posicion": mensaje.get("Position", "0"),
                "origen": mensaje.get("CallerID", ""),
                "id_unico": mensaje.get("Uniqueid", ""),
                "tiempo_espera": mensaje.get("Wait", "0"),
            })

        # QueueMember: estado de un agente miembro de una cola
        @gestor._manager.register_event("QueueMember")
        async def _manejar_queue_member(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "QueueMember",
                "cola": mensaje.get("Queue", ""),
                "nombre": mensaje.get("MemberName", ""),
                "interface": mensaje.get("Interface", ""),
                "estado": mensaje.get("Status", "0"),
                "pausado": mensaje.get("Paused", "0"),
                "penalty": mensaje.get("Penalty", "0"),
                "miembro_id": mensaje.get("Location", ""),
            })

        # QueueCallerAbandon: un cliente cuelga mientras espera en cola
        @gestor._manager.register_event("QueueCallerAbandon")
        async def _manejar_queue_abandono(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "QueueCallerAbandon",
                "cola": mensaje.get("Queue", ""),
                "id_unico": mensaje.get("Uniqueid", ""),
                "origen": mensaje.get("CallerID", ""),
                "tiempo_espera": mensaje.get("WaitTime", "0"),
            })

        # AgentConnect: llamada en cola conectada a un agente
        @gestor._manager.register_event("AgentConnect")
        async def _manejar_agent_connect(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "AgentConnect",
                "cola": mensaje.get("Queue", ""),
                "id_unico": mensaje.get("Uniqueid", ""),
                "origen": mensaje.get("CallerID", ""),
                "agente": mensaje.get("MemberName", ""),
                "tiempo_espera": mensaje.get("HoldTime", "0"),
                "puente_id_unico": mensaje.get("BridgedUniqueid", ""),
            })

        # AgentComplete: llamada en cola finalizada por el agente
        @gestor._manager.register_event("AgentComplete")
        async def _manejar_agent_complete(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "AgentComplete",
                "cola": mensaje.get("Queue", ""),
                "id_unico": mensaje.get("Uniqueid", ""),
                "agente": mensaje.get("MemberName", ""),
                "tiempo_espera": mensaje.get("HoldTime", "0"),
                "tiempo_conversacion": mensaje.get("TalkTime", "0"),
                "motivo": mensaje.get("Reason", ""),
            })

        # AgentRingNoAnswer: el agente no respondio la llamada de cola
        @gestor._manager.register_event("AgentRingNoAnswer")
        async def _manejar_agent_no_answer(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "AgentRingNoAnswer",
                "cola": mensaje.get("Queue", ""),
                "id_unico": mensaje.get("Uniqueid", ""),
                "agente": mensaje.get("MemberName", ""),
                "tiempo_ring": mensaje.get("RingTime", "0"),
            })

        # QueueMemberStatus: cambio de estado de un agente en cola
        @gestor._manager.register_event("QueueMemberStatus")
        async def _manejar_member_status(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "QueueMemberStatus",
                "cola": mensaje.get("Queue", ""),
                "nombre": mensaje.get("MemberName", ""),
                "interface": mensaje.get("Interface", ""),
                "estado": mensaje.get("Status", "0"),
                "pausado": mensaje.get("Paused", "0"),
            })

        # QueueMemberPaused: agente pausado o despausado en cola
        @gestor._manager.register_event("QueueMemberPaused")
        async def _manejar_member_paused(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "QueueMemberPaused",
                "cola": mensaje.get("Queue", ""),
                "nombre": mensaje.get("MemberName", ""),
                "interface": mensaje.get("Interface", ""),
                "pausado": mensaje.get("Paused", "0"),
                "motivo": mensaje.get("Reason", ""),
            })

        # --- EVENTOS SIP ---

        # PeerStatus: cambio de estado de un peer SIP (registrado/no registrado)
        @gestor._manager.register_event("PeerStatus")
        async def _manejar_peer_status(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "PeerStatus",
                "origen": mensaje.get("Peer", ""),
                "estado": mensaje.get("PeerStatus", ""),
                "codigo_respuesta": mensaje.get("Time", ""),
                "direccion": mensaje.get("Address", ""),
            })

        # Registry: estado de registro a troncal SIP
        @gestor._manager.register_event("Registry")
        async def _manejar_registry(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "Registry",
                "origen": mensaje.get("Host", ""),
                "estado": mensaje.get("State", ""),
                "codigo_respuesta": mensaje.get("Cause", ""),
                "dominio": mensaje.get("Domain", ""),
                "usuario": mensaje.get("Username", ""),
            })

        # --- EVENTO CDR ---

        # Cdr: registro detallado de llamada al finalizar
        @gestor._manager.register_event("Cdr")
        async def _manejar_cdr(mensaje: Message) -> None:
            self._encolar_evento({
                "tipo": "Cdr",
                "id_unico": mensaje.get("uniqueid", ""),
                "origen": mensaje.get("src", ""),
                "destino": mensaje.get("dst", ""),
                "canal": mensaje.get("channel", ""),
                "canal_destino": mensaje.get("dstchannel", ""),
                "contexto": mensaje.get("dcontext", ""),
                "origen_clid": mensaje.get("clid", ""),
                "inicio": mensaje.get("start", ""),
                "respuesta": mensaje.get("answer", ""),
                "fin": mensaje.get("end", ""),
                "duracion": mensaje.get("duration", "0"),
                "duracion_facturable": mensaje.get("billsec", "0"),
                "disposition": mensaje.get("disposition", ""),
                "codigo_cuenta": mensaje.get("accountcode", ""),
                "ultima_app": mensaje.get("lastapp", ""),
                "ultimos_datos": mensaje.get("lastdata", ""),
            })

        # --- EVENTO QoS (RTCP) ---

        # RTCPReceived: reporte RTCP con calidad de voz
        @gestor._manager.register_event("RTCPReceived")
        async def _manejar_rtcp(mensaje: Message) -> None:
            uniqueid = mensaje.get("Uniqueid", "")
            canal = mensaje.get("Channel", "")
            # Si Uniqueid esta vacio o es SSRC (numerico), intentar resolver por canal
            if not uniqueid or uniqueid.isdigit():
                if canal in self._channel_to_uniqueid:
                    uniqueid = self._channel_to_uniqueid[canal]
                else:
                    uniqueid = mensaje.get("SSRC", "")
            self._encolar_evento({
                "tipo": "RTCPReceived",
                "id_unico": uniqueid,
                "fraccion_perdida": mensaje.get("FractionLost", "0"),
                "jitter": mensaje.get("Jitter", "0"),
                "rtt": mensaje.get("RTT", "0"),
                "ssrc": mensaje.get("SSRC", ""),
                "fuente_ip": mensaje.get("SourceIP", ""),
                "fuente_puerto": mensaje.get("SourcePort", "0"),
                "canal": canal,
            })

    def _encolar_evento(self, evento: Dict[str, Any]) -> None:
        """Encola un evento en la cola interna para procesamiento.

        Args:
            evento: Diccionario con los datos normalizados del evento.
        """
        try:
            # put_nowait inserta sin bloquear (la cola es ilimitada)
            self._cola_eventos.put_nowait(evento)
            # Loggear a nivel DEBUG el evento encolado
            self.logger.depuracion(
                "Evento encolado",
                contexto={"tipo": evento.get("tipo", "desconocido")}
            )
        except Exception as error:
            # Error poco probable (cola ilimitada), pero capturado por seguridad
            self.logger.error(
                "Error al encolar evento",
                contexto={"error": str(error), "tipo": evento.get("tipo")}
            )
