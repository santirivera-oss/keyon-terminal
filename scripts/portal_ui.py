#!/usr/bin/env python3
"""
KEYON Portal UI v0.2.0 - Optimizado para LCD 320x480
"""
import tkinter as tk
from tkinter import font as tkfont
import qrcode
from PIL import Image, ImageTk
import sys

# === Config ===
HOTSPOT_SSID = "KEYON-Setup"
HOTSPOT_PASS = "keyon2026"
HOTSPOT_GATEWAY = "192.168.50.1"

# === Paleta KEYON Dark ===
BG = "#0c0c0c"
SURFACE = "#1a1a1a"
ACCENT = "#00d9ff"
PRIMARY = "#ffffff"
SECONDARY = "#a1a1aa"
BORDER = "#27272a"

# === Dimensiones LCD ===
SCREEN_W = 320
SCREEN_H = 480


def generar_qr_wifi():
    """QR con formato estandar WiFi (auto-conexion al escanear)."""
    qr_data = f"WIFI:T:WPA;S:{HOTSPOT_SSID};P:{HOTSPOT_PASS};;"
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=PRIMARY, back_color=BG)
    return img.convert("RGB")


def main():
    print("KEYON Portal UI v0.2.0")
    
    root = tk.Tk()
    root.title("KEYON Portal")
    root.attributes('-fullscreen', True)
    root.configure(bg=BG)
    root.geometry(f"{SCREEN_W}x{SCREEN_H}")
    root.config(cursor="none")
    root.bind('<Escape>', lambda e: root.destroy())
    root.bind('<q>', lambda e: root.destroy())
    
    # === Fuentes Inter (compactas) ===
    try:
        font_title = tkfont.Font(family="Inter", size=16, weight="bold")
        font_subtitle = tkfont.Font(family="Inter", size=9)
        font_label = tkfont.Font(family="Inter", size=8, weight="bold")
        font_value = tkfont.Font(family="Inter", size=10)
        font_small = tkfont.Font(family="Inter", size=7)
    except Exception:
        font_title = ("Helvetica", 16, "bold")
        font_subtitle = ("Helvetica", 9)
        font_label = ("Helvetica", 8, "bold")
        font_value = ("Helvetica", 10)
        font_small = ("Helvetica", 7)
    
    # === Linea cyan superior ===
    accent_line = tk.Frame(root, bg=ACCENT, height=2)
    accent_line.place(x=0, y=0, relwidth=1)
    
    # === HEADER (compacto) ===
    header_frame = tk.Frame(root, bg=BG, height=50)
    header_frame.pack(fill="x", pady=(8, 0))
    header_frame.pack_propagate(False)
    
    title_label = tk.Label(
        header_frame, text="KEYON",
        font=font_title, fg=PRIMARY, bg=BG
    )
    title_label.pack(pady=(2, 0))
    
    subtitle_label = tk.Label(
        header_frame, text="Configuración WiFi",
        font=font_subtitle, fg=SECONDARY, bg=BG
    )
    subtitle_label.pack(pady=(0, 2))
    
    # === Linea separadora ===
    sep = tk.Frame(root, bg=BORDER, height=1)
    sep.pack(fill="x", padx=20)
    
    # === QR CODE (170x170) ===
    qr_frame = tk.Frame(root, bg=BG)
    qr_frame.pack(pady=(10, 4))
    
    try:
        qr_img = generar_qr_wifi()
        qr_size = 170
        qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
        # Borde blanco sutil
        bordered = Image.new("RGB", (qr_size + 12, qr_size + 12), PRIMARY)
        bordered.paste(qr_img, (6, 6))
        qr_tk = ImageTk.PhotoImage(bordered)
        qr_label = tk.Label(qr_frame, image=qr_tk, bg=BG, bd=0)
        qr_label.image = qr_tk
        qr_label.pack()
        print(f"QR: {qr_size}x{qr_size}")
    except Exception as e:
        print(f"ERROR QR: {e}")
    
    # === Hint scan ===
    scan_hint = tk.Label(
        root, text="Escanea para conectar",
        font=font_small, fg=SECONDARY, bg=BG
    )
    scan_hint.pack(pady=(0, 6))
    
    # === DETALLES (compacto, 1 sola fila por dato) ===
    details_frame = tk.Frame(root, bg=SURFACE, padx=12, pady=8)
    details_frame.pack(fill="x", padx=20)
    
    # Helper para crear filas compactas
    def fila(label_text, value_text):
        row = tk.Frame(details_frame, bg=SURFACE)
        row.pack(fill="x", pady=2)
        
        tk.Label(
            row, text=label_text,
            font=font_label, fg=ACCENT, bg=SURFACE,
            anchor="w", width=12
        ).pack(side="left")
        
        tk.Label(
            row, text=value_text,
            font=font_value, fg=PRIMARY, bg=SURFACE,
            anchor="w"
        ).pack(side="left")
    
    fila("RED", HOTSPOT_SSID)
    fila("CONTRASEÑA", HOTSPOT_PASS)
    fila("ABRE EN", HOTSPOT_GATEWAY)
    
    # === FOOTER ===
    footer = tk.Label(
        root,
        text="KEYON Terminal Pro v2 · Exara Studio",
        font=font_small, fg=SECONDARY, bg=BG
    )
    footer.pack(side="bottom", pady=6)
    
    print("Mainloop")
    root.mainloop()


if __name__ == "__main__":
    main()
