# Instalacion y Configuracion del Agente CallMetric Pro

## Requisitos del sistema

- **Sistema operativo**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+, Rocky Linux 9+)
- **Python**: 3.10 o superior
- **Acceso AMI**: Puerto 5038/TCP hacia el servidor Asterisk
- **Acceso backend**: Puerto 8080/TCP (o el que corresponda) hacia el servidor CallMetric

---

## 1. Manejo de Python antiguo

Si el servidor tiene una version de Python anterior a 3.10 y NO puedes actualizar el sistema (por ejemplo, Ubuntu 18.04 con Python 3.6 que usan otros servicios), tienes tres opciones:

### Opcion A: pyenv (recomendada)

Instala Python 3.11 sin afectar el Python del sistema:

```bash
# Instalar dependencias para compilar Python
sudo apt update
sudo apt install -y build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev curl \
  libncursesw5-dev xz-utils tk-dev libxml2-dev \
  libxmlsec1-dev libffi-dev liblzma-dev

# Instalar pyenv
curl https://pyenv.run | bash

# Agregar al .bashrc (el instalador ya lo sugiere)
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo '[[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
exec $SHELL

# Instalar Python 3.11
pyenv install 3.11.11

# Crear entorno virtual con esa version
cd /opt/callmetric/agente
pyenv local 3.11.11
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Opcion B: deadsnakes PPA (Ubuntu)

Agrega el repositorio deadsnakes que tiene Python 3.11 para versiones viejas de Ubuntu:

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# Usar explicitamente python3.11
cd /opt/callmetric/agente
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Opcion C: compilar desde fuente

```bash
# Dependencias de compilacion
sudo apt update
sudo apt install -y build-essential libssl-dev zlib1g-dev \
  libbz2-dev libreadline-dev libsqlite3-dev curl \
  libncursesw5-dev xz-utils tk-dev libxml2-dev \
  libxmlsec1-dev libffi-dev liblzma-dev

# Descargar y compilar Python 3.11.11
cd /tmp
wget https://www.python.org/ftp/python/3.11.11/Python-3.11.11.tgz
tar -xf Python-3.11.11.tgz
cd Python-3.11.11
./configure --enable-optimizations --prefix=/usr/local/python3.11
make -j$(nproc)
sudo make install

# Usar el Python recien compilado
cd /opt/callmetric/agente
/usr/local/python3.11/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Copiar los archivos

```bash
# Desde tu maquina de desarrollo
scp -r agente_v3/ usuario@<IP-VM>:/opt/callmetric/agente

# O directamente en la VM si tienes acceso al repositorio
git clone <repo-url> /opt/callmetric
```

---

## 3. Crear usuario dedicado (recomendado)

```bash
sudo useradd -r -s /usr/sbin/nologin -m -d /opt/callmetric callmetric
sudo chown -R callmetric:callmetric /opt/callmetric
```

---

## 4. Configurar variables de entorno

Editar `/opt/callmetric/agente/.env`:

```ini
# Identificacion unica del agente (generar con: uuidgen)
AGENT_ID=<UUID>

# Conexion AMI hacia Asterisk
AMI_HOST=<IP del Asterisk>
AMI_PORT=5038
AMI_USUARIO=<usuario AMI>
AMI_SECRETO=<password AMI>

# Backend CallMetric
BACKEND_URL=http://<IP-backend>:8080
TOKEN_REGISTRO=<token del backend>

# Heartbeat
INTERVALO_HEARTBEAT=30

# Logging
NIVEL_LOG=INFO
```

### Variables clave

| Variable | Descripcion | Ejemplo |
|---|---|---|
| `AGENT_ID` | UUID v4 unico (generar con `uuidgen`) | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `AMI_HOST` | IP del servidor Asterisk | `192.168.1.50` |
| `AMI_PORT` | Puerto AMI | `5038` |
| `AMI_USUARIO` | Usuario configurado en `manager.conf` de Asterisk | `callmetric` |
| `AMI_SECRETO` | Password del usuario AMI | `PasswordSegura123` |
| `BACKEND_URL` | URL base del backend CallMetric | `http://10.0.0.10:8080` |
| `TOKEN_REGISTRO` | Token de registro (generado por el backend) | `cm_token_abc123` |
| `NIVEL_LOG` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

> **Importante**: En el `.env` incluido en el repositorio, `BACKEND_URL` apunta a `http://localhost:3000` (frontend). Debes cambiarlo a la URL del **backend API** (puerto 8080 por defecto).

---

## 5. Probar la instalacion

```bash
cd /opt/callmetric/agente
source .venv/bin/activate
python src/main.py
```

Si la conexion es exitosa, veras en la salida:

```
CallMetric Pro Agent v1.0.0
Agente listo para procesar eventos
```

Presiona `Ctrl+C` para detener.

---

## 6. Ejecutar como servicio systemd

Crear `/etc/systemd/system/callmetric-agent.service`:

```ini
[Unit]
Description=CallMetric Pro Agent
Documentation=https://callmetric.com/docs/agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=callmetric
Group=callmetric
WorkingDirectory=/opt/callmetric/agente
ExecStart=/opt/callmetric/agente/.venv/bin/python src/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now callmetric-agent
sudo systemctl status callmetric-agent
```

Ver logs en vivo:

```bash
sudo journalctl -u callmetric-agent -f
```

---

## 7. Firewall y red

Asegurar conectividad desde la VM:

```bash
# Probar conexion AMI al Asterisk
nc -zv <AMI_HOST> 5038

# Probar conexion al backend CallMetric
curl -s -o /dev/null -w "%{http_code}" http://<BACKEND_URL>/api/v1/agent/health

# Si la VM tiene ufw activo
sudo ufw allow out 5038/tcp   # AMI
sudo ufw allow out 8080/tcp   # Backend API
```

### Puertos requeridos

| Direccion | Puerto | Protocolo | Proposito |
|---|---|---|---|
| Salida → Asterisk | 5038 | TCP | AMI |
| Salida → Backend | 8080 | TCP | API HTTP |
| Salida → Backend | 8080 | TCP | WebSocket (ws://) |

---

## 8. Verificar que el agente esta activo en el backend

```bash
# Consultar estado del agente (requiere token JWT de admin)
curl -s -H "Authorization: Bearer <token>" \
  http://<BACKEND_URL>/api/agentes | jq
```

Si el agente aparece con `status: "active"` y `ultimo_heartbeat` reciente, la instalacion fue exitosa.

---

## 9. Solucion de problemas

### "No module named ..."

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### "Connection refused" al AMI

- Verificar que Asterisk tenga AMI habilitado en `/etc/asterisk/manager.conf`:

```ini
[general]
enabled = yes
port = 5038
bindaddr = 0.0.0.0

[callmetric]
secret = PasswordSegura123
read = all
write = all
```

- Verificar que no haya firewall bloqueando el puerto 5038.

### "Error fatal en el agente"

Revisar los logs:

```bash
sudo journalctl -u callmetric-agent -n 50 --no-pager
```

Si el nivel de log es `WARNING` o superior, cambiarlo a `INFO` o `DEBUG` en `.env` para mas detalle.

### Heartbeat no llega al backend

Verificar que `BACKEND_URL` en `.env` apunte al backend (puerto 8080) y no al frontend (puerto 3000). El endpoint es `POST /api/v1/agent/heartbeat` con header `X-Agent-ID`.
