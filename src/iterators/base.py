"""Define la interfaz abstracta para iteradores asincronos.

Los iteradores permiten procesar streams de datos
sin cargar todo en memoria, soportando pausas,
reanudacion y cancelacion segura.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para definir clases abstractas con metodos abstractos
from abc import ABC, abstractmethod
# Tipos para iteradores asincronos y firmas de metodos
from typing import Any, AsyncIterator, Dict, Optional


class IteradorBase(ABC):
    """Interfaz base para iteradores asincronos de eventos.

    Cada iterador consume datos de una fuente (AMI, archivo,
    buffer) y los expone como un flujo continuo de elementos.
    """

    @abstractmethod
    async def iterar(self) -> AsyncIterator[Dict[str, Any]]:
        """Itera sobre los elementos de la fuente de datos.

        Yields:
            Elemento procesado como diccionario.

        Raises:
            StopAsyncIteration: Cuando no hay mas datos.
        """
        ...
        yield  # pragma: no cover

    @abstractmethod
    async def detener(self) -> None:
        """Detiene la iteracion de forma segura.

        Debe cancelar recursos pendientes y esperar
        a que las tareas hijas terminen.
        """
        ...
