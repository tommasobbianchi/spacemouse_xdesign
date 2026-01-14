import asyncio
import json
import math
import os
import logging
import http
import ssl
# import websockets # Replaced by aiohttp
from aiohttp import web, WSMsgType
import signal
import time
import random
import string
import struct
import struct
import struct
import subprocess
import webbrowser

# Dependencies for math
import numpy as np
# from scipy.spatial import transform  <-- Removed to lightweight packaging

import spnav_wrapper as spnav
from spnav_wrapper import SPNAV_EVENT_MOTION, SPNAV_EVENT_BUTTON
from uinput_wrapper import VirtualKeyboard

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Global Virtual Keyboard instance
vkab = None

# WAMP Constants
WAMP_WELCOME = 0
WAMP_PREFIX = 1
WAMP_CALL = 2
WAMP_CALLRESULT = 3
WAMP_CALLERROR = 4
WAMP_SUBSCRIBE = 5
WAMP_UNSUBSCRIBE = 6
WAMP_PUBLISH = 7
WAMP_EVENT = 8

def _rand_id(len=16) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=len))

# Global event queue for passing events from thread to async loop
event_queue = asyncio.Queue()

# Environment Fix for xdotool (GUI interaction)

# Load Configuration
def get_config_dir():
    xdg_config = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
    config_dir = os.path.join(xdg_config, 'spacemouse-bridge')
    os.makedirs(config_dir, exist_ok=True)
    return config_dir

CONFIG_DIR = get_config_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CERT_FILE = os.path.join(CONFIG_DIR, "cert.pem")
KEY_FILE = os.path.join(CONFIG_DIR, "key.pem")
DEFAULT_CONFIG = {
    "sensitivity": 1.0,
    "deadzone": 10,
    "gamma": 1.0,
    "spin_axis": "z", # or 'y'
    "buttons": {}
}


def discover_environ_var(var_name, process_names=["gnome-shell", "gnome-session", "plasmashell", "xfce4-session"]):
    """Attempts to find an environment variable from a running user session process."""
    try:
        user_uid = os.getuid()
        for pid in os.listdir('/proc'):
            if not pid.isdigit():
                continue
            try:
                # Check ownership
                stat = os.stat(f'/proc/{pid}')
                if stat.st_uid != user_uid:
                     continue
                
                # Check name
                try:
                    with open(f'/proc/{pid}/comm', 'r') as f:
                        comm = f.read().strip()
                except: continue
                
                if comm in process_names:
                    # Read environ
                    try:
                        with open(f'/proc/{pid}/environ', 'rb') as f:
                            env_data = f.read()
                        
                        env_vars = env_data.split(b'\0')
                        name_bytes = var_name.encode('utf-8') + b'='
                        for env in env_vars:
                            if env.startswith(name_bytes):
                                 value = env[len(name_bytes):].decode('utf-8')
                                 logging.info(f"Discovered {var_name} from {comm} (PID {pid}): {value}")
                                 return value
                    except Exception:
                        continue
            except (PermissionError, FileNotFoundError, OSError):
                continue
    except Exception as e:
        logging.warning(f"Error discovering {var_name}: {e}")
    return None

def init_environment():
    # Helper to setup DISPLAY, XAUTHORITY, DBUS, WAYLAND
    
    # DBUS_SESSION_BUS_ADDRESS (Crucial for Firefox/Webbrowser)
    if "DBUS_SESSION_BUS_ADDRESS" not in os.environ:
         db = discover_environ_var("DBUS_SESSION_BUS_ADDRESS")
         if db: os.environ["DBUS_SESSION_BUS_ADDRESS"] = db

    # WAYLAND_DISPLAY
    if "WAYLAND_DISPLAY" not in os.environ:
         wd = discover_environ_var("WAYLAND_DISPLAY")
         if wd:
             os.environ["WAYLAND_DISPLAY"] = wd
         else:
             # Check for socket explicitly if discovery fails
             uid = os.getuid()
             socket_path = f"/run/user/{uid}/wayland-0"
             if os.path.exists(socket_path):
                 logging.info(f"Inferred WAYLAND_DISPLAY from socket: {socket_path}")
                 os.environ["WAYLAND_DISPLAY"] = "wayland-0"

    # DISPLAY (Fallback to :0 if missing)
    if "DISPLAY" not in os.environ:
         d = discover_environ_var("DISPLAY")
         if d: 
             os.environ["DISPLAY"] = d
         else:
             os.environ["DISPLAY"] = ":0"
    
    # XAUTHORITY
    if "XAUTHORITY" not in os.environ:
         x = discover_environ_var("XAUTHORITY")
         if x: 
             os.environ["XAUTHORITY"] = x
         else:
             # Fallback Search
             uid = os.getuid()
             candidates = [
                 os.path.expanduser("~/.Xauthority"),
                 f"/run/user/{uid}/gdm/Xauthority",
                 f"/run/user/{uid}/.mutter-Xwaylandauth"
             ]
             # Also scan run dir for any *auth* file
             try:
                 run_dir = f"/run/user/{uid}"
                 if os.path.exists(run_dir):
                     for f in os.listdir(run_dir):
                         if "auth" in f:
                             candidates.append(os.path.join(run_dir, f))
             except: pass
             
             for c in candidates:
                 if os.path.exists(c):
                     logging.info(f"Found XAUTHORITY candidate: {c}")
                     os.environ["XAUTHORITY"] = c
                     break

    # XDG_RUNTIME_DIR (Mandatory for Wayland)

    # XDG_RUNTIME_DIR (Mandatory for Wayland)
    if "XDG_RUNTIME_DIR" not in os.environ:
        uid = os.getuid()
        runtime_dir = f"/run/user/{uid}"
        if os.path.exists(runtime_dir):
            os.environ["XDG_RUNTIME_DIR"] = runtime_dir
            logging.info(f"Set XDG_RUNTIME_DIR to {runtime_dir}")

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
    return DEFAULT_CONFIG

APP_CONFIG = load_config()

class Controller:
    """
    Manages the state and logic for a single connected client (xDesign session).
    """
    def __init__(self, websocket, client_metadata):
        self.ws = websocket
        self.client_metadata = client_metadata
        self.focus = False
        self.subscribed_topic = None
        self.in_flight_rpcs = {} # Map call_id -> Future
        self.id = "controller0"
        self.horizon_locked = False
        self.pending_rot_z = 0

    async def handle_update(self, args):
        """Handle 3dx_rpc:update calls."""
        if isinstance(args, list) and len(args) > 1:
            props = args[1]
            if "focus" in props:
                self.focus = props["focus"]
                logging.info(f"Client Focus changed to: {self.focus}")

    def resolve_rpc(self, call_id, result, error=None):
        if call_id in self.in_flight_rpcs:
            future = self.in_flight_rpcs[call_id]
            if not future.done():
                if error:
                    future.set_exception(Exception(error))
                else:
                    future.set_result(result)
            del self.in_flight_rpcs[call_id]

    # Math Logic from spacenav-ws
    @staticmethod
    def get_affine_pivot_matrices(model_extents):
        # Allow for empty/None extents safely
        if not model_extents or len(model_extents) < 6:
            return np.eye(4, dtype=np.float32), np.eye(4, dtype=np.float32)

        min_pt = np.array(model_extents[0:3], dtype=np.float32)
        max_pt = np.array(model_extents[3:6], dtype=np.float32)
        pivot = (min_pt + max_pt) * 0.5

        pivot_pos = np.eye(4, dtype=np.float32)
        pivot_pos[3, :3] = pivot
        pivot_neg = np.eye(4, dtype=np.float32)
        pivot_neg[3, :3] = -pivot
        return pivot_pos, pivot_neg

    # DISPLAY
    # This function is not defined in the provided context, assuming it's a placeholder or external.
    # def discover_environ_var(var_name):
    #     # Placeholder for actual discovery logic
    #     return None

    # if "DISPLAY" not in os.environ:
    #      d = discover_environ_var("DISPLAY")
    #      if d:
    #          os.environ["DISPLAY"] = d
    #      else:
    #          # Fallback default
    #          os.environ["DISPLAY"] = ":0"
    
    # WAYLAND_DISPLAY (Check for socket presence)
    if "WAYLAND_DISPLAY" not in os.environ:
         # wd = discover_environ_var("WAYLAND_DISPLAY") # Assuming discover_environ_var is defined elsewhere
         wd = None # Placeholder
         if wd:
             os.environ["WAYLAND_DISPLAY"] = wd
         else:
             # Check for socket
             uid = os.getuid()
             socket_path = f"/run/user/{uid}/wayland-0"
             if os.path.exists(socket_path):
                 logging.info(f"Inferred WAYLAND_DISPLAY from socket: {socket_path}")
                 os.environ["WAYLAND_DISPLAY"] = "wayland-0"

    # XAUTHORITY
    # if "XAUTHORITY" not in os.environ: # Assuming this was part of the environment setup
    #     # Placeholder for XAUTHORITY discovery
    #     pass

    def apply_gamma(self, val, gamma):
        """
        Applies non-linear response curve.
        Formula: value = sign * (|value| / max_range) ^ gamma * max_range
        Assumes max_range approx 350.0 for SpaceMouse.
        """
        if val == 0: return 0
        MAX_RANGE = 350.0
        
        # Normalize
        norm = abs(val) / MAX_RANGE
        # Clamp to 1.0 to avoid explosion if driver reports > 350
        if norm > 1.0: norm = 1.0
        
        # Curve
        curved = pow(norm, gamma)
        
        # Denormalize
        return math.copysign(curved * MAX_RANGE, val)

    async def process_motion(self, event):
        """Handle motion events (6-DOF)."""
        # Get Config
        global APP_CONFIG
        scale_speed = APP_CONFIG.get("sensitivity", 1.0)
        
        # Robust handling for legacy config structure (dict vs float)
        if isinstance(scale_speed, dict):
            scale_speed = scale_speed.get("translation", 1.0)
        
        # DEBUG: Log raw input occasionally to verify driver liveness
        if event.motion.x != 0:
             logging.debug(f"Input: {event.motion.x}")
        
        deadzone = APP_CONFIG.get("deadzone", 10)
        gamma = APP_CONFIG.get("gamma", 1.0)
        
        # Raw Data
        t = event.motion
        tx, ty, tz = t.x, t.y, t.z
        rx, ry, rz = t.rx, t.ry, t.rz
        
        # Apply Deadzone & Gamma
        def process_axis(val):
            if abs(val) < deadzone: return 0
            if hasattr(self, 'apply_gamma'):
                return self.apply_gamma(val, gamma)
            # Self-contained fallback in case helper is missing
            MAX_RANGE = 350.0
            norm = abs(val) / MAX_RANGE
            if norm > 1.0: norm = 1.0
            curved = pow(norm, gamma)
            return math.copysign(curved * MAX_RANGE, val)

        tx = process_axis(tx)
        ty = process_axis(ty)
        tz = process_axis(tz)
        rx = process_axis(rx)
        ry = process_axis(ry)
        rz = process_axis(rz)
        
        # Scale Factors (tuned for xDesign)
        # Translation: Map +/- 350 to +/- 100 units approx
        trans_scale = (scale_speed * 0.5) / 350.0
        
        # Rotation: Map +/- 350 to degrees
        rot_scale = (scale_speed * 10.0) / 350.0 
        
        # Use simple adaptive scale if needed
        # Note: 'dist' was from Pivot calculation which is context-dependent.
        # For robustness, we use static scale first, then later we can re-add pivot logic if needed.
        # But 'process_motion' usually contained the Pivot logic.
        # Im re-inserting the FULL logic including Pivot reading.
        
        if not self.focus:
            self.focus = True
            
        if not self.subscribed_topic:
            # logging.debug("No subscribed topic. Ignoring motion.")
            return

        try:
            # 1. Read current state
            perspective = await self.remote_read("view.perspective")
            affine_data = await self.remote_read("view.affine")
            if not affine_data: 
                logging.warning("remote_read('view.affine') returned None")
                return
            
            curr_affine = np.asarray(affine_data, dtype=np.float32).reshape(4, 4)
            
            # 2. Calculate Rotation
            R_cam = curr_affine[:3, :3].T
            U, _, Vt = np.linalg.svd(R_cam)
            R_cam = U @ Vt
            
            model_extents = await self.remote_read("model.extents") or [0,0,0,0,0,0]
            
            # Pivot calc
            min_pt = np.array(model_extents[0:3], dtype=np.float32)
            max_pt = np.array(model_extents[3:6], dtype=np.float32)
            pivot_world = (min_pt + max_pt) * 0.5
            
            pivot_world_h = np.append(pivot_world, 1.0)
            pivot_cam = pivot_world_h @ curr_affine
            dist = np.linalg.norm(pivot_cam[:3])
            dist = max(dist, 1.0)

            # Adaptive Scale
            adaptive_scale = trans_scale * dist
            
            trans_vec = np.array([-tx, -ty, -tz], dtype=np.float32) * adaptive_scale
            
            # Rotation Math
            rx_rad = np.radians(rx * rot_scale)
            ry_rad = np.radians(ry * rot_scale)
            rz_rad = np.radians(-rz * rot_scale)
            
            cx, sx = np.cos(rx_rad), np.sin(rx_rad)
            cy, sy = np.cos(ry_rad), np.sin(ry_rad)
            cz, sz = np.cos(rz_rad), np.sin(rz_rad)
            
            Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
            Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
            
            R_delta_cam = Rx @ Ry @ Rz
            
            if self.pending_rot_z != 0:
                 # Spin logic (Screen Z axis rotation)
                 logging.info(f"Applying Spin 90: {self.pending_rot_z}")
                 angle = self.pending_rot_z
                 ca, sa = np.cos(angle), np.sin(angle)
                 # Rotate around Z axis
                 R_spin = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]])
                 
                 # Combine with current motion (Spin applied effectively "after" or "on top" of user input)
                 R_delta_cam = R_spin @ R_delta_cam
                 
                 self.pending_rot_z = 0 
            
            R_world = R_cam @ R_delta_cam @ R_cam.T
            
            rot_delta = np.eye(4, dtype=np.float32)
            rot_delta[:3, :3] = R_world
            
            trans_delta = np.eye(4, dtype=np.float32)
            trans_delta[3, :3] = trans_vec
            
            # Apply
            pivot_pos, pivot_neg = self.get_affine_pivot_matrices(model_extents)
            new_affine = trans_delta @ curr_affine @ (pivot_neg @ rot_delta @ pivot_pos)
            
            await self.remote_write("motion", True)
            await self.remote_write("view.affine", new_affine.reshape(-1).tolist())

        except Exception as e:
            logging.error(f"Motion Error: {e}")

    async def remote_read(self, property_name):
        return await self.client_rpc("self:read", property_name)

    async def process_button(self, event):
        """Handle button events."""
        bnum = event.button.bnum
        is_press = event.button.press != 0
        logging.info(f"Button Event: ID={bnum}, Press={is_press}")

        button_id_str = str(bnum)
        buttons_config = APP_CONFIG.get("buttons", {})
        
        if button_id_str in buttons_config:
            b_conf = buttons_config[button_id_str]
            action = b_conf.get("action")
            value = b_conf.get("value")
            
            if action == "key" and is_press:
                # Use Virtual Keyboard
                if vkab:
                     vkab.press_combo(value)
                     logging.info(f"Button {bnum}: Key {value}")
                
            elif action == "modifier":
                if vkab:
                     vkab.press_combo(value)
                     logging.info(f"Button {bnum}: Modifier {value}")
                
            elif action == "logic" and is_press:
                if value == "lock_horizon":
                    self.horizon_locked = not self.horizon_locked
                    logging.info(f"Horizon Lock: {self.horizon_locked}")
                    
                elif value == "spin_90":
                    self.pending_rot_z = -math.pi / 2
                    logging.info("Spin 90 requested. Triggering immediate motion update.")
                    
                    # Create a dummy zero-motion event to force process_motion to run immediately
                    # We can't easily construct a SpaceNav event here without spnav module
                    # But process_motion just takes an object with .motion.x etc.
                    class DummyEvent:
                        class Motion:
                            x=0; y=0; z=0; rx=0; ry=0; rz=0
                        motion = Motion()
                    
                    await self.process_motion(DummyEvent())



            elif action == "open_browser" and is_press:
                # Open Config UI URL via HTTP
                url = "https://localhost:8181/config"
                # Force explicit launch to ensure window appears
                # webbrowser.open returns True but fails to show window in some service contexts
                try:
                    # Log the environment we are using
                    logging.info(f"Launching Firefox with env: DISPLAY={os.environ.get('DISPLAY')}, WAYLAND={os.environ.get('WAYLAND_DISPLAY')}, DBUS={os.environ.get('DBUS_SESSION_BUS_ADDRESS')}")
                    
                    subprocess.Popen(["firefox", "--new-window", url], env=os.environ)
                    logging.info(f"Button {bnum}: Opened Config UI (subprocess firefox)")
                except Exception as e:
                    logging.error(f"Failed to launch firefox subprocess: {e}")
                    # Safe fallback
                    webbrowser.open(url, new=1)

    async def remote_write(self, property_name, value):
        # spacenav-ws uses "self:update" NOT "self:write"
        return await self.client_rpc("self:update", property_name, value)

    async def client_rpc(self, method, *args):
        """
        Execute an RPC on the client.
        We emulate spacenav-ws structure exactly.
        """
        if not self.subscribed_topic:
            return None

        call_id = _rand_id()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.in_flight_rpcs[call_id] = future

        # Construct Call: [2, callID, method, args...]
        # CRITICAL QUIRK: spacenav-ws inserts an empty string before the first argument!
        rpc_args = ["", *args]
        
        call_msg = [WAMP_CALL, call_id, method, *rpc_args]
        
        # Wrap in Event: [8, topic, payload]
        event_msg = [WAMP_EVENT, self.subscribed_topic, call_msg]
        
        try:
            # logging.debug(f"RPC OUT: {event_msg}")
            await self.ws.send_str(json.dumps(event_msg))
            result = await asyncio.wait_for(future, timeout=0.5)
            # logging.debug(f"RPC RES: {result}")
            return result
        except asyncio.TimeoutError:
            # logging.debug(f"RPC Timed out: {method}")
            if call_id in self.in_flight_rpcs:
                del self.in_flight_rpcs[call_id]
            return None
        except Exception as e:
            logging.error(f"RPC Failed ({method}): {e}")
            if call_id in self.in_flight_rpcs:
                del self.in_flight_rpcs[call_id]
            return None

# ---------------------------------------------------------
# WebSocket / WAMP Logic
# ---------------------------------------------------------

connected_controllers = {} # websocket -> Controller
start_time = time.time()

async def handle_options(request):
    """
    Handle CORS Preflight / Private Network Access (PNA)
    """
    logging.info(f"OPTIONS request: {request.path}")
    origin = request.headers.get("Origin", "*")
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Private-Network": "true"
    }
    return web.Response(text="OK", headers=headers)

async def handle_config(request):
    """Serve Config UI"""
    logging.debug("Serving Config UI")
    try:
        with open("config_ui/index.html", "r") as f:
            content = f.read()
        origin = request.headers.get("Origin", "*")
        headers = {
            "Content-Type": "text/html", 
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Private-Network": "true"
        }
        return web.Response(text=content, headers=headers)
    except Exception as e:
        return web.Response(text=f"Error: {e}", status=500)

async def handle_websocket(request):
    """
    Handle WebSocket connection (both WAMP and Config)
    """
    # Check if this is a WebSocket upgrade
    if request.headers.get("Upgrade", "").lower() != "websocket":
        # Check if browser visiting root -> Redirect to Config
        accept = request.headers.get("Accept", "").lower()
        if request.path == "/" and "text/html" in accept:
            return web.HTTPFound("/config")

        # Handle standard HTTP GET probe (xDesign expects this at /)
        logging.info(f"HTTP GET probe from {request.remote} path={request.path}")
        data = {"port": 8181, "version": "1.4.8.21486"}
        origin = request.headers.get("Origin", "*")
        
        # PNA / CORS headers for Probe
        headers = {
            "Content-Type": "application/json", 
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Private-Network": "true"
        }
        return web.Response(text=json.dumps(data), headers=headers)

    ws = web.WebSocketResponse(protocols=("wamp", "3dx-v1"))
    try:
        await ws.prepare(request)
    except Exception as e:
        logging.error(f"WebSocket handshake failed: {e}")
        return ws
    
    logging.info(f"New connection: {request.remote}")
    
    global APP_CONFIG
    
    # Create controller
    controller = Controller(ws, {})
    connected_controllers[ws] = controller
    
    try:
        # 1. Send WELCOME
        session_id = _rand_id()
        # [0, sessionID, 1, ident]
        await ws.send_str(json.dumps([WAMP_WELCOME, session_id, 1, "AntigravityBridge"]))
        
        async for msg in ws:
            logging.info(f"WS RAW: Type={msg.type} Data={msg.data!r}")
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    logging.debug(f"WS RX: {data}")
                    msg_type = data[0]
                    
                    if msg_type == WAMP_PREFIX:
                        pass 
                        
                    elif msg_type == WAMP_CALL:
                        call_id = data[1]
                        proc = data[2]
                        args = data[3:]
                        
                        if "create" in proc:
                            if args and "3dmouse" in args[0]:
                                 await ws.send_str(json.dumps([WAMP_CALLRESULT, call_id, {"connexion": "mouse0"}]))
                            elif args and "3dcontroller" in args[0]:
                                 meta = args[2] if len(args) > 2 else {}
                                 controller.client_metadata = meta
                                 logging.info(f"Client Metadata: {meta}")
                                 await ws.send_str(json.dumps([WAMP_CALLRESULT, call_id, {"instance": "controller0"}]))
                        
                        elif "update" in proc:
                            await controller.handle_update(args)
                            await ws.send_str(json.dumps([WAMP_CALLRESULT, call_id, None]))
    
                        elif "config.get" in proc:
                            await ws.send_str(json.dumps([WAMP_CALLRESULT, call_id, APP_CONFIG]))
    
                        elif "config.set" in proc:
                            try:
                                new_conf = args[0]
                                APP_CONFIG = new_conf
                                with open(CONFIG_PATH, "w") as f:
                                    json.dump(APP_CONFIG, f, indent=4)
                                logging.info("Config updated via RPC")
                                await ws.send_str(json.dumps([WAMP_CALLRESULT, call_id, "OK"]))
                            except Exception as e:
                                logging.error(f"Config update failed: {e}")
                                await ws.send_str(json.dumps([WAMP_CALLERROR, call_id, str(e)]))
                            
                        else:
                            await ws.send_str(json.dumps([WAMP_CALLRESULT, call_id, None]))
    
                    elif msg_type == WAMP_SUBSCRIBE:
                        topic = data[1]
                        logging.info(f"Subscribed to: {topic}")
                        controller.subscribed_topic = topic
                        
                    elif msg_type == WAMP_CALLRESULT:
                        call_id = data[1]
                        res = data[2]
                        controller.resolve_rpc(call_id, res)
                        
                    elif msg_type == WAMP_CALLERROR:
                        call_id = data[1]
                        err = data[2]
                        controller.resolve_rpc(call_id, None, error=err)
                        
                except Exception as e:
                    logging.error(f"Error handling msg: {e}")
            
            elif msg.type == WSMsgType.ERROR:
                logging.error('ws connection closed with exception %s', ws.exception())

    finally:
        if ws in connected_controllers:
            del connected_controllers[ws]
        logging.info("WebSocket Closed")

    return ws

# ---------------------------------------------------------
# Spacenav Handler (Thread)
# ---------------------------------------------------------

def spacenav_thread_func():
    logging.info("Spacenav thread started.")
    
    while True:
        # 1. Connection Loop
        connected = False
        try:
            spnav.spnav_open()
            connected = True
            logging.info("Connected to spacenavd.")
        except spnav.SpnavError:
            # logging.error("Failed to connect to spacenavd. Retrying in 2s...")
            time.sleep(2)
            continue
        except Exception as e:
            logging.error(f"Unexpected error connecting to spacenavd: {e}")
            time.sleep(2)
            continue
            
        # 2. Event Loop
        while connected:
            try:
                event = spnav.spnav_wait_event()
                if event:
                    if event.type == SPNAV_EVENT_MOTION or event.type == SPNAV_EVENT_BUTTON:
                        if event_queue_loop:
                             asyncio.run_coroutine_threadsafe(event_queue.put(event), event_queue_loop)
                else:
                    # No event, check if connection is still alive?
                    # Since spnav_wait_event is non-blocking or blocking depending on impl,
                    # receiving None constantly in non-blocking mode is normal.
                    time.sleep(0.01)

            except Exception as e:
                logging.error(f"Spacenav loop error: {e}. Reconnecting...")
                try:
                    spnav.spnav_close()
                except:
                    pass
                connected = False
                time.sleep(1)

    # Should not reach here

event_queue_loop = None



async def broadcast_loop():
    logging.info("Starting broadcast loop")
    while True:
        event = await event_queue.get()
        # Process for ALL connected active controllers
        # (Usually only one active)
        tasks = []
        for ctrl in connected_controllers.values():
            if event.type == SPNAV_EVENT_MOTION:
                tasks.append(asyncio.create_task(ctrl.process_motion(event)))
            elif event.type == SPNAV_EVENT_BUTTON:
                 tasks.append(asyncio.create_task(ctrl.process_button(event)))
        
        if tasks:
            await asyncio.gather(*tasks)


def ensure_ssl_certs(cert_file, key_file):
    """
    Checks for existence of SSL certs. If missing, generates a self-signed cert
    using OpenSSL to allow the WSS server to start securely.
    """
    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        logging.warning("SSL certificates not found. Generating self-signed certificate...")
        try:
            # Generate key and cert in one go (valid for 365 days)
            # Add Subject Alternative Names for Chrome PNA compatibility
            cmd = [
                "openssl", "req", "-x509",
                "-newkey", "rsa:2048",
                "-keyout", key_file,
                "-out", cert_file,
                "-days", "365",
                "-nodes",
                "-subj", "/CN=localhost",
                "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:127.51.68.120"
            ]
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info("Self-signed certificate generated successfully.")
        except Exception as e:
            logging.error(f"Failed to generate SSL certs: {e}")
            raise


async def on_startup(app):
    init_environment()
    ensure_ssl_certs(CERT_FILE, KEY_FILE)
    
    # Initialize Virtual Keyboard
    global vkab
    vkab = VirtualKeyboard()
    
    # Start broadcast consumer
    app['broadcast_task'] = asyncio.create_task(broadcast_loop())
    
    # Start input producer thread
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, spacenav_thread_func)
    
    logging.info("Bridge Service Started (aiohttp)")

async def capture_loop_ref(app):
    global event_queue_loop
    event_queue_loop = asyncio.get_running_loop()


@web.middleware
async def monitor_middleware(request, handler):
    # Log valid probes/pings at DEBUG level to avoid spam, errors/others at INFO
    if request.path == "/" or request.path == "/3dconnexion/nlproxy":
         logging.debug(f"INCOMING: {request.method} {request.path} Origin={request.headers.get('Origin')}")
    else:
         logging.info(f"INCOMING: {request.method} {request.path} Origin={request.headers.get('Origin')}")
    
    # Handle OPTIONS globally if no specific route matched (Optional, but safe)
    if request.method == "OPTIONS":
        # Check if route exists? well, if handler is default 404/405, we intercept
        # But aiohttp middleware wraps the handler.
        pass

    try:
        response = await handler(request)
    except web.HTTPException as ex:
        response = ex
    except Exception as e:
        logging.error(f"Server Error: {e}")
        response = web.Response(status=500, text=str(e))

    # Force CORS/PNA headers
    origin = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    # response.headers["Access-Control-Allow-Credentials"] = "true" # Optional, risky with *
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    
    return response

async def on_shutdown(app):
    logging.info("Shutting down app...")
    if 'broadcast_task' in app:
         app['broadcast_task'].cancel()
         try:
             await app['broadcast_task']
         except asyncio.CancelledError:
             pass
    logging.info("Shutdown complete.")
    # Force exit to prevent hanging on thread join or aiohttp cleanup
    os._exit(0)

if __name__ == "__main__":
    app = web.Application(middlewares=[monitor_middleware])
    
    # CORS
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)
    
    # Config UI
    app.router.add_get("/", handle_websocket) # Root handles Probe (JSON) or Redirect
    app.router.add_get("/config", handle_config)

    
    # WebSocket
    app.router.add_get("/3dconnexion/nlproxy", handle_websocket)
    
    # Hooks
    app.on_startup.append(capture_loop_ref) # CRITICAL: Set global loop var first
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # SSL
    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(CERT_FILE, KEY_FILE)
    
    # Run
    # Run
    # Listen on both IPv4 and IPv6
    web.run_app(app, host=["0.0.0.0", "::"], port=8181, ssl_context=ssl_context, access_log=None)
