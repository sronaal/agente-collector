"""Define la interfaz abstracta para las fabricas de conectores.

Todas las fabricas concretas deben implementar el metodo
crear_conector para producir instancias de conectores
segun el tipo de fuente de eventos solicitado.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para definir clases abstractas con metodos abstractos
from abc import ABC, abstractmethod
# Tipos para firmas de metodos con type hints
from typing import Any, Dict


class FabricaAbstracta(ABC):
    """Interfaz base para el patron Factory Method.

    Las fabricas concretas implementan crear_conector
    para instanciar el conector adecuado segun el tipo
    de fuente (AMI, CDR, CEL, metricas del sistema).
    """

    @abstractmethod
    async def crear_conector(self, tipo_fuente: str, **parametros: Any) -> Any:
        """Crea y retorna un conector para la fuente especificada.

        Args:
            tipo_fuente: Tipo de fuente (ami, cdr, cel, sistema).
            **parametros: Argumentos especificos del conector.

        Returns:
            Instancia del conector correspondiente al tipo.

        Raises:
            ValueError: Si el tipo de fuente no es soportado.
        """
        ...
