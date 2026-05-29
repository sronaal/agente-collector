"""Punto de entrada del agente CallMetric Pro.

Inicializa la configuracion, el logger y el motor de
ingestion, luego ejecuta el bucle principal asincrono
hasta que se recibe una senal de detencion.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Modulo para manejo de tareas asincronas y event loop
import asyncio
# Manejo de senales del sistema operativo (SIGINT, SIGTERM)
import signal
# Acceso a sys.stderr para errores fatales
import sys
# Tipos para firmas de metodos con type hints
from typing import Any, Optional, Set

# Configuracion singleton del agente
from src.core.config import ConfiguracionAgente
# Logger estructurado singleton
from src.core.logger import LoggerEstructurado
# Fachada del motor de ingestion que orquesta todos los componentes
from src.facade.ingestion_engine import MotorIngestion


class AgenteCallMetric:
    """Clase principal que orquesta el ciclo de vida del agente.

    Se encarga de inicializar componentes, manejar senales
    del sistema operativo y ejecutar el bucle principal.

    Uso:
        agente = AgenteCallMetric()
        await agente.ejecutar()
    """

    def __init__(self) -> None:
        # Configuracion singleton cargada desde .env
        self.config = ConfiguracionAgente.obtener_instancia()
        # Logger estructurado singleton (aun no configurado)
        self.logger = LoggerEstructurado.obtener_instancia()
        # Motor de ingestion (None hasta ejecutar())
        self.motor: Optional[MotorIngestion] = None
        # Conjunto de tareas asincronas del agente
        self._tareas: Set[asyncio.Task] = set()

    async def ejecutar(self) -> None:
        """Inicia la configuracion y ejecuta el agente.

        Flujo:
        1. Carga configuracion desde .env
        2. Configura el logger estructurado
        3. Inicia el motor de ingestion
        4. Espera senal de detencion
        5. Detiene el motor de ingestion
        """
        # Paso 1: Cargar variables de entorno desde archivo .env
        self.config.cargar()

        # Paso 2: Configurar el sistema de logging con formato JSON
        self.logger.configurar(nivel=self.config.nivel_log)

        # Banner de inicio del agente en el log
        self.logger.info("=" * 50)
        self.logger.info(
            "CallMetric Pro Agent v1.0.0",
            contexto={"agente_id": self.config.agente_id}
        )
        self.logger.info("=" * 50)

        # Paso 3: Crear el motor de ingestion con la configuracion cargada
        self.motor = MotorIngestion(config=self.config)

        try:
            # Iniciar todos los componentes del motor
            await self.motor.iniciar()

            # Verificar que el agente arranco correctamente
            estado = await self.motor.obtener_estado()
            self.logger.info(
                "Agente listo para procesar eventos",
                contexto={
                    "estado": estado["estado"],
                    "pbx": estado["pbx_host"],
                }
            )

            # Bucle principal: mantener vivo el proceso
            # Las tareas internas (procesamiento, heartbeat, monitoreo)
            # se ejecutan en segundo plano como asyncio.Tasks
            while True:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            self.logger.info("Recibida senal de cancelacion")

        except KeyboardInterrupt:
            self.logger.info("Recibida interrupcion de teclado")

        except Exception as error:
            self.logger.error(
                "Error fatal en el agente",
                contexto={"error": str(error)}
            )
            raise

        finally:
            # Garantizar detencion limpia incluso en caso de error
            if self.motor is not None:
                await self.motor.detener()

            # Mostrar resumen final con metricas de la ejecucion
            estado_final = await self.motor.obtener_estado() if self.motor else {}
            self.logger.info(
                "Agente detenido",
                contexto={
                    "eventos_procesados": estado_final.get("metricas", {}).get(
                        "eventos_procesados", 0
                    ),
                    "eventos_transmitidos": estado_final.get("metricas", {}).get(
                        "eventos_transmitidos", 0
                    ),
                }
            )


def main() -> None:
    """Funcion principal de entrada al agente.

    Configura el event loop con manejo de senales
    y ejecuta el agente.
    """
    try:
        # Crear instancia del agente y ejecutar el event loop
        agente = AgenteCallMetric()
        asyncio.run(agente.ejecutar())
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(f"Error fatal: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
