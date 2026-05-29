"""Implementacion del patron Factory Method para conectores.

La fabrica concreta crea conectores segun el tipo de fuente
de eventos, permitiendo extender el agente con nuevos tipos
de conectores sin modificar el codigo existente.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Conector AMI que se crea cuando tipo_fuente="ami"
from src.connectors.ami_connector import ConectorAMI
# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Interfaz abstracta que esta clase implementa
from src.factories.base import FabricaAbstracta


class FabricaFuenteEventos(FabricaAbstracta):
    """Fabrica concreta que crea conectores segun el tipo de fuente.

    Soporta la creacion de conectores AMI. En futuras versiones
    se agregaran conectores para CDR, CEL y metricas del sistema.

    Uso:
        fabrica = FabricaFuenteEventos()
        conector = await fabrica.crear_conector("ami", host="...")
    """

    # Diccionario que mapea tipo de fuente a clase concreta
    CONECTORES_DISPONIBLES = {
        "ami": ConectorAMI,
    }

    def __init__(self) -> None:
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def crear_conector(self, tipo_fuente: str, **parametros: Any) -> Any:
        """Crea un conector del tipo solicitado.

        Args:
            tipo_fuente: Tipo de conector a crear ("ami").
            **parametros: Argumentos para inicializar el conector.

        Returns:
            Instancia del conector creado.

        Raises:
            ValueError: Si el tipo de fuente no esta soportado.
        """
        # Buscar la clase concreta en el diccionario de conectores disponibles
        clase_conector = self.CONECTORES_DISPONIBLES.get(tipo_fuente.lower())

        if clase_conector is None:
            # Construir mensaje de error con las fuentes disponibles
            fuentes = ", ".join(self.CONECTORES_DISPONIBLES.keys())
            raise ValueError(
                f"Tipo de fuente '{tipo_fuente}' no soportado. "
                f"Fuentes disponibles: {fuentes}"
            )

        self.logger.info(
            f"Creando conector de tipo: {tipo_fuente}",
            contexto={"tipo": tipo_fuente, "parametros": list(parametros.keys())}
        )

        # Instanciar el conector con los parametros proporcionados
        conector = clase_conector(**parametros)
        return conector
