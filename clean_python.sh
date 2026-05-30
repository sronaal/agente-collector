#!/bin/bash
# =========================================================
# Limpia compilacion de Python 3.11 para empezar desde 0
# Compatible con el instalador install_agent.sh
# =========================================================

set -e

ROJO='\033[0;31m'; VERDE='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${VERDE}[INFO]${NC} $1"; }
aviso() { echo -e "${CYAN}[AVISO]${NC} $1"; }
error() { echo -e "${ROJO}[ERROR]${NC} $1"; }

if [ "$EUID" -ne 0 ]; then
    error "Ejecutar como root: sudo $0"
    exit 1
fi

echo ""
echo "====================================================="
echo " LIMPIEZA DE PYTHON 3.11"
echo "====================================================="
echo ""

echo "Se eliminará:"
echo "  - /usr/local/python3.11/"
echo "  - /usr/local/bin/python3.11"
echo "  - /usr/src/Python-3.11.11/"
echo "  - Configuración ldconfig y profile"
echo ""

if [ "$1" = "--all" ]; then
    echo "  - /usr/local/ssl/ (OpenSSL 1.1)"
    echo "  - /usr/src/openssl-1.1.1w/"
fi

echo ""
read -p "¿Continuar? (s/N): " CONFIRMAR
[[ ! "$CONFIRMAR" =~ ^[sSyY] ]] && { aviso "Cancelado"; exit 0; }

rm -rf /usr/local/python3.11 && info "/usr/local/python3.11 eliminado"
rm -f /usr/local/bin/python3.11 && info "/usr/local/bin/python3.11 eliminado"
rm -f /etc/ld.so.conf.d/python3.11.conf && ldconfig && info "Registro ldconfig eliminado"
rm -rf /usr/src/Python-3.11.11 /usr/src/Python-3.11.11.tgz && info "Source /usr/src/Python-3.11.11 eliminado"
rm -f /etc/profile.d/python311.sh && info "Profile /etc/profile.d/python311.sh eliminado"

if [ "$1" = "--all" ]; then
    rm -rf /usr/src/openssl-1.1.1w /usr/src/openssl-1.1.1w.tar.gz && info "Source OpenSSL eliminado"
    rm -rf /usr/local/ssl && info "/usr/local/ssl eliminado"
    rm -f /etc/ld.so.conf.d/openssl11.conf && ldconfig && info "Registro ldconfig OpenSSL eliminado"
    info "OpenSSL 1.1 eliminado completamente"
fi

echo ""
info "Limpieza completada"
echo ""
echo "Próximo paso:"
echo "  sudo bash install_agent.sh"
echo ""
