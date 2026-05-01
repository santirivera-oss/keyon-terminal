#!/usr/bin/env python3
"""
KEYON WiFi Detector v0.1.0
Decide al boot si activar modo portal o modo cliente normal.

Logica:
  1. Espera 30 segundos a que NetworkManager conecte
  2. Verifica si hay WiFi conectado
  3. Si SI -> exit 0 (KEYON UI arranca normal)
  4. Si NO -> activa hotspot + Flask, exit 0 con flag
"""
import subprocess
import time
import os
import sys

# Configuracion
WAIT_TIMEOUT = 30           # segundos a esperar conexion al boot
LOG_PATH = "/home/keyon/keyon-terminal/logs/wifi-detector.log"
PORTAL_FLAG = "/tmp/keyon-portal-active"  # archivo flag para keyon-ui.service
PORTAL_DIR = "/home/keyon/keyon-terminal/scripts/portal"
HOTSPOT_SCRIPT = "/home/keyon/keyon-terminal/scripts/wifi-portal.sh"


def log(msg):
    """Log con timestamp."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, 'a') as f:
            f.write(line + "\n")
    except Exception:
        pass


def hay_wifi_conectado():
    """Verifica si wlan0 esta conectado a alguna red."""
    try:
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'DEVICE,STATE', 'device', 'status'],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.strip().split('\n'):
            partes = line.split(':')
            if len(partes) >= 2 and partes[0] == 'wlan0':
                if partes[1] == 'connected':
                    return True
        return False
    except Exception as e:
        log(f"Error verificando wlan0: {e}")
        return False


def hay_internet():
    """Test de conectividad real con ping."""
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '3', '8.8.8.8'],
            capture_output=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def esperar_wifi(timeout):
    """Espera hasta timeout segundos a que conecte WiFi."""
    log(f"Esperando WiFi por {timeout} segundos...")
    inicio = time.time()
    
    while time.time() - inicio < timeout:
        if hay_wifi_conectado():
            elapsed = int(time.time() - inicio)
            log(f"WiFi conectado en {elapsed}s")
            return True
        time.sleep(2)
    
    log(f"Timeout {timeout}s alcanzado, sin WiFi")
    return False


def activar_modo_portal():
    """Activa hotspot KEYON-Setup + Flask server."""
    log("=== ACTIVANDO MODO PORTAL ===")
    
    # 1. Crear flag para que keyon-ui.service NO arranque
    try:
        with open(PORTAL_FLAG, 'w') as f:
            f.write(str(int(time.time())))
        log(f"Flag creado: {PORTAL_FLAG}")
    except Exception as e:
        log(f"Error creando flag: {e}")
    
    # 2. Activar hotspot
    log("Activando hotspot KEYON-Setup...")
    try:
        result = subprocess.run(
            ['sudo', HOTSPOT_SCRIPT, 'on'],
            capture_output=True, text=True, timeout=20
        )
        if result.returncode == 0:
            log("Hotspot activado OK")
        else:
            log(f"Hotspot ERROR: {result.stderr}")
            return False
    except Exception as e:
        log(f"Excepcion activando hotspot: {e}")
        return False
    
    # 3. Iniciar Flask server
    log("Iniciando servidor Flask...")
    try:
        # Cambiar al directorio del portal
        os.chdir(PORTAL_DIR)
        # Ejecutar Flask en background, no esperar
        subprocess.Popen(
            ['sudo', 'python3', 'app.py'],
            stdout=open('/tmp/portal-stdout.log', 'a'),
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        log("Flask iniciado (PID en /tmp/portal-stdout.log)")
        time.sleep(3)
        
        # Verificar que arrancó
        check = subprocess.run(
            ['sudo', 'lsof', '-i', ':80'],
            capture_output=True, text=True, timeout=5
        )
        if 'python3' in check.stdout:
            log("Flask escuchando en puerto 80 OK")
        else:
            log("WARNING: Flask no escucha en puerto 80")
    except Exception as e:
        log(f"Excepcion iniciando Flask: {e}")
        return False
    
    log("=== MODO PORTAL LISTO ===")
    log("Esperando configuracion del usuario...")
    return True


def main():
    log("=" * 50)
    log("KEYON WiFi Detector v0.1.0")
    log("=" * 50)
    
    # Limpiar flag previo si existe
    if os.path.exists(PORTAL_FLAG):
        try:
            os.remove(PORTAL_FLAG)
            log(f"Flag previo limpiado: {PORTAL_FLAG}")
        except Exception:
            pass
    
    # Esperar a que conecte WiFi
    if esperar_wifi(WAIT_TIMEOUT):
        log("Modo CLIENTE: WiFi conectado, KEYON UI arrancara normal")
        sys.exit(0)
    else:
        log("Modo PORTAL: sin WiFi, activando configurador...")
        activar_modo_portal()
        # Salimos OK aunque activamos portal
        # keyon-ui.service vera el flag y NO arrancara
        sys.exit(0)


if __name__ == '__main__':
    main()
