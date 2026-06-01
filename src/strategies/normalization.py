"""Estrategia de normalizacion con consolidacion de llamadas.

Acumula eventos por id_unico y cuando la llamada finaliza
(Hangup) emite un registro consolidado con todos los datos
del ciclo de vida completo: origen, destino, duracion, causa.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para generacion de timestamps en formato ISO 8601
import datetime
# Modulo para generar hashes SHA-256 (idempotencia de event_id)
import hashlib
# Modulo para timestamps Unix y tiempo de expiracion de llamadas huerfanas
import time
# Tipos para type hints en firmas de metodos
from typing import Any, Dict, List, Optional

# Singleton de contexto para obtener el agente_id
from src.core.contexto import ContextoEjecucion
# Interfaz abstracta que esta clase implementa
from src.strategies.base import EstrategiaNormalizacion


class LlamadaEnProgreso:
    """Acumula eventos de una llamada hasta que finaliza.

    Cada instancia representa una llamada identificada por su
    id_unico de Asterisk. Los eventos parciales (NewChannel,
    Dial, Answer) actualizan sus campos. Al recibir Hangup
    se genera el registro consolidado final.
    """

    def __init__(self, id_unico: str) -> None:
        # Identificador unico de Asterisk para esta llamada
        self.id_unico = id_unico
        # Nombre del canal SIP/IAX2 (ej: SIP/100-00000001)
        self.canal: str = ""
        # Extension o numero que origina la llamada (CallerID)
        self.origen: str = ""
        # Extension o numero destino al que se llama
        self.destino: str = ""
        # Contexto de Asterisk donde se ejecuta el dialplan
        self.contexto: str = ""
        # Canal que inicio la marcacion (quien llama)
        self.canal_origen: str = ""
        # Canal que recibe la llamada (quien es llamado)
        self.canal_destino: str = ""
        # Bandera: True si alguien respondio (evento Answer recibido)
        self.respondio: bool = False
        # Duracion en segundos desde NewChannel hasta Hangup
        self.duracion: str = "0"
        # Descripcion textual de la causa de cuelgue (Normal Clearing, etc.)
        self.causa: str = ""
        # Timestamp ISO 8601 del primer evento de la llamada (NewChannel)
        self.timestamp_inicio: str = ""
        # Timestamp ISO 8601 del evento Hangup (fin de la llamada)
        self.timestamp_fin: str = ""
        # QoS: fraccion de perdida de paquetes RTCP (0-255)
        self.fraccion_perdida: str = ""
        # QoS: jitter en milisegundos
        self.jitter: str = ""
        # QoS: round trip time en milisegundos
        self.rtt: str = ""
        # QoS: codec de audio detectado
        self.codec: str = ""

    def actualizar_con(self, evento: Dict[str, Any]) -> None:
        """Actualiza el estado de la llamada con un evento parcial.

        Args:
            evento: Evento crudo recibido del conector AMI.
        """
        # Extraer el tipo de evento del diccionario
        tipo = evento.get("tipo", "")

        # timestamp_inicio solo se setea con el primer evento que llega
        if not self.timestamp_inicio:
            # Obtener timestamp UTC actual en formato ISO 8601
            self.timestamp_inicio = self._ahora()

        # NewChannel: Asterisk crea un canal (evento de nacimiento)
        if tipo == "NewChannel":
            # CallerIDNum = quien llama (origen de la llamada)
            self.canal = evento.get("canal", self.canal)
            self.origen = evento.get("origen", self.origen)
            # Exten = extension destino marcada
            self.destino = evento.get("destino", self.destino)
            # Context del dialplan donde se ejecuta la llamada
            self.contexto = evento.get("contexto", self.contexto)

        # Dial: Asterisk esta intentando conectar con el destino
        elif tipo == "Dial":
            # Actualizar origen/destino por si NewChannel no los trajo
            self.origen = evento.get("origen", self.origen)
            self.destino = evento.get("destino", self.destino)
            # Quien marca (Channel) y quien recibe (Destination)
            self.canal_origen = evento.get("canal_origen", self.canal_origen)
            self.canal_destino = evento.get("canal_destino", self.canal_destino)

        # Answer: alguien respondio la llamada
        elif tipo == "Answer":
            # NO sobreescribimos origen: el CallerID del Answer es
            # quien responde, no el llamante original
            self.respondio = True
            # Actualizar canal por si cambio durante el establecimiento
            self.canal = evento.get("canal", self.canal)

        # Hangup: la llamada termino oficialmente
        elif tipo == "Hangup":
            # Duracion en segundos reportada por Asterisk
            self.duracion = evento.get("duracion", self.duracion)
            # Causa legible (Normal Clearing, Busy, No Answer, etc.)
            self.causa = evento.get("causa", self.causa)
            # Marcar el timestamp de finalizacion
            self.timestamp_fin = self._ahora()

        # RTCPReceived: actualizar metricas de calidad de voz
        elif tipo == "RTCPReceived":
            self.fraccion_perdida = evento.get("fraccion_perdida", self.fraccion_perdida)
            self.jitter = evento.get("jitter", self.jitter)
            self.rtt = evento.get("rtt", self.rtt)

    def actualizar_qos(self, evento: Dict[str, Any]) -> None:
        """Actualiza metricas de calidad de voz desde un evento RTCP.

        Args:
            evento: Evento RTCPReceived con datos de calidad.
        """
        self.fraccion_perdida = evento.get("fraccion_perdida", self.fraccion_perdida)
        self.jitter = evento.get("jitter", self.jitter)
        self.rtt = evento.get("rtt", self.rtt)

    def esta_completa(self) -> bool:
        """Indica si la llamada ya recibio el evento Hangup.

        Returns:
            True si ya se recibio el Hangup (timestamp_fin seteado).
        """
        # timestamp_fin solo se setea en actualizar_con() con tipo Hangup
        return bool(self.timestamp_fin)

    def consolidar(self, agente_id: str) -> Dict[str, Any]:
        """Genera el registro consolidado final de la llamada.

        Solo se invoca cuando llega el Hangup. Produce un unico
        registro que contiene TODO el ciclo de vida de la llamada.

        Args:
            agente_id: UUID del agente para incluir en el registro.

        Returns:
            Diccionario con todos los datos de la llamada.
        """
        # Construir el diccionario completo del evento consolidado
        return {
            # Hash unico para idempotencia (misma llamada = mismo event_id)
            "event_id": self._generar_id(),
            # Timestamp de inicio de la llamada (ISO 8601)
            "timestamp": self.timestamp_inicio,
            # Timestamp de fin de la llamada (ISO 8601)
            "timestamp_fin": self.timestamp_fin,
            # Fuente de origen del evento (AMI en este caso)
            "fuente": "ami",
            # UUID del agente que capturo esta llamada
            "agente_id": agente_id,
            # Tipo de evento consolidado (diferente de parcial)
            "tipo": "llamada_completa",
            # Datos especificos de la llamada
            "datos": {
                # ID unico de Asterisk para correlacion
                "id_unico": self.id_unico,
                # Numero de quien llamo (con fallback a desconocido)
                "origen": self.origen or "(desconocido)",
                # Numero de quien recibio la llamada
                "destino": self.destino or "(desconocido)",
                # Canal utilizado en la llamada
                "canal": self.canal,
                # Contexto de Asterisk
                "contexto": self.contexto,
                # Booleano: true si la llamada fue respondida
                "respondio": self.respondio,
                # Duracion total en segundos
                "duracion_segundos": self.duracion,
                # Causa textual de finalizacion
                "causa": self.causa,
                # Calidad de voz (QoS) recolectada de eventos RTCP
                "calidad_voz": {
                    "fraccion_perdida": self.fraccion_perdida,
                    "jitter": self.jitter,
                    "rtt": self.rtt,
                },
            },
        }

    def _generar_id(self) -> str:
        # Combinar id_unico + timestamp_inicio como semilla unica
        base = f"{self.id_unico}:{self.timestamp_inicio}"
        # Generar hash SHA-256 truncado a 32 caracteres para idempotencia
        return hashlib.sha256(base.encode()).hexdigest()[:32]

    def _ahora(self) -> str:
        # Obtener timestamp actual con timezone UTC en formato ISO 8601
        return datetime.datetime.now(datetime.timezone.utc).isoformat()


class NormalizadorAMI(EstrategiaNormalizacion):
    """Normaliza eventos AMI y consolida llamadas completas.

    Acumula los eventos parciales de cada llamada (identificada
    por id_unico) y solo emite el registro consolidado cuando
    la llamada finaliza (Hangup). Las llamadas huerfanas se
    limpian automaticamente.

    Uso:
        normalizador = NormalizadorAMI()
        resultado = normalizador.normalizar(evento_crudo)
    """

    def __init__(self) -> None:
        # Obtener instancia singleton del contexto de ejecucion
        self.contexto = ContextoEjecucion.obtener_instancia()
        # Diccionario de llamadas en curso: key = id_unico de Asterisk
        self._llamadas: Dict[str, LlamadaEnProgreso] = {}
        # Tiempo maximo en segundos sin Hangup antes de limpiar
        # 3600s = 1 hora: si una llamada no termina en 1h, se descarta
        self._tiempo_maximo_huerfana: float = 3600.0

    def normalizar(self, evento_crudo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normaliza un evento y consolida informacion de la llamada.

        Si el evento es Hangup, retorna el registro consolidado
        de toda la llamada. En cualquier otro caso, actualiza
        el estado interno y retorna None (el evento parcial no
        se transmite individualmente).

        Args:
            evento_crudo: Evento del conector AMI.

        Returns:
            Dict consolidado si la llamada termino, None en caso contrario.
        """
        # Extraer campos base del evento crudo
        id_unico = evento_crudo.get("id_unico", "")
        tipo = evento_crudo.get("tipo", "")

        # Ignorar eventos que no pertenecen a una llamada
        # (ej: heartbeat de AMI, eventos del sistema sin id_unico)
        if not id_unico:
            return None

        # Limpieza preventiva antes de procesar el evento actual
        # Elimina llamadas huerfanas que nunca recibieron Hangup
        self._limpiar_llamadas_huerfanas()

        # Si es la primera vez que vemos este id_unico, crear registro
        if id_unico not in self._llamadas:
            self._llamadas[id_unico] = LlamadaEnProgreso(id_unico)

        # Obtener la instancia de llamada y actualizarla con el evento
        llamada = self._llamadas[id_unico]
        llamada.actualizar_con(evento_crudo)

        # Solo cuando llega Hangup se genera el registro consolidado
        # Eventos parciales (NewChannel, Dial, Answer) retornan None
        # y NO se transmiten individualmente al backend
        if tipo == "Hangup":
            # Generar el registro completo con todos los datos
            registro = llamada.consolidar(self.contexto.agente_id)
            # Eliminar la llamada del diccionario para evitar fuga de memoria
            del self._llamadas[id_unico]
            # Retornar el registro consolidado para su transmision
            return registro

        # RTCPReceived: actualizar QoS sin emitir evento
        if tipo == "RTCPReceived":
            llamada.actualizar_qos(evento_crudo)
            return None

        # Evento parcial: se acumula internamente, no se transmite
        return None

    def _limpiar_llamadas_huerfanas(self) -> None:
        """Elimina llamadas que nunca recibieron Hangup.

        En casos de caida de red o reinicio de Asterisk, algunas
        llamadas quedan sin Hangup. Esta limpieza evita la
        acumulacion indefinida en memoria.
        """
        ahora = time.time()
        ids_a_eliminar = [
            uid for uid, ll in self._llamadas.items()
            if ahora - self._obtener_tiempo_creacion(ll) > self._tiempo_maximo_huerfana
        ]
        if ids_a_eliminar:
            print(
                f"[ADVERTENCIA] Limpiando {len(ids_a_eliminar)} llamadas huerfanas "
                f"(mas de {self._tiempo_maximo_huerfana}s sin Hangup)"
            )
        for uid in ids_a_eliminar:
            del self._llamadas[uid]

    def _obtener_tiempo_creacion(self, llamada: LlamadaEnProgreso) -> float:
        """Retorna timestamp Unix de creacion de la llamada.

        Utiliza timestamp_inicio (ISO 8601) si esta disponible,
        o el timestamp actual como fallback para llamadas sin inicio registrado.
        """
        if llamada.timestamp_inicio:
            try:
                dt = datetime.datetime.fromisoformat(llamada.timestamp_inicio)
                return dt.timestamp()
            except (ValueError, TypeError, OverflowError):
                pass
        return time.time()


class EntradaColaEnProgreso:
    """Acumula eventos de una entrada en cola hasta que se resuelve.

    Cada instancia representa una llamada en cola identificada por
    su id_unico. Los eventos QueueEntry, QueueCallerAbandon, AgentConnect,
    AgentComplete y AgentRingNoAnswer actualizan su estado.
    """

    def __init__(self, id_unico: str) -> None:
        self.id_unico = id_unico
        self.cola: str = ""
        self.posicion: str = ""
        self.origen: str = ""
        self.tiempo_espera: str = "0"
        self.agente: str = ""
        self.tiempo_conversacion: str = ""
        self.tiempo_ring: str = ""
        self.motivo: str = ""
        self.timestamp_inicio: str = ""

    def actualizar_con(self, evento: Dict[str, Any]) -> None:
        tipo = evento.get("tipo", "")
        if not self.timestamp_inicio:
            self.timestamp_inicio = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if tipo == "QueueEntry":
            self.cola = evento.get("cola", self.cola)
            self.posicion = evento.get("posicion", self.posicion)
            self.origen = evento.get("origen", self.origen)
            self.tiempo_espera = evento.get("tiempo_espera", self.tiempo_espera)
        elif tipo == "QueueCallerAbandon":
            self.tiempo_espera = evento.get("tiempo_espera", self.tiempo_espera)
        elif tipo == "AgentConnect":
            self.agente = evento.get("agente", self.agente)
            self.tiempo_espera = evento.get("tiempo_espera", self.tiempo_espera)
        elif tipo == "AgentComplete":
            self.cola = evento.get("cola", self.cola)
            self.agente = evento.get("agente", self.agente)
            self.tiempo_espera = evento.get("tiempo_espera", self.tiempo_espera)
            self.tiempo_conversacion = evento.get("tiempo_conversacion", self.tiempo_conversacion)
            self.motivo = evento.get("motivo", self.motivo)
        elif tipo == "AgentRingNoAnswer":
            self.agente = evento.get("agente", self.agente)
            self.tiempo_ring = evento.get("tiempo_ring", self.tiempo_ring)

    def consolidar(self, agente_id: str, subtipo: str) -> Dict[str, Any]:
        base = f"{self.id_unico}:{subtipo}:{self.timestamp_inicio}"
        event_id = hashlib.sha256(base.encode()).hexdigest()[:32]
        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {
            "event_id": event_id,
            "timestamp": self.timestamp_inicio,
            "timestamp_fin": ahora,
            "fuente": "queue",
            "agente_id": agente_id,
            "tipo": "evento_queue",
            "datos": {
                "id_unico": self.id_unico,
                "cola": self.cola,
                "origen": self.origen or "(desconocido)",
                "posicion": self.posicion,
                "tiempo_espera": self.tiempo_espera,
                "agente": self.agente,
                "tiempo_conversacion": self.tiempo_conversacion,
                "tiempo_ring": self.tiempo_ring,
                "motivo": self.motivo,
                "subtipo": subtipo,
            },
        }


class NormalizadorQueue:
    """Normaliza eventos Queue de Asterisk.

    Acumula entradas en cola (QueueEntry) y emite eventos
    consolidados cuando ocurre un abandono, conexion con
    agente, o finalizacion.
    Eventos sin acumulacion (QueueParams, QueueMember, etc.)
    se emiten inmediatamente.
    """

    EVENTOS_INMEDIATOS = frozenset({
        "QueueParams", "QueueMember", "QueueMemberStatus", "QueueMemberPaused",
    })

    EVENTOS_ACUMULABLES = frozenset({
        "QueueEntry", "QueueCallerAbandon", "AgentConnect",
        "AgentComplete", "AgentRingNoAnswer",
    })

    def __init__(self) -> None:
        self.contexto = ContextoEjecucion.obtener_instancia()
        self._entradas: Dict[str, EntradaColaEnProgreso] = {}

    def normalizar(self, evento_crudo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tipo = evento_crudo.get("tipo", "")

        if tipo in self.EVENTOS_INMEDIATOS:
            return self._emitir_inmediato(evento_crudo)

        if tipo in self.EVENTOS_ACUMULABLES:
            return self._procesar_acumulable(evento_crudo)

        return None

    def _emitir_inmediato(self, evento: Dict[str, Any]) -> Dict[str, Any]:
        tipo = evento.get("tipo", "")
        agente_id = self.contexto.agente_id
        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        base = f"{tipo}:{evento.get('cola', '')}:{ahora}"
        event_id = hashlib.sha256(base.encode()).hexdigest()[:32]
        return {
            "event_id": event_id,
            "timestamp": ahora,
            "timestamp_fin": ahora,
            "fuente": "queue",
            "agente_id": agente_id,
            "tipo": "evento_queue",
            "datos": dict(evento),
        }

    def _procesar_acumulable(self, evento: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        id_unico = evento.get("id_unico", "")
        tipo = evento.get("tipo", "")

        if not id_unico:
            return None

        if id_unico not in self._entradas:
            self._entradas[id_unico] = EntradaColaEnProgreso(id_unico)

        entrada = self._entradas[id_unico]
        entrada.actualizar_con(evento)

        if tipo == "QueueCallerAbandon":
            registro = entrada.consolidar(self.contexto.agente_id, "abandono_cola")
            del self._entradas[id_unico]
            return registro

        if tipo == "AgentConnect":
            registro = entrada.consolidar(self.contexto.agente_id, "conectado_a_agente")
            del self._entradas[id_unico]
            return registro

        if tipo == "AgentComplete":
            registro = entrada.consolidar(self.contexto.agente_id, "completada_por_agente")
            del self._entradas[id_unico]
            return registro

        if tipo == "AgentRingNoAnswer":
            registro = entrada.consolidar(self.contexto.agente_id, "agente_no_respondio")
            del self._entradas[id_unico]
            return registro

        return None


class NormalizadorSIP:
    """Normaliza eventos SIP (PeerStatus, Registry) de Asterisk.

    Los eventos SIP reflejan cambios en el estado de peers
    (registro/desregistro) y troncales (conexion/perdida).
    Se emiten inmediatamente como eventos individuales.
    """

    EVENTOS_SIP = frozenset({
        "PeerStatus", "Registry",
    })

    def __init__(self) -> None:
        self.contexto = ContextoEjecucion.obtener_instancia()

    def normalizar(self, evento_crudo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tipo = evento_crudo.get("tipo", "")
        if tipo not in self.EVENTOS_SIP:
            return None

        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        origen = evento_crudo.get("origen", "")
        estado = evento_crudo.get("estado", "")
        base = f"{tipo}:{origen}:{estado}:{ahora}"
        event_id = hashlib.sha256(base.encode()).hexdigest()[:32]

        return {
            "event_id": event_id,
            "timestamp": ahora,
            "timestamp_fin": ahora,
            "fuente": "sip",
            "agente_id": self.contexto.agente_id,
            "tipo": "evento_sip",
            "datos": {
                "metodo": tipo,
                "origen": origen,
                "estado": estado,
                "codigo_respuesta": evento_crudo.get("codigo_respuesta", ""),
                "detalle": evento_crudo.get("direccion", evento_crudo.get("dominio", "")),
            },
        }


class NormalizadorLogSIP:
    """Normaliza eventos SIP en logs SIP (sip_log) para almacenamiento y analisis.

    Produce eventos de tipo 'sip_log' con mensajes legibles y clasificacion
    para la tabla logs_sip del backend.
    """

    EVENTOS_LOG_SIP = frozenset({
        "PeerStatus", "Registry",
    })

    def __init__(self) -> None:
        self.contexto = ContextoEjecucion.obtener_instancia()

    def normalizar(self, evento_crudo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        tipo = evento_crudo.get("tipo", "")
        if tipo not in self.EVENTOS_LOG_SIP:
            return None

        ahora = datetime.datetime.now(datetime.timezone.utc).isoformat()
        origen = evento_crudo.get("origen", "")
        estado = evento_crudo.get("estado", "")
        base = f"{tipo}:{origen}:{estado}:{ahora}"
        event_id = hashlib.sha256(base.encode()).hexdigest()[:32]

        nivel, clasificacion = self._clasificar(tipo, estado)

        if tipo == "Registry":
            mensaje = f"Registro SIP {estado.lower()} para {origen}"
            raw = evento_crudo.get("codigo_respuesta", "")
        else:
            mensaje = f"Peer {origen} cambio a estado {estado}"
            raw = evento_crudo.get("direccion", "")

        return {
            "event_id": event_id,
            "timestamp": ahora,
            "timestamp_fin": ahora,
            "fuente": "sip",
            "agente_id": self.contexto.agente_id,
            "tipo": "sip_log",
            "datos": {
                "nivel": nivel,
                "tipo_sip": tipo,
                "clasificacion": clasificacion,
                "mensaje": mensaje,
                "raw": raw,
            },
        }

    @staticmethod
    def _clasificar(tipo: str, estado: str) -> tuple[str, str]:
        estado_lower = estado.lower() if estado else ""
        if tipo == "Registry":
            if estado_lower in ("rejected", "timeout"):
                return "ERROR", "auth"
            elif estado_lower == "registered":
                return "INFO", "auth"
            return "WARN", "auth"
        else:  # PeerStatus
            if estado_lower in ("unregistered", "rejected"):
                return "ERROR", "peer"
            elif estado_lower == "registered":
                return "INFO", "peer"
            return "WARN", "peer"


class NormalizadorCDR:
    """Normaliza eventos CDR (Call Detail Record) de Asterisk.

    Los CDR se emiten al finalizar cada llamada y contienen
    datos precisos de facturacion (billsec, disposition) y
    timestamps exactos (start, answer, end).
    Se emiten como eventos independientes de tipo 'cdr_completo'.
    """

    def __init__(self) -> None:
        self.contexto = ContextoEjecucion.obtener_instancia()

    def normalizar(self, evento_crudo: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        id_unico = evento_crudo.get("id_unico", "")
        inicio = evento_crudo.get("inicio", "")
        if not id_unico:
            return None

        base = f"{id_unico}:{inicio}:cdr"
        event_id = hashlib.sha256(base.encode()).hexdigest()[:32]

        return {
            "event_id": event_id,
            "timestamp": inicio,
            "timestamp_fin": evento_crudo.get("fin", ""),
            "fuente": "cdr",
            "agente_id": self.contexto.agente_id,
            "tipo": "cdr_completo",
            "datos": {
                "id_unico": id_unico,
                "origen": evento_crudo.get("origen", ""),
                "destino": evento_crudo.get("destino", ""),
                "canal": evento_crudo.get("canal", ""),
                "canal_destino": evento_crudo.get("canal_destino", ""),
                "contexto": evento_crudo.get("contexto", ""),
                "origen_clid": evento_crudo.get("origen_clid", ""),
                "inicio": inicio,
                "respuesta": evento_crudo.get("respuesta", ""),
                "fin": evento_crudo.get("fin", ""),
                "duracion": evento_crudo.get("duracion", "0"),
                "duracion_facturable": evento_crudo.get("duracion_facturable", "0"),
                "disposition": evento_crudo.get("disposition", ""),
                "codigo_cuenta": evento_crudo.get("codigo_cuenta", ""),
                "ultima_app": evento_crudo.get("ultima_app", ""),
                "ultimos_datos": evento_crudo.get("ultimos_datos", ""),
            },
        }
