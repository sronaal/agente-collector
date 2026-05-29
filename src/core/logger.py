"""Modulo Singleton para el sistema de logging estructurado.

Provee un logger JSON con rotacion de archivos, formato
estructurado para ingestion en sistemas centralizados
y soporte para niveles de log configurables.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Serializacion de registros de log a formato JSON
import json
# Modulo estandar de logging de Python
import logging
# Salida estandar para el manejador de consola
import sys
# Manejo de rutas de archivos del sistema
from pathlib import Path
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional


class FormateadorJSON(logging.Formatter):
    """Formatea los registros de log como objetos JSON.

    Cada linea de log es un objeto JSON valido con los campos:
    timestamp, nivel, modulo, mensaje y contexto adicional.
    """

    def format(self, registro: logging.LogRecord) -> str:
        """Convierte un registro de log a formato JSON.

        Args:
            registro: Registro de log a formatear.

        Returns:
            Cadena JSON con el registro formateado.
        """
        entrada: Dict[str, Any] = {
            "timestamp": self.formatTime(registro, "%Y-%m-%dT%H:%M:%S"),
            "nivel": registro.levelname,
            "modulo": registro.name,
            "mensaje": registro.getMessage(),
        }

        # Incluir contexto adicional si existe en el registro
        if hasattr(registro, "contexto") and registro.contexto:
            entrada["contexto"] = registro.contexto

        # Incluir informacion de excepcion si la hay
        if registro.exc_info and registro.exc_info[0]:
            entrada["excepcion"] = self.formatException(registro.exc_info)

        return json.dumps(entrada, ensure_ascii=False)


class LoggerEstructurado:
    """Singleton que gestiona el logger principal del agente.

    Configura el logging con formato JSON y salida a consola.
    El nivel de log es configurable via .env (NIVEL_LOG).

    Uso:
        logger = LoggerEstructurado.obtener_instancia()
        logger.info("Agente iniciado", contexto={"host": "192.168.1.1"})
    """

    _instancia: Optional[LoggerEstructurado] = None

    def __init__(self) -> None:
        # Logger interno de Python (None hasta configurar())
        self._logger: Optional[logging.Logger] = None

    @classmethod
    def obtener_instancia(cls) -> LoggerEstructurado:
        """Retorna la instancia unica del singleton."""
        if cls._instancia is None:
            cls._instancia = cls()
        return cls._instancia

    def configurar(self, nivel: str = "INFO", ruta_log: Optional[str] = None) -> logging.Logger:
        """Configura el sistema de logging con formato JSON.

        Args:
            nivel: Nivel de log (DEBUG, INFO, WARNING, ERROR).
            ruta_log: Ruta opcional para archivo de log rotativo.

        Returns:
            Logger configurado para uso en toda la aplicacion.
        """
        self._logger = logging.getLogger("callmetric")
        nivel_log = getattr(logging, nivel.upper(), logging.INFO)
        self._logger.setLevel(nivel_log)

        # Evitar duplicacion de handlers si se llama configurar() varias veces
        if self._logger.handlers:
            return self._logger

        # Manejador de consola: escribe a stdout con formato JSON
        manejador_consola = logging.StreamHandler(sys.stdout)
        manejador_consola.setFormatter(FormateadorJSON())
        self._logger.addHandler(manejador_consola)

        # Manejador de archivo opcional con rotacion (10MB por archivo, 5 backups)
        if ruta_log:
            from logging.handlers import RotatingFileHandler
            ruta = Path(ruta_log)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            manejador_archivo = RotatingFileHandler(
                str(ruta), maxBytes=10*1024*1024, backupCount=5
            )
            manejador_archivo.setFormatter(FormateadorJSON())
            self._logger.addHandler(manejador_archivo)

        return self._logger

    @property
    def logger(self) -> logging.Logger:
        """Retorna el logger configurado.

        Raises:
            RuntimeError: Si el logger no ha sido configurado aun.
        """
        if self._logger is None:
            raise RuntimeError("Logger no configurado. Llame a configurar() primero.")
        return self._logger

    def info(self, mensaje: str, contexto: Optional[Dict[str, Any]] = None) -> None:
        """Registra un mensaje informativo.

        Args:
            mensaje: Mensaje a registrar.
            contexto: Diccionario opcional con contexto adicional.
        """
        extra = {"contexto": contexto} if contexto else {}
        self.logger.info(mensaje, extra=extra)

    def error(self, mensaje: str, contexto: Optional[Dict[str, Any]] = None) -> None:
        """Registra un mensaje de error.

        Args:
            mensaje: Mensaje a registrar.
            contexto: Diccionario opcional con contexto adicional.
        """
        extra = {"contexto": contexto} if contexto else {}
        self.logger.error(mensaje, extra=extra)

    def advertencia(self, mensaje: str, contexto: Optional[Dict[str, Any]] = None) -> None:
        """Registra un mensaje de advertencia.

        Args:
            mensaje: Mensaje a registrar.
            contexto: Diccionario opcional con contexto adicional.
        """
        extra = {"contexto": contexto} if contexto else {}
        self.logger.warning(mensaje, extra=extra)

    def depuracion(self, mensaje: str, contexto: Optional[Dict[str, Any]] = None) -> None:
        """Registra un mensaje de depuracion.

        Solo se muestra si el nivel de log es DEBUG.

        Args:
            mensaje: Mensaje a registrar.
            contexto: Diccionario opcional con contexto adicional.
        """
        extra = {"contexto": contexto} if contexto else {}
        self.logger.debug(mensaje, extra=extra)
