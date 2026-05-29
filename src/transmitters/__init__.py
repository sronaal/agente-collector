"""Modulos de transmision para envio de datos al backend.

Los transmisores gestionan la comunicacion de red con el
backend central, tanto via HTTP como WebSocket, con soporte
para TLS, reintentos y manejo de errores.
"""

# Exportar clientes de transmision para acceso publico
from src.transmitters.http_client import ClienteHTTP
from src.transmitters.ws_client import ClienteWebSocket

# Lista de simbolos publicos del modulo
__all__ = ["ClienteHTTP", "ClienteWebSocket"]
