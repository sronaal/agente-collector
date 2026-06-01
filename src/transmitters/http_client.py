"""Cliente HTTP asincrono para comunicacion con el backend.

Implementa peticiones HTTP usando la libreria httpx con
soporte para TLS 1.3, reintentos configurables, timeouts
precisos y manejo de errores.
"""

# Habilitar evaluacion diferida de type hints (Python 3.7+)
from __future__ import annotations

# Tipos para firmas de metodos con type hints
from typing import Any, Dict, Optional

# Cliente HTTP asincrono con soporte para HTTP/2 y TLS
import httpx

# Logger estructurado singleton para registro de eventos
from src.core.logger import LoggerEstructurado
# Estrategias de reintento con backoff exponencial
from src.strategies.retry_policy import BackoffExponencial, EstrategiaReintento


class ClienteHTTP:
    """Cliente HTTP asincrono con reintentos y TLS.

    Envia peticiones al backend central usando HTTP/HTTPS
    con verificacion de certificados, timeouts y reintentos
    automaticos con backoff exponencial.

    Args:
        timeout_peticion: Timeout por defecto en segundos.
        verificar_tls: Si verifica el certificado TLS.
        max_intentos: Numero maximo de reintentos.
        estrategia_reintento: Estrategia de reintento a utilizar.
    """

    def __init__(
        self,
        timeout_peticion: float = 30.0,
        verificar_tls: bool = True,
        max_intentos: int = 3,
        estrategia_reintento: Optional[EstrategiaReintento] = None,
    ) -> None:
        # Timeout por defecto para todas las peticiones HTTP
        self.timeout = timeout_peticion
        # Si se debe verificar el certificado TLS del backend
        self.verificar_tls = verificar_tls
        # Numero maximo de reintentos antes de declarar fallo
        self.max_intentos = max_intentos
        # Estrategia de backoff para calcular demora entre reintentos
        self.estrategia = estrategia_reintento or BackoffExponencial(
            demora_inicial=1.0,
            demora_maxima=10.0,
        )
        # Cliente httpx asincrono (None hasta iniciar())
        self._cliente: Optional[httpx.AsyncClient] = None
        # Logger singleton para registro de eventos
        self.logger = LoggerEstructurado.obtener_instancia()

    async def iniciar(self) -> None:
        """Inicializa el cliente HTTP asincrono."""
        # Crear cliente httpx con configuracion base
        self._cliente = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            verify=self.verificar_tls,
            headers={
                "User-Agent": "CallMetric-Agent/1.0",
            },
        )
        self.logger.depuracion("Cliente HTTP inicializado")

    async def cerrar(self) -> None:
        """Cierra el cliente HTTP y libera recursos."""
        if self._cliente is not None:
            # Cerrar el pool de conexiones HTTP
            await self._cliente.aclose()
            self._cliente = None
            self.logger.depuracion("Cliente HTTP cerrado")

    async def enviar_peticion(
        self,
        metodo: str,
        url: str,
        datos: Optional[str] = None,
        cabeceras: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> bool:
        """Envia una peticion HTTP con reintentos automaticos.

        Args:
            metodo: Metodo HTTP (GET, POST, PUT, DELETE).
            url: URL de destino.
            datos: Cuerpo de la peticion como string JSON.
            cabeceras: Cabeceras HTTP adicionales.
            timeout: Timeout especifico para esta peticion.

        Returns:
            True si la peticion fue exitosa (2xx).
        """
        if self._cliente is None:
            self.logger.error("Cliente HTTP no inicializado")
            return False

        # Almacenar el ultimo error para mostrarlo si todos los intentos fallan
        ultimo_error = None

        # Bucle de reintentos con backoff exponencial entre cada intento
        for intento in range(1, self.max_intentos + 1):
            try:
                # Usar timeout especifico o el timeout por defecto.
                # timeout=None significa sin timeout (httpx espera indefinido).
                tiempo_limite = timeout if timeout is not None else self.timeout
                respuesta = await self._cliente.request(
                    method=metodo.upper(),
                    url=url,
                    content=datos,
                    headers=cabeceras,
                    timeout=tiempo_limite,
                )

                # 401 o 403 = autenticacion rechazada, no reintentar
                if respuesta.status_code == 401 or respuesta.status_code == 403:
                    self._manejar_rechazo_autenticacion(respuesta.status_code)
                    return False

                # Cualquier codigo 2xx se considera exito
                if respuesta.is_success:
                    return True

                # Error HTTP recuperable (5xx, 4xx distintos de auth)
                ultimo_error = (
                    f"HTTP {respuesta.status_code}: {respuesta.text[:200]}"
                )

            except httpx.TimeoutException as error:
                ultimo_error = f"Timeout: {error}"
            except httpx.RequestError as error:
                ultimo_error = f"Error de conexion: {error}"
            except Exception as error:
                ultimo_error = f"Error inesperado: {error}"

            # Esperar con backoff exponencial antes del siguiente intento
            if intento < self.max_intentos:
                demora = self.estrategia.calcular_demora(intento)
                self.logger.advertencia(
                    f"Reintentando peticion ({intento}/{self.max_intentos})",
                    contexto={
                        "url": url,
                        "metodo": metodo,
                        "demora": f"{demora:.1f}s",
                        "error": ultimo_error,
                    }
                )
                import asyncio
                await asyncio.sleep(demora)

        # Todos los intentos fallaron, loggear y retornar False
        self.logger.error(
            "Peticion HTTP fallida tras todos los intentos",
            contexto={
                "url": url,
                "metodo": metodo,
                "intentos": self.max_intentos,
                "ultimo_error": ultimo_error,
            }
        )
        return False

    def _manejar_rechazo_autenticacion(self, codigo: int) -> None:
        """Maneja rechazos de autenticacion (401/403).

        Activa el modo seguro del agente cuando el backend
        rechaza la conexion.

        Args:
            codigo: Codigo de estado HTTP (401 o 403).
        """
        from src.core.contexto import ContextoEjecucion
        contexto = ContextoEjecucion.obtener_instancia()
        contexto.activar_modo_seguro()

        self.logger.error(
            "Autenticacion rechazada por el backend",
            contexto={
                "codigo_http": codigo,
                "agente_id": contexto.agente_id,
                "accion": "modo_seguro_activado",
            }
        )
