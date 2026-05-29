"""Define la interfaz abstracta para los comandos.

El patron Command encapsula operaciones atomicas como
objetos, permitiendo encolarlas, reintentarlas y
desacoplarlas de quien las ejecuta.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para definir clases abstractas con metodos abstractos
from abc import ABC, abstractmethod
# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional


class ComandoBase(ABC):
    """Interfaz base para el patron Command.

    Cada comando encapsula una operacion atomica con
    metodos para ejecutar y opcionalmente deshacer.
    """

    @abstractmethod
    async def ejecutar(self) -> bool:
        """Ejecuta la operacion encapsulada por el comando.

        Returns:
            True si la ejecucion fue exitosa, False en caso contrario.
        """
        ...

    async def deshacer(self) -> None:
        """Deshace la operacion ejecutada (opcional).

        Por defecto no hace nada. Los comandos que soporten
        rollback deben sobrescribir este metodo.
        """
        ...
