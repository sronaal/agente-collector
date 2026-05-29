# CallMetric Pro Agent

Agente Python on-premise para captura, normalización y transmisión de telemetría de sistemas PBX basados en Asterisk/FreePBX hacia la plataforma SaaS CallMetric Pro.

## Arquitectura

```
PBX (Asterisk)
  │
  ▼ AMI
ConectorAMI ──► StreamAsync ──► Normalización ──► Comando
                                         │
                    ┌────────────────────┘
                    ▼
           GestorColas (Queue Manager)
                    │
          ┌─────────┴─────────┐
          ▼                    ▼
    Transmisión HTTP      Buffer SQLite
    (tiempo real)         (offline)
          │                    │
          └─────────┬──────────┘
                    ▼
           Backend CallMetric (Spring Boot)
```

## Stack

| Área | Tecnología |
|------|-----------|
| Runtime | Python 3.10+, asyncio |
| AMI | `asyncio-manager` (conexión persistente a Asterisk) |
| HTTP | `httpx` (AsyncClient) |
| WebSocket | `websockets` |
| Buffer | `aiosqlite` (SQLite asíncrono) |
| Validación | `pydantic` v2 |
| Métricas | `psutil` (CPU, RAM, disco) |
| Service | systemd |

## Estructura

```
src/
├── main.py                    # Punto de entrada (AgenteCallMetric)
├── core/                      # Configuración, contexto, logger
├── factories/                 # Fábrica de fuentes de eventos
├── connectors/                # Conectores (AMI)
├── iterators/                 # Streams asíncronos
├── strategies/                # Normalización, retry, transmisión
├── commands/                  # Procesamiento de eventos, heartbeat, flush
├── facade/                    # Motor de ingestión (orquestador)
├── buffer/                    # Buffer offline SQLite + queue manager
├── transmitters/              # Clientes HTTP y WebSocket
├── health/                    # Heartbeat y auto-monitoreo
config/
├── default.yaml               # Configuración por defecto
docs/                          # Documentación técnica
install_agent.sh               # Instalador multi-distro (systemd)
```

## Eventos Capturados

| Categoría | Eventos AMI |
|-----------|-------------|
| Ciclo de llamada | NewChannel, Dial, Answer, Hangup |
| CDR | Cdr |
| Colas (Queue) | QueueParams, QueueEntry, QueueMember, QueueCallerAbandon, AgentConnect, AgentComplete, AgentRingNoAnswer, QueueMemberStatus, QueueMemberPaused |
| SIP | PeerStatus, Registry |
| QoS | RTCPReceived (jitter, RTT, packet loss) |

## Instalación Rápida

```bash
# 1. Copiar agente al servidor PBX
scp -r agente_v3/ usuario@p bx:/opt/callmetric/

# 2. Ejecutar instalador
cd /opt/callmetric/agente_v3
sudo bash install_agent.sh

# 3. Configurar .env (el instalador guía el proceso)
# AGENT_ID=<uuid>
# BACKEND_URL=https://tu-instancia.callmetric.com
# AMI_HOST=localhost
# AMI_PORT=5038
# AMI_USUARIO=callmetric
# AMI_SECRETO=****

# 4. Verificar estado
systemctl status callmetric-agent
journalctl -u callmetric-agent -f
```

Para documentación detallada de instalación ver:
- `docs/INSTALACION.md` (Ubuntu/Debian)
- `docs/INSTALACION_CENTOS.md` (CentOS/RHEL)
- `docs/ESTRUCTURA.md` (arquitectura interna)

## Modo Seguro

Si el backend responde con `401` o `403`, el agente entra en **SAFE MODE**:
- Detiene transmisión
- Continúa capturando eventos
- Almacena localmente en buffer SQLite
- Reintenta heartbeat periódicamente

## Buffer Offline

Ante caídas de red o backend, el buffer SQLite (`/tmp/callmetric/buffer.db`) acumula eventos con:
- Máximo configurable (default: 10,000 eventos)
- FIFO con eviction de los más antiguos
- Flush automático al recuperar conexión

## Licencia

Propietaria — CallMetric Pro
