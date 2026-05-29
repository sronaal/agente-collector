"""Define la interfaz abstracta para todos los conectores.

Los conectores son componentes que leen datos de fuentes
externas (AMI, archivos CDR, CEL, sistema) y los exponen
como streams asincronos iterables.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para definir clases abstractas con metodos abstractos
from abc import ABC, abstractmethod
# Tipos para iteradores asincronos y firmas de metodos
from typing import AsyncIterator, Any, Dict


class ConectorBase(ABC):
    """Interfaz base abstracta para todos los conectores.

    Cada conector implementa la logica especifica para
    conectarse, leer y desconectarse de su fuente de datos.
    """

    @abstractmethod
    async def conectar(self) -> None:
        """Establece la conexion con la fuente de datos.

        Raises:
            ConnectionError: Si no se puede establecer la conexion.
        """
        ...

    @abstractmethod
    async def desconectar(self) -> None:
        """Cierra la conexion con la fuente de datos.

        Debe ser seguro llamarlo aunque no haya conexion activa.
        """
        ...

    @abstractmethod
    async def leer_eventos(self) -> AsyncIterator[Dict[str, Any]]:
        """Itera sobre los eventos entrantes de forma asincrona.

        Yields:
            Diccionario con los datos del evento normalizado.

        Raises:
            ConnectionError: Si la conexion se pierde durante la lectura.
        """
        ...

    @property
    @abstractmethod
    def esta_conectado(self) -> bool:
        """Indica si el conector tiene una conexion activa.

        Returns:
            True si hay conexion activa, False en caso contrario.
        """
        ...
