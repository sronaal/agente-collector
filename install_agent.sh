#!/bin/bash
# =========================================================
# Instalador del Agente CallMetric Pro
# Compatible con:
#   - CentOS 7+ / RHEL 7+ / Rocky Linux / AlmaLinux / Fedora
#   - Ubuntu 18.04+ / Debian 10+
#   - openSUSE / SLES
#
# Hace:
#   1. Compila e instala Python 3.11 (si no existe)
#   2. Crea usuario y directorio del agente
#   3. Crea entorno virtual e instala dependencias
#   4. Configura .env interactivamente
#   5. Crea servicio systemd
# =========================================================

set -e

PYTHON_VERSION="3.11.11"
PYTHON_PREFIX="/usr/local/python3.11"
SRC_DIR="/usr/src"
AGENT_DIR="/opt/callmetric/agente"
SERVICE_USER="callmetric"

# Colores
ROJO='\033[0;31m'; VERDE='\033[0;32m'
AMARILLO='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${VERDE}[OK]${NC} $1"; }
aviso() { echo -e "${AMARILLO}[AVISO]${NC} $1"; }
error() { echo -e "${ROJO}[ERROR]${NC} $1"; }

# =========================================================
# DETECTAR DISTRIBUCION
# =========================================================
detectar_distro() {
    DISTRO_FAMILY=""
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO_ID="$ID"
        DISTRO_VERSION_ID="$VERSION_ID"
        case "$ID" in
            centos|rhel|rocky|almalinux|fedora|amzn)
                DISTRO_FAMILY="rhel" ;;
            ubuntu|debian|pop|mint|kali)
                DISTRO_FAMILY="debian" ;;
            suse|opensuse|sles)
                DISTRO_FAMILY="suse" ;;
        esac
    fi
    # Si os-release no lo detectó, probar con archivos tradicionales
    if [ -z "$DISTRO_FAMILY" ]; then
        if [ -f /etc/redhat-release ]; then
            DISTRO_ID="rhel"; DISTRO_FAMILY="rhel"
        elif [ -f /etc/debian_version ]; then
            DISTRO_ID="debian"; DISTRO_FAMILY="debian"
        elif command -v rpm &>/dev/null; then
            DISTRO_ID="rhel"; DISTRO_FAMILY="rhel"
        elif command -v dpkg &>/dev/null; then
            DISTRO_ID="debian"; DISTRO_FAMILY="debian"
        else
            DISTRO_ID="unknown"; DISTRO_FAMILY="unknown"
        fi
    fi
    info "Distribucion detectada: ${DISTRO_ID} ${DISTRO_VERSION_ID-}"
}

# =========================================================
# INSTALAR PAQUETES SEGUN DISTRO
# =========================================================
instalar_paquetes() {
    local paquetes_rhel=("$@")
    local paquetes_deb=("$@")
    local paquetes_suse=("$@")

    case "$DISTRO_FAMILY" in
        rhel)
            if command -v dnf &>/dev/null; then
                dnf install -y "${paquetes_rhel[@]}"
            else
                yum install -y "${paquetes_rhel[@]}"
            fi
            ;;
        debian)
            apt-get update -qq
            apt-get install -y "${paquetes_deb[@]}"
            ;;
        suse)
            zypper install -y "${paquetes_suse[@]}"
            ;;
        *)
            error "Distribucion no soportada: $DISTRO_ID"
            exit 1
            ;;
    esac
}

instalar_grupo_dev() {
    case "$DISTRO_FAMILY" in
        rhel)
            if command -v dnf &>/dev/null; then
                dnf groupinstall "Development Tools" -y
            else
                yum groupinstall "Development Tools" -y
            fi
            ;;
        debian)
            apt-get install -y build-essential
            ;;
        suse)
            zypper install -y -t pattern devel_C_C++
            ;;
    esac
}

# =========================================================
# VERIFICAR HEADER (busca en rutas estándar y multi-arch)
# =========================================================
HEADER_ERROR=""
_verificar_header() {
    local _nombre="$1" _header="$2" _pkg_rhel="$3" _pkg_deb="$4" _pkg_suse="$5"
    local _found=false _pkg=""
    for _hp in $_header; do
        [ -f "$_hp" ] && _found=true && break
    done
    if ! $_found; then
        case "$DISTRO_FAMILY" in
            rhel) _pkg="$_pkg_rhel" ;;
            debian) _pkg="$_pkg_deb" ;;
            suse) _pkg="$_pkg_suse" ;;
        esac
        aviso "$_nombre no encontrado. Instalando '$_pkg'..."
        case "$DISTRO_FAMILY" in
            rhel)
                if command -v dnf &>/dev/null; then
                    dnf install -y "$_pkg" 2>&1 || true
                else
                    yum install -y "$_pkg" 2>&1 || true
                fi
                ;;
            debian)
                apt-get install -y "$_pkg" 2>&1 || true
                ;;
            suse)
                zypper install -y "$_pkg" 2>&1 || true
                ;;
        esac
        _found=false
        for _hp in $_header; do
            [ -f "$_hp" ] && _found=true && break
        done
    fi
    if ! $_found; then
        HEADER_ERROR="$_nombre"
        echo ""
        error "FATAL: $_nombre no encontrado."
        echo ""
        if [ "$DISTRO_FAMILY" = "rhel" ]; then
            error "El servidor no tiene acceso al paquete '$_pkg_rhel'."
            error "Verifica los repositorios y activa los necesarios:"
            echo ""
            error "  1. Ver repos disponibles:  yum repolist all"
            error "  2. Ver suscripción RHEL:  subscription-manager status"
            error "  3. Activar repos base:"
            error "     subscription-manager repos --enable rhel-*-baseos-rpms"
            error "     subscription-manager repos --enable rhel-*-appstream-rpms"
            echo ""
            error "  4. Instalar manualmente:  yum install -y $_pkg_rhel"
            echo ""
        elif [ "$DISTRO_FAMILY" = "debian" ]; then
            error "  apt-get install -y $_pkg_deb"
        else
            error "Instala manualmente uno de estos paquetes según tu distro:"
            error "  Red Hat / CentOS:  yum install -y $_pkg_rhel"
            error "  Debian / Ubuntu:   apt-get install -y $_pkg_deb"
            error "  SUSE / openSUSE:   zypper install -y $_pkg_suse"
        fi
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            error "Distro detectada: $ID $VERSION_ID"
        fi
        error "Una vez instalado manualmente, vuelve a ejecutar el script."
        echo ""
        return 1
    fi
    ok "$_nombre encontrado"
}

# =========================================================
# PASO 1: Verificar si ya hay Python 3.11
# =========================================================
paso1_python311() {
    echo ""
    echo "====================================================="
    echo " PASO 1: VERIFICANDO PYTHON 3.11"
    echo "====================================================="
    echo ""

    _reparar_ldconfig() {
        if [ -d "${PYTHON_PREFIX}/lib" ] && [ ! -f /etc/ld.so.conf.d/python3.11.conf ]; then
            echo "${PYTHON_PREFIX}/lib" > /etc/ld.so.conf.d/python3.11.conf
            ldconfig
        fi
    }

    if command -v python3.11 &>/dev/null; then
        if python3.11 --version &>/dev/null; then
            ok "Python 3.11 ya instalado: $(python3.11 --version)"
            return 0
        fi
        aviso "python3.11 encontrado pero no arranca (librería compartida faltante)"
        _reparar_ldconfig
        if python3.11 --version &>/dev/null; then
            ok "Python 3.11 reparado (ldconfig actualizado)"
            return 0
        fi
        aviso "Recompilando Python..."
        return 1
    fi

    if [ -x "${PYTHON_PREFIX}/bin/python3.11" ]; then
        ln -sf "${PYTHON_PREFIX}/bin/python3.11" /usr/local/bin/python3.11
        _reparar_ldconfig
        if python3.11 --version &>/dev/null; then
            ok "Python 3.11 encontrado en ${PYTHON_PREFIX}"
            return 0
        fi
        aviso "Python en ${PYTHON_PREFIX} no funciona. Recompilando..."
        return 1
    fi

    aviso "Python 3.11 no encontrado. Compilando desde fuente..."
    return 1
}

# =========================================================
# PASO 2: Instalar dependencias de compilacion
# =========================================================
paso2_dependencias() {
    echo ""
    echo "====================================================="
    echo " PASO 2: INSTALANDO DEPENDENCIAS DE COMPILACION"
    echo "====================================================="
    echo ""

    instalar_grupo_dev

    case "$DISTRO_FAMILY" in
        rhel)
            instalar_paquetes \
                gcc gcc-c++ make wget tar \
                openssl openssl-devel \
                bzip2-devel libffi-devel zlib-devel \
                xz-devel sqlite-devel readline-devel \
                tk-devel gdbm-devel ncurses-devel \
                uuid-devel libuuid-devel pkgconfig
            instalar_paquetes perl-CORE 2>/dev/null || true
            ;;
        debian)
            instalar_paquetes \
                gcc g++ make wget tar \
                libssl-dev libbz2-dev libffi-dev zlib1g-dev \
                liblzma-dev libsqlite3-dev libreadline-dev \
                tk-dev libgdbm-dev libncurses-dev \
                uuid-dev pkg-config
            ;;
        suse)
            instalar_paquetes \
                gcc gcc-c++ make wget tar \
                libopenssl-devel libbz2-devel libffi-devel zlib-devel \
                xz-devel sqlite3-devel readline-devel \
                tk-devel gdbm-devel ncurses-devel \
                libuuid-devel pkg-config
            ;;
    esac

    _verificar_header "zlib.h"    "/usr/include/zlib.h /usr/include/*-linux-gnu/zlib.h" \
        "zlib-devel" "zlib1g-dev" "zlib-devel" || exit 1
    _verificar_header "sqlite3.h" "/usr/include/sqlite3.h /usr/include/*-linux-gnu/sqlite3.h" \
        "sqlite-devel" "libsqlite3-dev" "sqlite3-devel" || exit 1
    _verificar_header "bzlib.h"   "/usr/include/bzlib.h /usr/include/*-linux-gnu/bzlib.h" \
        "bzip2-devel" "libbz2-dev" "libbz2-devel" || exit 1
    _verificar_header "lzma.h"    "/usr/include/lzma.h /usr/include/*-linux-gnu/lzma.h" \
        "xz-devel" "liblzma-dev" "xz-devel" || exit 1
    _verificar_header "ssl.h"     "/usr/include/openssl/ssl.h" \
        "openssl-devel" "libssl-dev" "libopenssl-devel" || exit 1

    ok "Dependencias instaladas"
}

# =========================================================
# PASO 2b: Verificar OpenSSL (Python 3.11 requiere 1.1+)
# =========================================================
paso2b_openssl() {
    echo ""
    echo "====================================================="
    echo " PASO 2b: VERIFICANDO OPENSSL"
    echo "====================================================="
    echo ""

    if [ -f "/usr/local/ssl/lib/libssl.so.1.1" ]; then
        ok "OpenSSL 1.1 ya compilado en /usr/local/ssl"
        return 0
    fi

    local openssl_version
    openssl_version=$(openssl version 2>/dev/null | awk '{print $2}' | cut -d. -f1-2)

    if [ -z "$openssl_version" ]; then
        aviso "OpenSSL no encontrado. Compilando OpenSSL 1.1..."
        compilar_openssl11
        return 0
    fi

    local major minor
    major=$(echo "$openssl_version" | cut -d. -f1)
    minor=$(echo "$openssl_version" | cut -d. -f2)

    if [ "$major" -lt 1 ] || { [ "$major" -eq 1 ] && [ "$minor" -lt 1 ]; }; then
        aviso "OpenSSL $openssl_version detectado. Python 3.11 necesita 1.1+"
        aviso "Compilando OpenSSL 1.1 en /usr/local/ssl..."
        compilar_openssl11
    else
        ok "OpenSSL $openssl_version detectado (compatible)"
    fi
}

compilar_openssl11() {
    cd "$SRC_DIR"
    rm -rf openssl-1.1.1w openssl-1.1.1w.tar.gz

    wget -q https://www.openssl.org/source/openssl-1.1.1w.tar.gz
    tar -xf openssl-1.1.1w.tar.gz
    cd openssl-1.1.1w

    local _zlib_found=false
    for _zp in /usr/include/zlib.h /usr/include/*-linux-gnu/zlib.h; do
        [ -f "$_zp" ] && _zlib_found=true && break
    done

    local config_opts="--prefix=/usr/local/ssl --openssldir=/usr/local/ssl shared"
    if $_zlib_found; then
        config_opts="$config_opts zlib"
        ok "Compilando OpenSSL con soporte zlib"
    else
        aviso "zlib.h no encontrado. OpenSSL se compilará sin soporte zlib (no crítico)"
    fi

    ./config $config_opts
    make -j$(nproc)
    make install

    echo "/usr/local/ssl/lib" > /etc/ld.so.conf.d/openssl11.conf
    ldconfig

    ok "OpenSSL 1.1.1w instalado en /usr/local/ssl"
}

# =========================================================
# PASO 3: Compilar e instalar Python 3.11
# =========================================================
paso3_compilar_python() {
    echo ""
    echo "====================================================="
    echo " PASO 3: COMPILANDO PYTHON ${PYTHON_VERSION}"
    echo "====================================================="
    echo ""

    unset PYTHONHOME PYTHONPATH
    unset LDFLAGS CPPFLAGS LD_LIBRARY_PATH

    local ssl_dir="/usr"
    if [ -f "/usr/local/ssl/lib/libssl.so.1.1" ]; then
        ssl_dir="/usr/local/ssl"
        export LDFLAGS="-L${ssl_dir}/lib"
        export CPPFLAGS="-I${ssl_dir}/include"
        export LD_LIBRARY_PATH="${ssl_dir}/lib:${LD_LIBRARY_PATH}"
        ok "Usando OpenSSL 1.1 compilado en ${ssl_dir}"
    fi

    cd "$SRC_DIR"
    rm -rf "Python-${PYTHON_VERSION}" "Python-${PYTHON_VERSION}.tgz"

    wget -q "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
    tar -xf "Python-${PYTHON_VERSION}.tgz"
    cd "Python-${PYTHON_VERSION}"

    make distclean || true

    # Re-verificar headers antes de configure (doble seguridad)
    _verificar_header "zlib.h"    "/usr/include/zlib.h /usr/include/*-linux-gnu/zlib.h" \
        "zlib-devel" "zlib1g-dev" "zlib-devel" || exit 1
    _verificar_header "sqlite3.h" "/usr/include/sqlite3.h /usr/include/*-linux-gnu/sqlite3.h" \
        "sqlite-devel" "libsqlite3-dev" "sqlite3-devel" || exit 1

    local _configure_opts="--prefix=${PYTHON_PREFIX} --with-openssl=${ssl_dir} --with-openssl-rpath=auto --enable-shared"

    ./configure $_configure_opts

    make -j$(nproc)
    make altinstall

    echo "${PYTHON_PREFIX}/lib" > /etc/ld.so.conf.d/python3.11.conf
    ldconfig

    ln -sf "${PYTHON_PREFIX}/bin/python3.11" /usr/local/bin/python3.11

    # Establecer LD_LIBRARY_PATH para esta sesión
    export LD_LIBRARY_PATH="${ssl_dir}/lib:${PYTHON_PREFIX}/lib:${LD_LIBRARY_PATH}"

    if python3.11 -m ensurepip --upgrade --default-pip &>/dev/null; then
        ok "pip instalado via ensurepip"
    elif python3.11 -c "import zlib" &>/dev/null; then
        aviso "ensurepip falló, intentando get-pip.py..."
        wget -q https://bootstrap.pypa.io/get-pip.py
        if python3.11 get-pip.py; then
            ok "pip instalado via get-pip.py"
        else
            aviso "pip no disponible - se instalará en paso 4"
        fi
        rm -f get-pip.py
    else
        aviso "zlib no disponible - pip se instalará en paso 4"
    fi

    ok "Python ${PYTHON_VERSION} compilado e instalado"
}

# =========================================================
# PASO 4: Verificar instalacion de Python 3.11
# =========================================================
paso4_verificar_python() {
    echo ""
    echo "====================================================="
    echo " PASO 4: VERIFICANDO PYTHON"
    echo "====================================================="
    echo ""

    _reconstruir_modulo() {
        local _modulo="$1" _pkg_rhel="$2" _pkg_deb="$3" _pkg_suse="$4"
        aviso "Módulo '${_modulo}' no disponible — instalando dev headers y reconstruyendo..."
        case "$DISTRO_FAMILY" in
            rhel) instalar_paquetes "$_pkg_rhel" ;;
            debian) instalar_paquetes "$_pkg_deb" ;;
            suse) instalar_paquetes "$_pkg_suse" ;;
        esac
        if [ -d "/usr/src/Python-${PYTHON_VERSION}" ]; then
            cd "/usr/src/Python-${PYTHON_VERSION}"
            make -j$(nproc) 2>&1 | tail -5
            make altinstall 2>&1 | tail -5
            ldconfig
            if python3.11 -c "import ${_modulo}" &>/dev/null; then
                ok "Módulo '${_modulo}' reconstruido"
                return 0
            fi
        fi
        error "Módulo '${_modulo}' sigue sin funcionar"
        error "Recompila manualmente: cd /usr/src/Python-${PYTHON_VERSION} && make clean && make -j\$(nproc) && make altinstall"
        return 1
    }

    python3.11 --version

    python3.11 -c "import ssl;     print('SSL ok')"     || _reconstruir_modulo "ssl"     "openssl-devel"   "libssl-dev"     "libopenssl-devel" || true
    python3.11 -c "import zlib;    print('ZLIB ok')"    || _reconstruir_modulo "zlib"    "zlib-devel"      "zlib1g-dev"     "zlib-devel"       || true
    python3.11 -c "import sqlite3; print('SQLite ok')"  || _reconstruir_modulo "sqlite3" "sqlite-devel"    "libsqlite3-dev" "sqlite3-devel"    || true
    python3.11 -c "import bz2;     print('BZ2 ok')"     || _reconstruir_modulo "bz2"     "bzip2-devel"     "libbz2-dev"     "libbz2-devel"     || true
    python3.11 -c "import lzma;    print('LZMA ok')"    || _reconstruir_modulo "lzma"    "xz-devel"        "liblzma-dev"    "xz-devel"         || true
    python3.11 -c "import hashlib; print('HASHLIB ok')" || true

    if ! python3.11 -m pip --version &>/dev/null; then
        aviso "pip no instalado. Reintentando ensurepip..."
        if python3.11 -m ensurepip --upgrade --default-pip &>/dev/null; then
            ok "pip instalado"
        else
            aviso "ensurepip falló. Intentando get-pip.py..."
            wget -q https://bootstrap.pypa.io/get-pip.py
            if python3.11 get-pip.py &>/dev/null; then
                ok "pip instalado"
            else
                error "pip no se pudo instalar"
                error "Después de la instalación, ejecuta: python3.11 -m ensurepip --upgrade"
            fi
            rm -f get-pip.py
        fi
    fi

    cat >/etc/profile.d/python311.sh <<EOF
export PATH=${PYTHON_PREFIX}/bin:\$PATH
EOF
    chmod +x /etc/profile.d/python311.sh

    ok "Python verificado correctamente"
}

# =========================================================
# PASO 5: Crear usuario y directorio del agente
# =========================================================
paso5_usuario() {
    echo ""
    echo "====================================================="
    echo " PASO 5: CREANDO USUARIO Y DIRECTORIO"
    echo "====================================================="
    echo ""

    if ! id -u ${SERVICE_USER} &>/dev/null; then
        local nologin_shell
        if [ -f /usr/sbin/nologin ]; then
            nologin_shell="/usr/sbin/nologin"
        else
            nologin_shell="/sbin/nologin"
        fi
        useradd -r -s "$nologin_shell" -d ${AGENT_DIR} ${SERVICE_USER}
        ok "Usuario '${SERVICE_USER}' creado"
    else
        ok "Usuario '${SERVICE_USER}' ya existe"
    fi

    mkdir -p ${AGENT_DIR}
    ok "Directorio ${AGENT_DIR} listo"
}

# =========================================================
# PASO 6: Copiar archivos del agente
# =========================================================
paso6_copiar_agente() {
    echo ""
    echo "====================================================="
    echo " PASO 6: COPIANDO ARCHIVOS DEL AGENTE"
    echo "====================================================="
    echo ""

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [ -f "${SCRIPT_DIR}/requirements.txt" ]; then
        mkdir -p "${AGENT_DIR}/config"
        cp -r "${SCRIPT_DIR}/src" "${AGENT_DIR}/"
        cp "${SCRIPT_DIR}/config/default.yaml" "${AGENT_DIR}/config/" 2>/dev/null || true
        cp "${SCRIPT_DIR}/requirements.txt" "${AGENT_DIR}/"
        cp "${SCRIPT_DIR}/.env" "${AGENT_DIR}/" 2>/dev/null || true
        ok "Archivos copiados desde ${SCRIPT_DIR}"
    else
        error "No se encuentra requirements.txt en ${SCRIPT_DIR}"
        echo "Copia manualmente los archivos del agente a ${AGENT_DIR}"
        echo "  src/"
        echo "  config/"
        echo "  requirements.txt"
        echo "  .env"
        read -p "Presiona Enter cuando esten copiados..."
    fi

    chown -R ${SERVICE_USER}:${SERVICE_USER} ${AGENT_DIR}
}

# =========================================================
# PASO 7: Crear entorno virtual e instalar dependencias
# =========================================================
paso7_venv() {
    echo ""
    echo "====================================================="
    echo " PASO 7: ENTORNO VIRTUAL E INSTALANDO DEPENDENCIAS"
    echo "====================================================="
    echo ""

    cd ${AGENT_DIR}

    python3.11 -m venv .venv
    ok "Entorno virtual creado"

    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    deactivate

    chown -R ${SERVICE_USER}:${SERVICE_USER} .venv

    ok "Dependencias instaladas"
}

# =========================================================
# PASO 8: Configurar .env
# =========================================================
paso8_env() {
    echo ""
    echo "====================================================="
    echo " PASO 8: CONFIGURANDO VARIABLES DE ENTORNO"
    echo "====================================================="
    echo ""

    ENV_FILE="${AGENT_DIR}/.env"

    if [ ! -f "${ENV_FILE}" ]; then
        cat > "${ENV_FILE}" << 'EOL'
AGENT_ID=
AMI_HOST=
AMI_PORT=5038
AMI_USUARIO=
AMI_SECRETO=
BACKEND_URL=
TOKEN_REGISTRO=
INTERVALO_HEARTBEAT=30
TIMEOUT_ACCION=5.0
TIMEOUT_CONEXION=10.0
TIMEOUT_LECTURA=30.0
RUTA_BUFFER=/tmp/callmetric/buffer.db
TAMANO_MAXIMO_BUFFER=10000
NIVEL_LOG=INFO
EOL
        aviso "Archivo .env creado con valores por defecto"
    fi

    local uuid_val
    if command -v uuidgen &>/dev/null; then
        uuid_val=$(uuidgen)
    elif command -v python3 &>/dev/null; then
        uuid_val=$(python3 -c "import uuid; print(uuid.uuid4())")
    else
        uuid_val="<generar con: python3 -c \"import uuid; print(uuid.uuid4())\">"
    fi

    echo "Configura las variables en ${ENV_FILE}"
    echo ""
    echo "  AGENT_ID       = ${uuid_val}"
    echo "  AMI_HOST       = IP del servidor Asterisk"
    echo "  AMI_USUARIO    = Usuario AMI"
    echo "  AMI_SECRETO    = Password AMI"
    echo "  BACKEND_URL    = http://<IP-BACKEND>:8080"
    echo "  TOKEN_REGISTRO = Token generado por el backend"
    echo "  NIVEL_LOG      = INFO (o DEBUG para depurar)"
    echo ""

    read -p "Editar .env ahora? (s/N): " EDITAR
    if [[ "${EDITAR}" =~ ^[sSyY] ]]; then
        if command -v nano &>/dev/null; then
            nano "${ENV_FILE}"
        elif command -v vi &>/dev/null; then
            vi "${ENV_FILE}"
        else
            echo "Abre ${ENV_FILE} y editalo manualmente."
        fi
    fi

    chown ${SERVICE_USER}:${SERVICE_USER} "${ENV_FILE}"
    ok "Archivo .env configurado"
}

# =========================================================
# PASO 9: Probar agente
# =========================================================
paso9_probar() {
    echo ""
    echo "====================================================="
    echo " PASO 9: PROBANDO EL AGENTE"
    echo "====================================================="
    echo ""

    echo "Ejecutando el agente durante 5 segundos..."
    timeout 5 sudo -u ${SERVICE_USER} bash -c "
        cd ${AGENT_DIR}
        source .venv/bin/activate
        python src/main.py
    " 2>&1 || true

    ok "Prueba completada"
}

# =========================================================
# PASO 10: Crear servicio systemd
# =========================================================
paso10_systemd() {
    echo ""
    echo "====================================================="
    echo " PASO 10: CREANDO SERVICIO SYSTEMD"
    echo "====================================================="
    echo ""

    cat > /etc/systemd/system/callmetric-agent.service <<EOF
[Unit]
Description=CallMetric Pro Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${AGENT_DIR}
ExecStart=${AGENT_DIR}/.venv/bin/python -m src.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    ok "Servicio creado: /etc/systemd/system/callmetric-agent.service"

    echo ""
    read -p "Iniciar el servicio ahora? (s/N): " INICIAR
    if [[ "${INICIAR}" =~ ^[sSyY] ]]; then
        systemctl enable --now callmetric-agent
        systemctl status callmetric-agent --no-pager | head -10
    fi
}

# =========================================================
# PASO 11: Sugerencias post-instalacion segun distro
# =========================================================
paso11_sugerencias() {
    if [ "$DISTRO_FAMILY" = "rhel" ] && command -v getenforce &>/dev/null; then
        if [ "$(getenforce)" = "Enforcing" ]; then
            echo ""
            aviso "SELinux esta en modo Enforcing."
            echo "Si el agente no puede conectar, revisa los logs con:"
            echo "  sudo ausearch -m avc -ts recent | grep python"
            echo ""
        fi
    fi

    echo "Firewall: el agente necesita salida TCP a:"
    echo "  - Puerto 5038 (AMI - Asterisk)"
    echo "  - Puerto 8080 (Backend API)"
    echo ""
}

# =========================================================
# RESUMEN FINAL
# =========================================================
resumen() {
    echo ""
    echo "====================================================="
    echo " INSTALACION COMPLETADA"
    echo "====================================================="
    echo ""
    echo "  Distribucion : ${DISTRO_ID} ${DISTRO_VERSION_ID-}"
    echo "  Directorio   : ${AGENT_DIR}"
    echo "  Entorno      : ${AGENT_DIR}/.venv"
    echo "  Python       : $(python3.11 --version 2>/dev/null)"
    echo "  Usuario      : ${SERVICE_USER}"
    echo ""
    echo "Comandos utiles:"
    echo ""
    echo "  Iniciar     : sudo systemctl start callmetric-agent"
    echo "  Detener     : sudo systemctl stop callmetric-agent"
    echo "  Estado      : sudo systemctl status callmetric-agent"
    echo "  Logs        : sudo journalctl -u callmetric-agent -f"
    echo "  Probar      : sudo -u ${SERVICE_USER} ${AGENT_DIR}/.venv/bin/python ${AGENT_DIR}/src/main.py"
    echo ""
    echo "Para editar .env:"
    echo "  nano ${AGENT_DIR}/.env"
    echo ""
    echo "Si el agente no arranca:"
    echo "  1. Revisa los logs: sudo journalctl -u callmetric-agent -n 50 --no-pager"
    echo "  2. Cambia NIVEL_LOG=DEBUG en .env"
    echo "  3. Prueba manualmente (ver comando mas arriba)"
    echo ""
    echo "====================================================="
}

# =========================================================
# MOSTRAR PLAN Y CONFIRMAR
# =========================================================
_confirmar_plan() {
    local _accion_python="Compilar Python ${PYTHON_VERSION} desde fuente"
    if command -v python3.11 &>/dev/null && python3.11 --version &>/dev/null; then
        _accion_python="Usar Python existente ($(python3.11 --version 2>/dev/null))"
    fi

    local _accion_openssl=""
    if [ -f "/usr/local/ssl/lib/libssl.so.1.1" ]; then
        _accion_openssl="OpenSSL 1.1 ya compilado"
    else
        local _ossl_ver
        _ossl_ver=$(openssl version 2>/dev/null | awk '{print $2}' | cut -d. -f1-2)
        if [ -n "$_ossl_ver" ] && [ "$(echo "$_ossl_ver" | cut -d. -f1)" -ge 1 ] && [ "$(echo "$_ossl_ver" | cut -d. -f2)" -ge 1 ]; then
            _accion_openssl="OpenSSL $_ossl_ver del sistema (compatible)"
        else
            _accion_openssl="Compilar OpenSSL 1.1 desde fuente"
        fi
    fi

    echo ""
    echo "====================================================="
    echo " PLAN DE INSTALACION"
    echo "====================================================="
    echo ""
    echo "  Distribucion  : ${DISTRO_ID} ${DISTRO_VERSION_ID-}"
    echo "  Directorio    : ${AGENT_DIR}"
    echo "  Usuario       : ${SERVICE_USER}"
    echo ""
    echo "  Acciones a realizar:"
    echo ""
    echo "    [1/9]  Verificar Python 3.11"
    echo "    [2/9]  Instalar dependencias de compilación"
    echo "    [3/9]  Verificar OpenSSL"
    echo "    [4/9]  ${_accion_python}"
    echo "    [5/9]  Verificar módulos de Python"
    echo "    [6/9]  Crear usuario y directorio"
    echo "    [7/9]  Copiar archivos del agente"
    echo "    [8/9]  Crear entorno virtual e instalar dependencias"
    echo "    [9/9]  Configurar .env"
    echo ""
    echo "  OpenSSL      : ${_accion_openssl}"
    echo "  Python       : ${_accion_python}"
    echo ""

    read -p "¿Continuar con la instalación? (s/N): " CONFIRMAR
    if [[ ! "${CONFIRMAR}" =~ ^[sSyY] ]]; then
        echo ""
        aviso "Instalación cancelada."
        exit 0
    fi
    echo ""
}

# =========================================================
# MAIN
# =========================================================
main() {
    clear
    echo ""
    echo "====================================================="
    echo " CALLMETRIC PRO - INSTALADOR DEL AGENTE"
    echo "====================================================="
    echo ""

    if [ "$EUID" -ne 0 ]; then
        error "Ejecutar como root: sudo $0"
        exit 1
    fi

    detectar_distro
    _confirmar_plan

    paso1_python311 || {
        paso2_dependencias
        paso2b_openssl
        paso3_compilar_python
    }

    paso4_verificar_python
    paso5_usuario
    paso6_copiar_agente
    paso7_venv
    paso8_env
    paso9_probar
    paso11_sugerencias

    read -p "Crear servicio systemd? (s/N): " SVC
    if [[ "${SVC}" =~ ^[sSyY] ]]; then
        paso10_systemd
    fi

    resumen
}

main "$@"
