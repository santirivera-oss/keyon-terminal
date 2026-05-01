#!/usr/bin/env python3
"""
KEYON Portal v0.1.0 - Captive portal para configuracion WiFi
Servidor Flask que corre cuando hotspot KEYON-Setup esta activo.
"""
import subprocess
import re
import os
import time
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')

# === Funciones de red ===

def escanear_redes():
    """Escanea redes WiFi disponibles. Retorna lista de dicts."""
    try:
        # Reactivar wlan0 brevemente para escanear
        subprocess.run(['sudo', 'nmcli', 'device', 'wifi', 'rescan'],
                      capture_output=True, timeout=15)
        time.sleep(2)
        
        result = subprocess.run(
            ['sudo', 'nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'device', 'wifi', 'list'],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        redes = []
        ssids_vistos = set()
        
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            partes = line.split(':')
            if len(partes) < 3:
                continue
            
            ssid = partes[0].strip()
            try:
                signal = int(partes[1].strip())
            except ValueError:
                signal = 0
            security = partes[2].strip() or 'Open'
            
            # Filtrar SSID vacios o duplicados
            if not ssid or ssid in ssids_vistos:
                continue
            # Excluir KEYON-Setup (somos nosotros)
            if ssid == 'KEYON-Setup':
                continue
            
            ssids_vistos.add(ssid)
            redes.append({
                'ssid': ssid,
                'signal': signal,
                'security': security,
                'requires_password': security != 'Open'
            })
        
        # Ordenar por intensidad de senal
        redes.sort(key=lambda x: x['signal'], reverse=True)
        return redes
    except Exception as e:
        print(f"Error escaneando: {e}")
        return []


def conectar_a_red(ssid, password):
    """Intenta conectar a la red especificada. Version robusta."""
    log_path = "/home/keyon/keyon-terminal/logs/portal.log"
    
    def log(msg):
        with open(log_path, 'a') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        print(msg)
    
    try:
        log(f"=== Intentando conectar a: {ssid} ===")
        
        # 1. Bajar el hotspot ANTES de intentar conectar
        log("1. Desactivando hotspot KEYON-Setup...")
        subprocess.run(
            ['sudo', 'nmcli', 'connection', 'down', 'KEYON-Setup'],
            capture_output=True, timeout=10
        )
        time.sleep(3)
        
        # 2. Activar wlan0 en modo cliente
        log("2. Activando wlan0...")
        subprocess.run(
            ['sudo', 'nmcli', 'device', 'set', 'wlan0', 'managed', 'yes'],
            capture_output=True, timeout=5
        )
        time.sleep(2)
        
        # 3. Buscar conexiones existentes con este SSID
        log("3. Buscando conexiones existentes...")
        result = subprocess.run(
            ['nmcli', '-t', '-f', 'NAME,TYPE', 'connection', 'show'],
            capture_output=True, text=True, timeout=5
        )
        
        conexiones_a_borrar = []
        for line in result.stdout.strip().split('\n'):
            partes = line.split(':')
            if len(partes) >= 2 and partes[1] == '802-11-wireless':
                # Si el nombre contiene el SSID, marcarlo
                if ssid in partes[0] and partes[0] != 'KEYON-Setup':
                    conexiones_a_borrar.append(partes[0])
        
        # Borrar conexiones viejas con ese SSID
        for con in conexiones_a_borrar:
            log(f"   Eliminando conexion vieja: {con}")
            subprocess.run(
                ['sudo', 'nmcli', 'connection', 'delete', con],
                capture_output=True, timeout=10
            )
        time.sleep(2)
        
        # 4. Intentar conectar
        log(f"4. Conectando a {ssid}...")
        if password:
            cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid,
                   'password', password, 'ifname', 'wlan0']
        else:
            cmd = ['sudo', 'nmcli', 'device', 'wifi', 'connect', ssid,
                   'ifname', 'wlan0']
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        
        log(f"   stdout: {result.stdout.strip()}")
        log(f"   stderr: {result.stderr.strip()}")
        log(f"   returncode: {result.returncode}")
        
        if result.returncode == 0:
            log(f"=== EXITO: Conectado a {ssid} ===")
            return {'ok': True, 'mensaje': f'Conectado a {ssid}'}
        else:
            error = result.stderr.strip() or result.stdout.strip() or 'Error desconocido'
            log(f"=== FALLO: {error} ===")
            return {'ok': False, 'mensaje': error}
            
    except subprocess.TimeoutExpired:
        log("=== TIMEOUT ===")
        return {'ok': False, 'mensaje': 'Timeout al conectar (45s)'}
    except Exception as e:
        log(f"=== EXCEPCION: {e} ===")
        return {'ok': False, 'mensaje': str(e)}

# === Rutas Flask ===

@app.route('/')
def index():
    """Pagina principal con lista de redes."""
    redes = escanear_redes()
    return render_template('index.html', redes=redes)


@app.route('/conectar', methods=['POST'])
def conectar():
    """Endpoint que recibe SSID + password e intenta conectar."""
    ssid = request.form.get('ssid', '').strip()
    password = request.form.get('password', '').strip()
    
    if not ssid:
        return jsonify({'ok': False, 'mensaje': 'SSID requerido'}), 400
    
    print(f"[PORTAL] Intentando conectar a: {ssid}")
    resultado = conectar_a_red(ssid, password)
    
    if resultado['ok']:
        # Programar reboot en 5 segundos para aplicar cambios
        subprocess.Popen(['sudo', 'sh', '-c', 'sleep 5 && reboot'])
        return render_template('exito.html', ssid=ssid)
    else:
        return render_template('error.html', mensaje=resultado['mensaje'], ssid=ssid)


@app.route('/escanear')
def escanear_endpoint():
    """API JSON para refrescar lista de redes."""
    redes = escanear_redes()
    return jsonify({'redes': redes, 'total': len(redes)})


# === Captive portal magic ===
# Estos endpoints hacen que iOS/Android detecten el portal automaticamente

@app.route('/generate_204')        # Android
@app.route('/gen_204')              # Android moderno
@app.route('/hotspot-detect.html')  # iOS / macOS
@app.route('/library/test/success.html')  # iOS
@app.route('/connecttest.txt')      # Windows
@app.route('/ncsi.txt')             # Windows  
@app.route('/redirect')
def captive_redirect():
    """Captura cualquier check de captive portal y redirige a /"""
    return redirect(url_for('index'))


# === Catch-all para cualquier ruta no definida ===

@app.errorhandler(404)
def catch_all(e):
    return redirect(url_for('index'))


if __name__ == '__main__':
    # Puerto 80 requiere sudo o capabilities
    print("=" * 50)
    print("  KEYON Portal v0.1.0")
    print("  Captive portal para configuracion WiFi")
    print("=" * 50)
    print("Servidor: http://192.168.50.1")
    print("=" * 50)
    app.run(host='0.0.0.0', port=80, debug=False)
