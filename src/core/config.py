"""Modulo Singleton para gestionar la configuracion del agente.

Carga variables de entorno desde archivo .env y las combina
con valores por defecto del archivo YAML. Provee acceso
de solo lectura a toda la configuracion.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Acceso a variables de entorno del sistema
import os
# Decoradores y funciones para data classes (clases de datos inmutables)
from dataclasses import dataclass, field
# Manejo de rutas de archivos del sistema
from pathlib import Path
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Cargador de archivos .env al entorno de proceso
from dotenv import load_dotenv


RUTA_BASE = Path(__file__).resolve().parent.parent.parent


@dataclass
class ConfiguracionAMI:
    """Configuracion de conexion al Asterisk Manager Interface."""
    host: str = "127.0.0.1"
    puerto: int = 5038
    usuario: str = ""
    secreto: str = ""
    timeout_accion: float = 5.0
    timeout_conexion: float = 10.0
    timeout_lectura: float = 30.0
    intervalo_ping: float = 10.0
    intentos_reconexion: int = 10
    demora_inicial_reconexion: float = 1.0
    demora_maxima_reconexion: float = 60.0


@dataclass
class ConfiguracionBackend:
    """Configuracion de conexion al backend central SaaS."""
    url: str = ""
    timeout_peticion: float = 30.0
    intentos_maximos: int = 3


@dataclass
class ConfiguracionBuffer:
    """Configuracion del buffer offline para resiliencia."""
    ruta: str = "/tmp/callmetric/buffer.db"
    tamano_maximo: int = 10000
    tamano_lote: int = 50
    intervalo_flush: int = 60


@dataclass
class ConfiguracionCDR:
    """Configuracion de conexion a base de datos CDR de Asterisk."""
    db_host: str = "localhost"
    db_port: int = 3306
    db_name: str = "asteriskcdrdb"
    db_user: str = ""
    db_password: str = ""
    intervalo_reporte: int = 90
    activo: bool = False


@dataclass
class ConfiguracionTransmision:
    """Configuracion del modo de transmision de eventos."""
    modo: str = "http"
    comprimir: bool = False


class ConfiguracionAgente:
    """Singleton que centraliza toda la configuracion del agente.

    Carga .env y default.yaml al iniciar y provee acceso
    estructurado a traves de propiedades tipadas.

    Uso:
        config = ConfiguracionAgente.obtener_instancia()
        ami_host = config.ami.host
    """

    _instancia: Optional[ConfiguracionAgente] = None

    def __init__(self) -> None:
        # Bandera para evitar recarga multiple
        self._cargado = False
        # Identificador unico del agente (UUID)
        self.agente_id: str = ""
        self.pbx_id: str = ""
        self.empresa_id: str = ""
        self.token_registro: str = ""
        # Intervalo en segundos entre envios de heartbeat
        self.intervalo_heartbeat: int = 30
        # Nivel de log (DEBUG, INFO, WARNING, ERROR)
        self.nivel_log: str = "INFO"
        # Configuracion especifica de conexion AMI
        self.ami = ConfiguracionAMI()
        # Configuracion de conexion al backend central
        self.backend = ConfiguracionBackend()
        # Configuracion del buffer offline SQLite
        self.buffer = ConfiguracionBuffer()
        # Configuracion del modo de transmision
        self.transmision = ConfiguracionTransmision()
        # Configuracion de reportes CDR desde MySQL de Asterisk
        self.cdr = ConfiguracionCDR()

    @classmethod
    def obtener_instancia(cls) -> ConfiguracionAgente:
        """Retorna la instancia unica del singleton."""
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    def cargar(self, ruta_env: Optional[str] = None) -> None:
        """Carga la configuracion desde archivos .env y YAML.

        Args:
            ruta_env: Ruta al archivo .env. Por defecto busca
                     en la raiz del proyecto.
        """
        # Solo cargar una vez, ignorar llamadas posteriores
        if self._cargado:
            return

        ruta_env = ruta_env or str(RUTA_BASE / ".env")
        # Cargar variables del archivo .env al entorno de proceso
        load_dotenv(ruta_env)

        self._cargar_desde_entorno()
        self._cargado = True

    def _cargar_desde_entorno(self) -> None:
        """Extrae valores desde variables de entorno."""
        # Identidad del agente
        self.agente_id = os.getenv("AGENT_ID", "")
        self.pbx_id = os.getenv("PBX_ID", "")
        self.empresa_id = os.getenv("EMPRESA_ID", "")
        self.token_registro = os.getenv("TOKEN_REGISTRO", "")
        self.intervalo_heartbeat = int(os.getenv("INTERVALO_HEARTBEAT", "30"))
        self.nivel_log = os.getenv("NIVEL_LOG", "INFO")

        # Configuracion de conexion a Asterisk AMI
        self.ami.host = os.getenv("AMI_HOST", "127.0.0.1")
        self.ami.puerto = int(os.getenv("AMI_PORT", "5038"))
        self.ami.usuario = os.getenv("AMI_USUARIO", "")
        self.ami.secreto = os.getenv("AMI_SECRETO", "")
        self.ami.timeout_accion = float(os.getenv("TIMEOUT_ACCION", "5.0"))
        self.ami.timeout_conexion = float(os.getenv("TIMEOUT_CONEXION", "10.0"))
        self.ami.timeout_lectura = float(os.getenv("TIMEOUT_LECTURA", "30.0"))

        # URL del backend central donde se envian los eventos
        url_backend = os.getenv("BACKEND_URL", "")
        self.backend.url = url_backend

        # Configuracion del buffer offline SQLite
        ruta_buffer = os.getenv("RUTA_BUFFER", "/tmp/callmetric/buffer.db")
        self.buffer.ruta = ruta_buffer
        self.buffer.tamano_maximo = int(os.getenv("TAMANO_MAXIMO_BUFFER", "10000"))

        # Configuracion de reportes CDR desde MySQL de Asterisk
        self.cdr.db_host = os.getenv("CDR_DB_HOST", "localhost")
        self.cdr.db_port = int(os.getenv("CDR_DB_PORT", "3306"))
        self.cdr.db_name = os.getenv("CDR_DB_NAME", "asteriskcdrdb")
        self.cdr.db_user = os.getenv("CDR_DB_USER", "")
        self.cdr.db_password = os.getenv("CDR_DB_PASSWORD", "")
        self.cdr.intervalo_reporte = int(os.getenv("CDR_REPORT_INTERVAL", "90"))
        self.cdr.activo = os.getenv("CDR_REPORT_ACTIVE", "false").lower() == "true"

    def obtener_como_dict(self) -> Dict[str, Any]:
        """Retorna la configuracion como diccionario (sin secretos).

        Util para logging o depuracion. Omite el campo secreto.
        """
        return {
            "agente_id": self.agente_id,
            "ami_host": self.ami.host,
            "ami_puerto": self.ami.puerto,
            "ami_usuario": self.ami.usuario,
            "intervalo_heartbeat": self.intervalo_heartbeat,
            "nivel_log": self.nivel_log,
        }
