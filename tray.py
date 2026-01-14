import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import sys
import os
import subprocess
import webbrowser
import threading
import time
import asyncio
import websockets
import logging


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Configuration
BRIDGE_URL = "wss://localhost:8181"
ICON_PATH = resource_path(os.path.join("assets", "icon.png"))

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - Tray - %(levelname)s - %(message)s')

class SpaceMouseTray:
    def __init__(self):
        self.icon = None
        self.connected = False
        self.running = True

    def create_image(self, status_color):
        # If asset icon exists, load it and overlay a status dot
        try:
            if os.path.exists(ICON_PATH):
                base = Image.open(ICON_PATH).convert("RGBA")
                # Resize for tray if needed, typically 64x64 is safe
                base.thumbnail((64, 64))
                
                # Create status dot
                dot = Image.new('RGBA', base.size, (0,0,0,0))
                draw = ImageDraw.Draw(dot)
                w, h = base.size
                # Draw dot in bottom right
                draw.ellipse((w-16, h-16, w, h), fill=status_color)
                
                return Image.alpha_composite(base, dot)
        except Exception as e:
            logging.error(f"Failed to screen icon: {e}")

        # Fallback: Generate simple image
        width = 64
        height = 64
        image = Image.new('RGB', (width, height), status_color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((width // 2 - 10, height // 2 - 10, width // 2 + 10, height // 2 + 10), fill='white')
        return image

    def on_open_config(self, icon, item):
        webbrowser.open("https://localhost:8181/config")

    def on_restart_service(self, icon, item):
        subprocess.run(["systemctl", "--user", "restart", "spacemouse-bridge.service"])

    def on_stop_service(self, icon, item):
        subprocess.run(["systemctl", "--user", "stop", "spacemouse-bridge.service"])

    def on_start_service(self, icon, item):
        subprocess.run(["systemctl", "--user", "start", "spacemouse-bridge.service"])
    
    def on_quit(self, icon, item):
        self.running = False
        icon.stop()

    async def check_connection(self):
        import ssl
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        while self.running:
            try:
                async with websockets.connect(BRIDGE_URL, ssl=ssl_context, subprotocols=["3dx-v1"]) as ws:
                    self.connected = True
                    self.update_icon()
                    logging.info("Connected to Bridge")
                    await ws.wait_closed()
            except Exception:
                self.connected = False
                self.update_icon()
                # logging.debug("Bridge not reachable")
            
            await asyncio.sleep(2)
            
    def update_icon(self):
        if self.icon:
            color = "green" if self.connected else "grey"
            self.icon.icon = self.create_image(color)
            self.icon.title = f"SpaceMouse xDesign: {'Connected' if self.connected else 'Disconnected'}"

    def run_monitor(self):
        asyncio.run(self.check_connection())

    def run(self):
        # Start Monitor Thread
        t = threading.Thread(target=self.run_monitor, daemon=True)
        t.start()

        # Build Menu
        menu = pystray.Menu(
            item('Open Configuration', self.on_open_config, default=True),
            item('Status: Connected', lambda i, it: None, enabled=False, visible=lambda i: self.connected),
            item('Status: Disconnected', lambda i, it: None, enabled=False, visible=lambda i: not self.connected),
            pystray.Menu.SEPARATOR,
            item('Restart Service', self.on_restart_service),
            item('Start Service', self.on_start_service, visible=lambda i: not self.connected),
            item('Stop Service', self.on_stop_service, visible=lambda i: self.connected),
            pystray.Menu.SEPARATOR,
            item('Quit Tray', self.on_quit)
        )

        self.icon = pystray.Icon(
            "spacemouse_tray",
            self.create_image("grey"),
            "SpaceMouse xDesign",
            menu
        )
        
        self.icon.run()

if __name__ == "__main__":
    app = SpaceMouseTray()
    app.run()
