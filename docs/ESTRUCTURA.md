# Estructura del Proyecto - CallMetric Pro Agent

Descripcion detallada de cada carpeta y archivo del agente Python.

```
prueba_agente/
├── .env
├── requirements.txt
├── config/
├── docs/
├── src/
│   ├── main.py
│   ├── core/
│   ├── factories/
│   ├── connectors/
│   ├── iterators/
│   ├── strategies/
│   ├── commands/
│   ├── facade/
│   ├── buffer/
│   ├── transmitters/
│   └── health/
└── .venv/
```

---

## Raiz del proyecto

### `.env`
**Proposito:** Variables de entorno para configurar la conexion AMI, backend y comportamiento del agente.

**Contenido principal:**
| Variable | Descripcion |
|---|---|
| `AGENT_ID` | UUID v4 unico que identifica esta instancia del agente |
| `AMI_HOST` | Direccion IP del servidor Asterisk |
| `AMI_PORT` | Puerto TCP del AMI (default: 5038) |
| `AMI_USUARIO` | Usuario de autenticacion AMI |
| `AMI_SECRETO` | Contrasena de autenticacion AMI |
| `BACKEND_URL` | URL del backend o API de prueba |
| `INTERVALO_HEARTBEAT` | Segundos entre heartbeats |
| `NIVEL_LOG` | Nivel de logging (DEBUG, INFO, WARNING, ERROR) |
| `RUTA_BUFFER` | Ruta del archivo SQLite para buffer offline |
| `TAMANO_MAXIMO_BUFFER` | Maximo de eventos en buffer antes de sobrescribir |

**Dependencias:** `python-dotenv` carga este archivo al iniciar.

---

### `requirements.txt`
**Proposito:** Lista de dependencias Python necesarias para ejecutar el agente.

**Dependencias:**
| Paquete | Version | Proposito |
|---|---|---|
| `asyncio-manager` | 1.0.1 | Cliente AMI asincrono para Asterisk |
| `httpx` | >=0.27.0 | Cliente HTTP asincrono con reintentos y TLS |
| `websockets` | >=12.0 | Cliente WebSocket para eventos en tiempo real |
| `aiosqlite` | >=0.20.0 | SQLite asincrono para buffer offline |
| `python-dotenv` | >=1.0.0 | Carga de variables de entorno desde `.env` |
| `psutil` | >=5.9.0 | Metricas del sistema (CPU, RAM) |

**Instalacion:** `pip install -r requirements.txt`

---

### `config/default.yaml`
**Proposito:** Configuracion por defecto del agente en formato YAML.

**Estructura:**
```yaml
agente:
  id: ""
  intervalo_heartbeat: 30

ami:
  host: "127.0.0.1"
  puerto: 5038
  timeout_accion: 5.0
  intentos_reconexion: 10

backend:
  url: ""
  timeout_peticion: 30.0

buffer:
  ruta: "/tmp/callmetric/buffer.db"
  tamano_maximo: 10000
  tamano_lote: 50

transmision:
  modo: "http"

monitoreo:
  intervalo_metricas: 60
```

**Dependencias:** Los valores de `.env` sobrescriben estos valores por defecto.

---

## `src/` — Codigo fuente del agente

### `src/__init__.py`
**Proposito:** Marca `src/` como paquete Python. Contiene docstring con la descripcion general del proyecto.

---

### `src/main.py`
**Proposito:** Punto de entrada del agente. Contiene la clase `AgenteCallMetric` que orquesta el ciclo de vida completo.

**Clases:**
- `AgenteCallMetric` — Inicializa configuracion, logger y motor de ingestion. Maneja senales del sistema y ejecuta el bucle principal.

**Flujo:**
1. Carga `.env` via `ConfiguracionAgente.cargar()`
2. Configura logger JSON
3. Crea `MotorIngestion` y llama a `iniciar()`
4. Espera hasta recibir `Ctrl+C` o senal de detencion
5. Llama a `detener()` para cierre ordenado

**Ejecucion:** `python3 -m src.main` (desde la raiz `prueba_agente/`)

---

## `src/core/` — Patron Singleton

### `src/core/config.py`
**Proposito:** Singleton que centraliza toda la configuracion del agente. Carga `.env` con `python-dotenv` y provee acceso estructurado.

**Clases:**
| Clase | Descripcion |
|---|---|
| `ConfiguracionAgente` | Singleton principal. Metodo `cargar()` lee `.env`. Propiedades: `agente_id`, `ami`, `backend`, `buffer` |
| `ConfiguracionAMI` | Dataclass: host, puerto, usuario, secreto, timeouts, reconexion |
| `ConfiguracionBackend` | Dataclass: url, timeout, intentos maximos |
| `ConfiguracionBuffer` | Dataclass: ruta, tamano maximo, lote, intervalo flush |
| `ConfiguracionTransmision` | Dataclass: modo, compresion |

**Metodo clave:** `obtener_instancia()` — retorna la unica instancia del singleton.

**Dependencias:** `python-dotenv`, `dataclasses`

---

### `src/core/logger.py`
**Proposito:** Singleton que configura el sistema de logging con formato JSON estructurado.

**Clases:**
| Clase | Descripcion |
|---|---|
| `FormateadorJSON` | Formatea cada linea de log como un objeto JSON valido |
| `LoggerEstructurado` | Singleton. Configura logger con salida a consola y archivo rotativo |

**Formato de salida:**
```json
{"timestamp": "2026-05-28T08:00:00", "nivel": "INFO", "modulo": "callmetric", "mensaje": "Agente iniciado", "contexto": {"host": "192.168.1.1"}}
```

**Metodos:** `info()`, `error()`, `advertencia()`, `depuracion()` — todos aceptan `contexto` opcional.

---

### `src/core/contexto.py`
**Proposito:** Singleton que mantiene el estado global del runtime del agente: identificador, estado, metricas.

**Clases:**
| Clase | Descripcion |
|---|---|
| `EstadoAgente` | Enum: DETENIDO, INICIANDO, ACTIVO, MODO_SEGURO, ERROR, DETENIENDOSE |
| `MetricasInternas` | Dataclass: eventos_procesados, transmitidos, encolados, perdidos, errores_conexion |
| `ContextoEjecucion` | Singleton. Almacena agente_id, pbx_host, estado, metricas |

**Metodos clave:**
- `inicializar(agente_id, pbx_host)` — establece valores iniciales
- `activar_modo_seguro()` — desactiva transmisiones (ante 401/403)
- `tiempo_activo()` — segundos desde el inicio del agente
- `esta_activo()` / `esta_en_modo_seguro()` — consultas de estado

---

## `src/factories/` — Patron Factory Method

### `src/factories/base.py`
**Proposito:** Define la interfaz abstracta para todas las fabricas de conectores.

**Clase:** `FabricaAbstracta` (ABC)
- Metodo abstracto: `crear_conector(tipo_fuente, **parametros)`
- Permite extender el sistema con nuevos tipos de conectores sin modificar codigo existente.

---

### `src/factories/event_source_factory.py`
**Proposito:** Fabrica concreta que crea conectores segun el tipo de fuente solicitado.

**Clase:** `FabricaFuenteEventos`
- Atributo: `CONECTORES_DISPONIBLES = {"ami": ConectorAMI}`
- Metodo: `crear_conector(tipo_fuente, **parametros)` — instancia y retorna el conector

**Extensibilidad:** Para agregar un nuevo conector (CDR, CEL), solo hay que anadirlo al diccionario `CONECTORES_DISPONIBLES`.

---

## `src/connectors/` — Conectores a fuentes de datos

### `src/connectors/base.py`
**Proposito:** Define la interfaz abstracta que todos los conectores deben implementar.

**Clase:** `ConectorBase` (ABC)
- `conectar()` — establece conexion con la fuente
- `desconectar()` — cierra conexion
- `leer_eventos()` — iterador asincrono de eventos
- `esta_conectado` — propiedad booleana

---

### `src/connectors/ami_connector.py`
**Proposito:** Conector que envuelve `CallManager` de `asyncio-manager` para capturar eventos AMI de Asterisk.

**Clase:** `ConectorAMI`
- Envuelve `asyncio_manager.CallManager`
- Registra 4 eventos de ciclo de vida de llamada:
  | Evento | Datos extraidos |
  |---|---|
  | `NewChannel` | id_unico, canal, origen, destino, contexto |
  | `Dial` | id_unico, origen, destino, canal_origen, canal_destino |
  | `Answer` | id_unico, canal, origen |
  | `Hangup` | id_unico, canal, origen, duracion, causa |
- Usa una cola asincrona (`asyncio.Queue`) para pasar eventos al pipeline

**Eventos NO capturados:** NewState, Bridge, Unbridge, VarSet, MusicOnHold, y todos los demas eventos internos de Asterisk. Solo interesan las 4 etapas del ciclo de vida de una llamada.

---

## `src/iterators/` — Patron Iterator

### `src/iterators/base.py`
**Proposito:** Define la interfaz abstracta para iteradores asincronos.

**Clase:** `IteradorBase` (ABC)
- `iterar()` — retorna `AsyncIterator[Dict]`
- `detener()` — detiene la iteracion

---

### `src/iterators/ami_stream.py`
**Proposito:** Iterador que consume eventos desde el conector AMI y los entrega uno a uno al pipeline de procesamiento.

**Clase:** `StreamAMI`
- `iterar()` — itera sobre `fuente.leer_eventos()`
- `detener()` — detiene la iteracion

**Uso:**
```python
async for evento in stream.iterar():
    comando = ComandoProcesarEvento(evento)
    await comando.ejecutar()
```

---

## `src/strategies/` — Patron Strategy

### `src/strategies/base.py`
**Proposito:** Define las tres interfaces abstractas de estrategia.

**Interfaces:**
| Interfaz | Metodo | Proposito |
|---|---|---|
| `EstrategiaNormalizacion` | `normalizar(evento)` | Transforma eventos crudos a esquema unificado |
| `EstrategiaReintento` | `calcular_demora(intento)` | Calcula tiempo de espera entre reintentos |
| `EstrategiaTransmision` | `transmitir(eventos, agente_id)` | Envia eventos al backend |

---

### `src/strategies/normalization.py`
**Proposito:** Normaliza eventos AMI y consolida informacion de llamadas. Acumula eventos parciales por `id_unico` y solo emite un registro cuando la llamada finaliza (Hangup).

**Clases:**
| Clase | Descripcion |
|---|---|
| `LlamadaEnProgreso` | Acumula estado de una llamada: origen, destino, canal, duracion, causa. Metodo `actualizar_con(evento)` y `consolidar(agente_id)` |
| `NormalizadorAMI` | Estrategia concreta. Mantiene diccionario de llamadas activas. Retorna `None` para eventos parciales, `Dict` consolidado en Hangup |

**Comportamiento:**
- NewChannel → crea/actualiza `LlamadaEnProgreso` → retorna `None`
- Dial → actualiza origen/destino → retorna `None`
- Answer → marca `respondio=true` → retorna `None`
- Hangup → actualiza duracion/causa → consolida → retorna Dict completo → elimina llamada del diccionario

**Registro consolidado:**
```json
{
  "event_id": "sha256...",
  "timestamp": "2026-05-28T08:00:00",
  "fuente": "ami",
  "agente_id": "uuid",
  "tipo": "llamada_completa",
  "datos": {
    "id_unico": "12345.6789",
    "origen": "100",
    "destino": "200",
    "canal": "SIP/100-abc",
    "contexto": "from-internal",
    "respondio": true,
    "duracion_segundos": "45",
    "causa": "Normal Clearing"
  }
}
```

---

### `src/strategies/retry_policy.py`
**Proposito:** Implementa algoritmos de reintento para operaciones fallidas.

**Clases:**
| Clase | Descripcion |
|---|---|
| `BackoffExponencial` | Incrementa tiempo exponencialmente con jitter aleatorio. Configurable: demora_inicial, demora_maxima, factor |
| `SinReintento` | No reintenta, retorna 0 siempre |

**Formula Backoff:** `min(demora_inicial * factor^(intento-1), demora_maxima) + jitter`

---

### `src/strategies/transmission.py`
**Proposito:** Implementa estrategias de transmision de eventos al backend.

**Clases:**
| Clase | Descripcion |
|---|---|
| `EstrategiaHTTPBatch` | Envia lotes de eventos via HTTP POST con header `X-Agent-ID`. Simula envio si no hay URL configurada |
| `EstrategiaWSRealtime` | Envia eventos individuales via WebSocket. Requiere conexion persistente |

**Modos de transmision:**
- **HTTP Batch:** Para sincronizacion historica y recuperacion offline. Envia en lotes de N eventos.
- **WebSocket Realtime:** Para eventos en vivo con latencia <500ms. Usa conexion persistente.

---

## `src/commands/` — Patron Command

### `src/commands/base.py`
**Proposito:** Define la interfaz abstracta para todos los comandos.

**Clase:** `ComandoBase` (ABC)
- `ejecutar()` → `bool` — ejecuta la operacion
- `deshacer()` → `None` — revierte la operacion (opcional)

---

### `src/commands/process_event.py`
**Proposito:** Comando que procesa un evento del stream. Normaliza usando `NormalizadorAMI` y encola el resultado en `GestorColas`.

**Clase:** `ComandoProcesarEvento`
- Recibe: `evento_crudo`, `normalizador`, `gestor_colas`
- `ejecutar()`:
  1. Llama a `normalizador.normalizar(evento_crudo)`
  2. Si retorna `None` (evento parcial), termina sin encolar
  3. Si retorna Dict (llamada completa), lo encola en `gestor_colas`
  4. Incrementa contadores de metricas

---

### `src/commands/flush_buffer.py`
**Proposito:** Comando que sincroniza el buffer SQLite con el backend. Lee lotes de eventos pendientes, los transmite y solo elimina tras confirmacion.

**Clase:** `ComandoVaciarBuffer`
- Recibe: `almacen_buffer`, `estrategia_transmision`, `tamano_lote`
- `ejecutar()`:
  1. Cuenta eventos pendientes en buffer
  2. Obtiene lote de N eventos
  3. Transmite via estrategia
  4. Si exito, marca como enviados en SQLite
  5. Repite hasta vaciar buffer

---

### `src/commands/send_heartbeat.py`
**Proposito:** Comando que envia heartbeat al backend para mantener la conexion activa y validar que el agente no haya sido revocado.

**Clase:** `ComandoEnviarHeartbeat`
- Recibe: `gestor_llamadas`, `cliente_http`, `intervalo`
- `ejecutar()`:
  1. Envia Ping al AMI para verificar salud local
  2. Envia POST al backend con metricas y estado
  3. Si recibe 401/403, activa modo seguro
  4. Actualiza timestamp del ultimo heartbeat

---

## `src/facade/` — Patron Facade

### `src/facade/ingestion_engine.py`
**Proposito:** Fachada principal que orquesta todos los componentes del agente. Expone API simple: `iniciar()`, `detener()`, `obtener_estado()`.

**Clase:** `MotorIngestion`

**Componentes que orquesta:**
| Componente | Variable | Proposito |
|---|---|---|
| ConectorAMI | `conector` | Captura eventos AMI |
| StreamAMI | `stream` | Stream asincrono |
| NormalizadorAMI | `normalizador` | Normaliza y consolida |
| AlmacenSQLite | `almacen` | Buffer offline |
| GestorColas | `gestor_colas` | Cola con backpressure |
| ClienteHTTP | `cliente_http` | HTTP client |
| ClienteWebSocket | `cliente_ws` | WS client |
| EstrategiaHTTPBatch | `estrategia_http` | Tx por lotes |
| EstrategiaWSRealtime | `estrategia_ws` | Tx en tiempo real |
| HeartbeatManager | `heartbeat` | Heartbeat periodico |
| AutoMonitor | `auto_monitor` | Metricas internas |

**Metodo `iniciar()` — Secuencia:**
1. Inicializa contexto (agente_id, pbx_host)
2. Inicializa buffer SQLite y cliente HTTP
3. Crea conector AMI via Factory y conecta
4. Crea stream de eventos
5. Inicia gestor de colas
6. Inicia heartbeat y auto-monitoreo
7. Cambia estado a ACTIVO
8. Inicia bucle de procesamiento de eventos

**Metodo `detener()` — Secuencia (inversa):**
1. Cancelar bucle de procesamiento
2. Detener heartbeat y monitor
3. Detener gestor de colas
4. Desconectar AMI
5. Cerrar clientes HTTP y WS
6. Cerrar buffer SQLite
7. Cambiar estado a DETENIDO

**Metodo `obtener_estado()`:** Retorna diccionario con estado, metricas, buffer pendientes.

---

## `src/buffer/` — Buffer offline

### `src/buffer/sqlite_store.py`
**Proposito:** Almacen persistente basado en SQLite asincrono (aiosqlite) para buffer offline.

**Clase:** `AlmacenSQLite`
- `inicializar()` — crea tabla `eventos` con indices
- `guardar(evento)` — inserta evento con estado `pendiente`
- `obtener_lote(cantidad)` — recupera N eventos pendientes
- `marcar_como_enviados(ids)` — cambia estado a `enviado`
- `contar_pendientes()` — cuenta eventos no transmitidos
- `limpiar_enviados(dias)` — elimina eventos enviados antiguos
- `cerrar()` — cierra conexion

**Esquema SQLite:**
```sql
CREATE TABLE eventos (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    tipo TEXT NOT NULL,
    datos TEXT NOT NULL,
    estado TEXT DEFAULT 'pendiente',
    creado_en REAL NOT NULL,
    enviado_en REAL
);
```

---

### `src/buffer/queue_manager.py`
**Proposito:** Gestiona la cola de eventos pendientes con soporte para backpressure. Decide si transmitir inmediatamente o almacenar en buffer SQLite.

**Clase:** `GestorColas`
- `iniciar()` — crea tarea asincrona de procesamiento
- `detener()` — detiene procesamiento y vacia cola
- `encolar(evento)` — agrega evento a la cola (o buffer directo si cola llena)
- `_procesar_cola()` — bucle que procesa eventos: transmite si hay red, guarda en buffer si no
- `_intentar_vaciar_buffer()` — intenta sincronizar buffer periodicamente

**Logica de decision:**
```
Evento llega → Cola asincrona
  → ¿Cola llena? → Guardar directo en buffer SQLite
  → ¿Hay red y agente activo? → Transmitir via estrategia
  → ¿Sin red? → Guardar en buffer SQLite
```

---

## `src/transmitters/` — Clientes de red

### `src/transmitters/http_client.py`
**Proposito:** Cliente HTTP asincrono usando `httpx` con soporte TLS 1.3, reintentos con backoff y manejo de errores.

**Clase:** `ClienteHTTP`
- `iniciar()` — crea `httpx.AsyncClient` con timeout
- `cerrar()` — cierra cliente
- `enviar_peticion(metodo, url, datos, cabeceras, timeout)` → `bool`

**Caracteristicas:**
- Reintentos automaticos con `BackoffExponencial`
- Timeout configurable por peticion
- Deteccion de 401/403 → activa modo seguro
- Header `User-Agent: CallMetric-Agent/1.0`

---

### `src/transmitters/ws_client.py`
**Proposito:** Cliente WebSocket asincrono para transmision en tiempo real de eventos con reconexion automatica.

**Clase:** `ClienteWebSocket`
- `conectar(agente_id)` — establece conexion con header `X-Agent-ID`
- `cerrar()` — cierra conexion
- `enviar_evento(evento, agente_id)` → `bool`
- `reconectar(agente_id)` — reintenta conexion

**Caracteristicas:**
- Reconexion automatica con backoff exponencial
- Ping interval para mantener conexion viva
- Hasta `max_intentos_conexion` reintentos

---

## `src/health/` — Monitoreo de salud

### `src/health/heartbeat.py`
**Proposito:** Gestiona el envio periodico de heartbeats al backend en un bucle asincrono.

**Clase:** `HeartbeatManager`
- `iniciar()` — crea tarea con bucle de heartbeats
- `detener()` — cancela tarea
- `_bucle_heartbeat()` — ejecuta comando heartbeat cada `intervalo` segundos

---

### `src/health/self_monitor.py`
**Proposito:** Recolecta metricas internas del agente (CPU, RAM, cola, buffer) y las registra en el log.

**Clase:** `AutoMonitor`
- `iniciar()` — inicia bucle de recoleccion
- `detener()` — detiene bucle
- `_recolectar_metricas()` — obtiene: estado, eventos procesados, buffer pendientes, CPU%, RAM MB

**Metricas recolectadas:**
- Estado del agente
- Tiempo activo
- Eventos procesados, transmitidos, encolados, perdidos
- Errores de conexion
- Buffer pendientes
- CPU % y RAM MB (via `psutil`)

---

## `docs/` — Documentacion

### `docs/README.md`
Documentacion principal del proyecto: instalacion, configuracion, uso, arquitectura, patrones, stack tecnologico, API endpoints.

### `docs/ESTRUCTURA.md`
Este archivo. Descripcion detallada de cada carpeta y archivo del proyecto.

### `docs/diagramas/`
Diagramas PlantUML de la arquitectura:
| Archivo | Descripcion |
|---|---|
| `arquitectura.puml` / `.png` | Componentes del agente y sus relaciones |
| `clases.puml` / `.png` | Jerarquia de clases y patrones de diseno |
| `flujo_llamada.puml` / `.png` | Secuencia completa de una llamada |
| `despliegue.puml` / `.png` | Nodos fisicos y conexiones de red |

---

## `prueba_api/` — API de prueba (referencia cruzada)

Ubicada en `../prueba_api/`. No es parte del agente Python pero se usa para desarrollo local.

### `package.json`
Proyecto Node.js con Express, dotenv, cors. Scripts: `start` y `dev`.

### `.env`
`PUERTO=3000`

### `src/index.js`
Servidor Express con 5 endpoints:
| Metodo | Ruta | Proposito |
|---|---|---|
| POST | `/api/v1/agent/activate` | Activa agente |
| POST | `/api/v1/agent/heartbeat` | Recibe heartbeat |
| POST | `/api/v1/agent/events` | Recibe llamadas consolidadas |
| GET | `/health` | Health check |

Muestra cada llamada en consola con formato:
```
╔══════════════════════════════════════════════╗
║  ✅ LLAMADA Completada                      ║
╚══════════════════════════════════════════════╝
  ID Unico   : 1234567890.abcdef
  Origen     : 100
  Destino    : 200
  Duracion   : 45s
  Causa      : Normal Clearing
```
