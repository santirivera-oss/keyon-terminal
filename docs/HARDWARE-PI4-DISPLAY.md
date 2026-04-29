# Hardware Setup — Raspberry Pi 4 + 3.5" SPI Display

Documentación de la configuración hardware para KEYON Terminal Pro v2 sobre Raspberry Pi 4 con pantalla SPI 3.5" ILI9486.

## Hardware

| Componente | Modelo | Notas |
|---|---|---|
| SBC | Raspberry Pi 4 Model B 1GB | Migración desde Pi Zero 2W (v2.0.4-dev y anteriores) |
| Pantalla | 3.5" SPI ILI9486 (480x320) | Genérica MPI3501-compatible con XPT2046 touch |
| Cámara | Logitech C270 HD Webcam | UVC USB |
| OS | Debian 13 Trixie 64-bit | Kernel 6.12.75+ |
| Ventilador | Carcasa acrílica con disipadores | Conectado a 5V/GND del GPIO |

## Configuración de pantalla SPI

### Editar config.txt

`sudo nano /boot/firmware/config.txt`

Agregar al final del archivo:
=== KEYON Display - MPI3501 3.5" SPI ILI9486 ===
dtoverlay=piscreen,drm,speed=18000000,rotate=90
hdmi_force_hotplug=1

### Reiniciar

`sudo reboot`

### Validación

`dmesg | grep ili9486` debe mostrar:
[drm] Initialized ili9486 1.0.0 for spi0.0 on minor 2
ili9486 spi0.0: [drm] fb0: ili9486drmfb frame buffer device

`ls /sys/class/drm/` debe incluir `card2-SPI-1`.

## Touch (XPT2046/ADS7846)

El touch se detecta automáticamente con el dtoverlay `piscreen,drm`. No requiere configuración adicional a nivel kernel.

### Validación del touch

```bash
sudo apt install evtest
sudo evtest
```

Seleccionar el dispositivo `ADS7846 Touchscreen`. Tocar la pantalla genera eventos:

- `EV_ABS / ABS_X` (0-4095)
- `EV_ABS / ABS_Y` (0-4095)
- `EV_ABS / ABS_PRESSURE` (0-255)
- `EV_KEY / BTN_TOUCH`

### Touch en KEYON kiosk

KEYON debe leer eventos directamente del device file `/dev/input/eventX` (donde X corresponde al ADS7846 Touchscreen, típicamente event4):

```python
import evdev
device = evdev.InputDevice('/dev/input/event4')
for event in device.read_loop():
    if event.type == evdev.ecodes.EV_KEY:
        if event.code == evdev.ecodes.BTN_TOUCH and event.value == 1:
            handle_touch_event()
```

Esto evita la complejidad de configurar Wayland/X11 para el touch.

## Migración Pi Zero 2W → Pi 4

### Cambios en código (terminal_main.py)

| Variable | Pi Zero 2W | Pi 4 |
|---|---|---|
| TERMINAL_ID | `keyon-pi-zero2w-01` | `keyon-pi4-01` |
| dispositivo | `Raspberry Pi Zero 2W` | `Raspberry Pi 4 Model B` |
| ffmpeg frame select | `eq(n,5)` | `eq(n,15)` |

El cambio de frame es por la mayor velocidad de USB 3.0 en Pi 4: el sensor C270 necesita más frames de warm-up para auto-calibrar exposición.

## Métricas validadas en Pi 4

| Métrica | Pi Zero 2W (histórico) | Pi 4 |
|---|---|---|
| Boot a operativa | 49s | 22s |
| Cosine score máximo | 0.834 | 0.874 |
| L2 score mínimo | 0.577 | 0.502 |
| YuNet detection confidence | 92-95% | 92-94% |
| RAM usada en operación | ~225 MB | ~300 MB |
| Temperatura idle | 42-48°C | 37-41°C |
| Temperatura en carga | 50-55°C | 45-50°C |

## Notas de arquitectura

La migración a Pi 4 simplificó la arquitectura del kiosco:

- **Versión anterior:** Pi Zero 2W + ESP32 + pantalla SPI (3 placas, 2 fuentes, 9 cables)
- **Versión Pi 4:** Pi 4 + pantalla SPI (1 placa, 1 fuente, 0 cables externos)

La Pi 4 tiene CPU suficiente para manejar tanto el procesamiento de IA (OpenCV + YuNet + SFace) como el renderizado de UI directamente en GPIO, sin necesidad del controlador secundario ESP32.
