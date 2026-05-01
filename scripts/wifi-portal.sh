#!/bin/bash
# wifi-portal.sh - Control del hotspot KEYON-Setup
# Uso: wifi-portal.sh on|off|status

ACTION=$1

case "$ACTION" in
    on)
        echo "Activando hotspot KEYON-Setup..."
        # Desconectar WiFi actual
        nmcli device disconnect wlan0 2>/dev/null
        sleep 2
        # Activar hotspot
        nmcli connection up KEYON-Setup
        if [ $? -eq 0 ]; then
            echo "Hotspot activo:"
            echo "  SSID: KEYON-Setup"
            echo "  Password: keyon2026"
            echo "  Gateway: 192.168.50.1"
            echo "  Captive portal: http://192.168.50.1"
        else
            echo "ERROR al activar hotspot"
            exit 1
        fi
        ;;
    off)
        echo "Desactivando hotspot..."
        nmcli connection down KEYON-Setup 2>/dev/null
        sleep 2
        # Reactivar conexion WiFi normal
        nmcli connection up netplan-wlan0-HGW-5B1770-2 2>/dev/null
        echo "Volviendo a modo cliente WiFi"
        ;;
    status)
        echo "=== Estado de red ==="
        nmcli device status | grep -E "wlan0|eth0"
        echo ""
        echo "=== Conexiones activas ==="
        nmcli connection show --active
        ;;
    *)
        echo "Uso: $0 {on|off|status}"
        exit 1
        ;;
esac
