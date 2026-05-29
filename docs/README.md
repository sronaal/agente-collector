# CallMetric Pro Agent

Agente Python `on-premise` para captura, normalizacion y transmision de eventos telefonicos desde servidores **Asterisk/FreePBX** hacia la plataforma central CallMetric Pro.

## Requisitos

- Python 3.10+
- Acceso al Manager Interface (AMI) de Asterisk
- pnpm (para la API de prueba)
- Node.js 18+ (para la API de prueba)

## Instalacion

```bash
# Clonar repositorio e ingresar al directorio del agente
cd prueba_agente

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Configuracion

Editar el archivo `.env` con los datos de conexion AMI:

| Variable | Descripcion | Ejemplo |
|---|---|---|
| `AGENT_ID` | UUID unico del agente | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `AMI_HOST` | IP del servidor Asterisk | `192.168.101.100` |
| `AMI_PORT` | Puerto AMI | `5038` |
| `AMI_USUARIO` | Usuario AMI | `callmetric` |
| `AMI_SECRETO` | Contrasena AMI | `PasswordSegura123` |
| `BACKEND_URL` | URL del backend o API de prueba | `http://localhost:3000` |
| `NIVEL_LOG` | Nivel de logging | `INFO`, `WARNING`, `ERROR` |

## Uso

### 1. Iniciar la API de prueba (Node.js)

```bash
cd prueba_api
pnpm install
pnpm start
```

### 2. Iniciar el agente Python

```bash
cd prueba_agente
source .venv/bin/activate
python3 -m src.main
```

### 3. Ver resultados

La API de prueba mostrara en consola cada llamada completada:

```
╔══════════════════════════════════════════════╗
║  ✅ LLAMADA Completada                      ║
╚══════════════════════════════════════════════╝
  ID Unico   : 1234567890.abcdef
  Origen     : 100
  Destino    : 200
  Canal      : SIP/100-00000001
  Respondio  : Si
  Duracion   : 45s
  Causa      : Normal Clearing
```

## Arquitectura

### Diagramas PlantUML

Los diagramas de arquitectura estan en `docs/diagramas/`:

| Diagrama | Archivo | Contenido |
|---|---|---|
| Componentes | `arquitectura.puml` | Relaciones entre modulos y patrones |
| Clases | `clases.puml` | Jerarquia de clases y patrones de diseno |
| Secuencia | `flujo_llamada.puml` | Ciclo de vida completo de una llamada |
| Despliegue | `despliegue.puml` | Nodos fisicos y conexiones de red |

Para generar las imagenes PNG:

```bash
# Con PlantUML instalado (java + jar)
java -jar plantuml.jar docs/diagramas/*.puml
```

O usar el servidor online: `https://www.plantuml.com/plantuml/uml/...`

### Estructura del proyecto

```
prueba_agente/
├── .env                        # Variables de entorno
├── requirements.txt            # Dependencias Python
├── config/
│   └── default.yaml            # Configuracion por defecto
├── docs/
│   ├── README.md               # Esta documentacion
│   └── diagramas/
│       ├── arquitectura.puml
│       ├── clases.puml
│       ├── flujo_llamada.puml
│       └── despliegue.puml
├── src/
│   ├── main.py                 # Punto de entrada
│   ├── core/                   # Singleton
│   │   ├── config.py           # Carga .env + configuracion
│   │   ├── logger.py           # Logging estructurado JSON
│   │   └── contexto.py         # Estado global del agente
│   ├── factories/              # Factory Method
│   │   └── event_source_factory.py
│   ├── connectors/             # Conectores a fuentes de datos
│   │   └── ami_connector.py    # Conexion AMI via asyncio-manager
│   ├── iterators/              # Iterator
│   │   └── ami_stream.py       # Stream asincrono de eventos
│   ├── strategies/             # Strategy
│   │   ├── normalization.py    # Consolidacion de llamadas
│   │   ├── retry_policy.py     # Backoff exponencial
│   │   └── transmission.py     # HTTP batch / WS realtime
│   ├── commands/               # Command
│   │   ├── process_event.py    # Procesa y normaliza evento
│   │   ├── flush_buffer.py     # Sincroniza buffer offline
│   │   └── send_heartbeat.py   # Heartbeat al backend
│   ├── facade/
│   │   └── ingestion_engine.py # Orquesta todo (Facade)
│   ├── buffer/
│   │   ├── sqlite_store.py     # Persistencia SQLite
│   │   └── queue_manager.py    # Cola con backpressure
│   ├── transmitters/
│   │   ├── http_client.py      # Cliente HTTP async (httpx)
│   │   └── ws_client.py        # Cliente WebSocket async
│   └── health/
│       ├── heartbeat.py        # Heartbeat periodico
│       └── self_monitor.py     # Metricas CPU/RAM/cola
└── .venv/                      # Entorno virtual
```

## Patrones de Diseno

| Patron | Modulo | Proposito |
|---|---|---|
| **Singleton** | `core/` | Instancia unica de configuracion, logger y contexto |
| **Factory Method** | `factories/` | Creacion de conectores segun tipo de fuente |
| **Iterator** | `iterators/` | Stream asincrono de eventos sin cargar en RAM |
| **Strategy** | `strategies/` | Algoritmos intercambiables (normalizacion, reintento, transmision) |
| **Command** | `commands/` | Operaciones atomicas encolables y reintentables |
| **Facade** | `facade/` | API simple `iniciar()`, `detener()`, `estado()` |

## Tecnologias

| Componente | Tecnologia |
|---|---|
| Runtime | Python 3.10+ |
| Async | asyncio nativo |
| Conexion AMI | asyncio-manager |
| HTTP | httpx |
| WebSocket | websockets |
| Buffer | aiosqlite |
| Metricas | psutil |
| Configuracion | python-dotenv |
| Logging | logging (formato JSON) |

## API de Prueba (Node.js)

La API de prueba en `../prueba_api/` recibe los eventos del agente:

| Metodo | Ruta | Header | Proposito |
|---|---|---|---|
| `POST` | `/api/v1/agent/events` | `X-Agent-ID` | Recibe llamadas consolidadas |
| `POST` | `/api/v1/agent/heartbeat` | `X-Agent-ID` | Recibe heartbeat |
| `POST` | `/api/v1/agent/activate` | — | Activa el agente |
| `GET` | `/health` | — | Health check |

## Flujo de una llamada

```
1. Asterisk genera evento AMI (NewChannel, Dial, Answer, Hangup)
2. ConectorAMI captura y encola eventos crudos
3. NormalizadorAMI acumula eventos por id_unico de llamada
4. Al recibir Hangup, consolida toda la informacion
5. GestorColas decide:
   - Si hay conexion → transmite via HTTP/WS a la API
   - Si no hay conexion → guarda en buffer SQLite
6. Buffer se sincroniza automaticamente cuando hay red
```

## Licencia

MIT
