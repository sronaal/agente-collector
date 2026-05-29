# Instalacion del Agente CallMetric Pro — CentOS / RHEL / Rocky Linux

## Requisitos del sistema

- **Sistema operativo**: CentOS 7+, RHEL 8+, Rocky Linux 8+, AlmaLinux 8+
- **Python**: 3.10 o superior
- **Acceso AMI**: Puerto 5038/TCP hacia el servidor Asterisk
- **Acceso backend**: Puerto 8080/TCP hacia el servidor CallMetric

---

## 1. Manejo de Python antiguo

CentOS 7 trae Python 2.7. CentOS/RHEL 8 trae Python 3.6 o 3.9. Si la version del sistema es anterior a 3.10, tienes tres opciones:

### Opcion A: pyenv (recomendada)

Instala Python 3.11 sin tocar el Python del sistema:

```bash
# Dependencias de compilacion para CentOS/RHEL
sudo dnf install -y gcc gcc-c++ make patch bzip2 bzip2-devel \
  openssl openssl-devel readline readline-devel zlib zlib-devel \
  sqlite sqlite-devel libffi libffi-devel xz xz-devel tk tk-devel \
  curl wget git

# En CentOS 7 usar yum en vez de dnf:
# sudo yum install -y gcc gcc-c++ make patch bzip2 bzip2-devel \
#   openssl openssl-devel readline readline-devel zlib zlib-devel \
#   sqlite sqlite-devel libffi libffi-devel xz xz-devel tk tk-devel \
#   curl wget git

# Instalar pyenv
curl https://pyenv.run | bash

# Agregar al .bashrc
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

### Opcion B: EPEL + COPR (CentOS 7/8)

Usa el repositorio COPR que provee Python 3.11 empaquetado para Enterprise Linux:

```bash
# CentOS 7
sudo yum install -y epel-release
sudo yum install -y centos-release-scl
sudo yum install -y rh-python311
scl enable rh-python311 bash

# CentOS/Rocky 8
sudo dnf install -y epel-release
sudo dnf install -y python3.11 python3.11-devel python3.11-pip

# Rocky 9 / CentOS 9 Stream
sudo dnf install -y python3.11 python3.11-devel python3.11-pip

# Usar explicitamente python3.11
cd /opt/callmetric/agente
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Opcion C: compilar desde fuente

```bash
# Dependencias de compilacion
sudo dnf install -y gcc gcc-c++ make wget openssl-devel \
  bzip2-devel libffi-devel zlib-devel readline-devel \
  sqlite-devel xz-devel tk-devel

# CentOS 7: sudo yum install -y gcc gcc-c++ make wget openssl-devel \
#   bzip2-devel libffi-devel zlib-devel readline-devel \
#   sqlite-devel xz-devel tk-devel

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

## 3. Crear usuario dedicado

```bash
sudo useradd -r -s /sbin/nologin -d /opt/callmetric callmetric
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

Salida esperada:

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

## 7. SELinux

CentOS/RHEL tienen SELinux activo por defecto. Si el agente no puede conectar hacia afuera, verifica:

```bash
# Ver estado de SELinux
getenforce

# Ver si hay denegaciones
sudo ausearch -m avc -ts recent | grep callmetric

# Si hay denegaciones, crear politica o poner contexto adecuado:
sudo semanage fcontext -a -t bin_t "/opt/callmetric/agente/.venv/bin/python"
sudo restorecon -v /opt/callmetric/agente/.venv/bin/python

# Alternativa: permitir conexiones de red desde el agente
sudo setsebool -P httpd_can_network_connect 1
```

> Si prefieres deshabilitar SELinux temporalmente para pruebas: `sudo setenforce 0`. No recomendado en produccion.

---

## 8. Firewall (firewalld)

CentOS usa `firewalld` por defecto. El agente necesita **salida** hacia el AMI y el backend (no requiere abrir puertos de entrada):

```bash
# Verificar estado
sudo firewall-cmd --state

# Permitir salida hacia el Asterisk (5038) y backend (8080)
# firewalld permite toda la salida por defecto, pero si hay reglas restrictivas:
sudo firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -d <IP-ASTERISK> --dport 5038 -j ACCEPT
sudo firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -d <IP-BACKEND> --dport 8080 -j ACCEPT
sudo firewall-cmd --reload

# Ver reglas
sudo firewall-cmd --direct --get-all-rules
```

### Puertos requeridos

| Direccion | Puerto | Protocolo | Proposito |
|---|---|---|---|
| Salida → Asterisk | 5038 | TCP | AMI |
| Salida → Backend | 8080 | TCP | API HTTP |
| Salida → Backend | 8080 | TCP | WebSocket (ws://) |

---

## 9. Verificar que el agente esta activo en el backend

```bash
# Consultar estado del agente (requiere token JWT de admin)
curl -s -H "Authorization: Bearer <token>" \
  http://<BACKEND_URL>/api/agentes | python3 -m json.tool
```

Si el agente aparece con `status: "active"` y `ultimo_heartbeat` reciente, la instalacion fue exitosa.

---

## 10. Solucion de problemas

### "No module named ..."

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Error de compilacion con pyenv

En CentOS 7, OpenSSL 1.0.2 es muy antiguo para Python 3.11. Solucion:

```bash
# Instalar OpenSSL 1.1 desde fuente
sudo yum install -y gcc gcc-c++ make wget perl-core
cd /tmp
wget https://www.openssl.org/source/openssl-1.1.1w.tar.gz
tar -xf openssl-1.1.1w.tar.gz
cd openssl-1.1.1w
./config --prefix=/usr/local/openssl --openssldir=/usr/local/openssl
make -j$(nproc)
sudo make install
sudo ldconfig

# Compilar Python contra OpenSSL 1.1
export LDFLAGS="-L/usr/local/openssl/lib"
export CPPFLAGS="-I/usr/local/openssl/include"
export LD_LIBRARY_PATH="/usr/local/openssl/lib:$LD_LIBRARY_PATH"
pyenv install 3.11.11
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

- Verificar conectividad:

```bash
nc -zv <AMI_HOST> 5038
```

- En CentOS, verificar que no haya regla de firewalld o iptables bloqueando.

### "Error fatal en el agente"

```bash
sudo journalctl -u callmetric-agent -n 50 --no-pager
```

Cambiar `NIVEL_LOG=DEBUG` en `.env` para mas detalle.

### Heartbeat no llega al backend

Verificar que `BACKEND_URL` apunte al backend (puerto 8080) y no al frontend (puerto 3000). Endpoint: `POST /api/v1/agent/heartbeat` con header `X-Agent-ID`.

### uuidgen no encontrado

```bash
sudo dnf install -y util-linux   # CentOS 8+
# CentOS 7: sudo yum install -y util-linux
```

### SELinux bloquea la conexion saliente

```bash
sudo ausearch -m avc -ts recent | grep python
# Si hay denegaciones:
sudo setsebool -P daemons_use_tcp_connect 1
```
