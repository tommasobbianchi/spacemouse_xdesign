import asyncio
import json
import os
import logging
import http
import ssl
import websockets
from websockets.http11 import Response, Headers
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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
CONFIG_PATH = "config.json"
DEFAULT_CONFIG = {
    "sensitivity": {
        "translation": 0.00015,
        "rotation": 0.01,
        "zoom": 0.00003
    },
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

    async def remote_read(self, property_name):
        """Read a property from the client via RPC."""
        # Try full URI: "3dconnexion:3dcontroller/controller0:read" ?
        # Or just "read" ?
        # spacenav-ws uses "self:read" which relies on prefixes.
        # "self" -> "3dconnexion:3dcontroller/controller0"
        
        # Let's try explicit full, but properly formatted.
        # If I am 'controller0', and I want to call 'read' on myself (the client mirror):
        # The client might have registered "3dconnexion:3dcontroller/controller0#read" ??
        
        # Let's try just "read" first, as "self:read" failed.
        # Wait, if I am the controller, the client called CREATE on me.
        # The client is the "caller" usually. 
        # But here server calls client.
        
        # Let's try:
        return await self.client_rpc("read", property_name)

    async def remote_write(self, property_name, value):
        """Write a property to the client via RPC."""
        return await self.client_rpc("write", property_name, value)

    async def client_rpc(self, method, *args):
        """
        Execute an RPC on the client.
        Structure matches spacenav-ws:
        WAMP EVENT [8, topic, payload]
        Payload is a serialized WAMP CALL [2, callID, method, args] WITH MSG_TYPE included.
        """
        if not self.subscribed_topic:
            return None

        call_id = _rand_id()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.in_flight_rpcs[call_id] = future

        # Construct Call: [2, callID, method, args...]
        # spacenav-ws: call.serialize_with_msg_id() -> [2, call_id, proc_uri, *args]
        # args passed here are already a list in *args tuple
        # But we need to be careful about nesting.
        # method="self:read", args=("view.affine",)
        
        # Correct structure: [2, call_id, method, arg1, arg2...]
        # NOT [2, call_id, method, [args]]
        call_msg = [WAMP_CALL, call_id, method, *args]
        
        # Wrap in Event: [8, topic, payload]
        # Payload IS the call message list
        event_msg = [WAMP_EVENT, self.subscribed_topic, call_msg]
        
        try:
            # logging.debug(f"Sending RPC: {event_msg}")
            await self.ws.send(json.dumps(event_msg))
            # Wait for result with a timeout
            result = await asyncio.wait_for(future, timeout=1.0)
            return result
        except asyncio.TimeoutError:
            logging.error(f"RPC Timed out: {method}")
            if call_id in self.in_flight_rpcs:
                del self.in_flight_rpcs[call_id]
            return None
        except Exception as e:
            logging.error(f"RPC Failed: {e}")
            if call_id in self.in_flight_rpcs:
                del self.in_flight_rpcs[call_id]
            return None

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

    async def process_motion(self, event):
        # ACTIVE CONTROL MODE
        # We try to read/write camera properties.
        
        if not self.focus:
            # Force focus just in case
            self.focus = True
            
        if not self.subscribed_topic:
            return

        # 1. Read current state
        try:
            # We assume these properties exist on the client (Onshape-like)
            perspective = await self.remote_read("view.perspective")
            
            # Affine matrix (4x4 flattened)
            affine_data = await self.remote_read("view.affine")
            if not affine_data:
                return
            
            curr_affine = np.asarray(affine_data, dtype=np.float32).reshape(4, 4)
            
            # 2. Calculate Rotation (Restore missing block)
            # Transpose of top-left 3x3
            R_cam = curr_affine[:3, :3].T
            # Orthogonalize using SVD to correct drift
            U, _, Vt = np.linalg.svd(R_cam)
            R_ortho = U @ Vt
            
            # Ensure determinant is +1 (Rotation) not -1 (Reflection)
            if np.linalg.det(R_ortho) < 0:
                # Flip the last row of Vt (or column of U)
                Vt[-1, :] *= -1
                R_ortho = U @ Vt
                
            R_cam = R_ortho
            model_extents = await self.remote_read("model.extents") or [0,0,0,0,0,0]

            # Calculate Pivot (Model Center in World Space)
            min_pt = np.array(model_extents[0:3], dtype=np.float32)
            max_pt = np.array(model_extents[3:6], dtype=np.float32)
            pivot_world = (min_pt + max_pt) * 0.5
            
            # Pivot in Camera Space (View Matrix * Pivot_World)
            # View Matrix is curr_affine (assumed Col-Major in GL, but NumPy is Row-Major? 
            # xDesign sends Row-Major: [R0, R1, R2, 0, R4, R5... Tx, Ty, Tz, 1] ?
            # `curr_affine` shape is (4,4).
            # We treat it as: Point_Cam = Point_World @ curr_affine
            
            pivot_world_h = np.append(pivot_world, 1.0) # Homogeneous
            pivot_cam = pivot_world_h @ curr_affine
            
            # Distance from Camera (Origin 0,0,0) to Pivot
            dist = np.linalg.norm(pivot_cam[:3])
            
            # Adaptive Speed
            # Base speed multiplier. We need to tune this.
            # If dist is 100mm, we want speed ~ 100 * k.
            # Previously constant scale was 0.0005. 
            # Let's say typical distance is 100-500 units.
            # If dist=200, 200 * k = 0.0005 -> k = 2.5e-6
            # Lets try multiplying the constant scale by (dist / reference_dist)
            # Reference distance = 100 units?
            
            # Clamp distance to avoid locking up when super close
            dist = max(dist, 1.0) 
            
            # New Scaling logic
            # trans_scale = 0.0005 * (dist / 100.0)
            # Effective: 5.0e-6 * dist
            # User reported "really slow". Increasing by 10x to 5.0e-5
            
            adaptive_scale = APP_CONFIG["sensitivity"]["translation"] * dist
            
            # Usually rotation is angle-based, so constant is fine.
            # User reported Y/Z rotation "not working". Likely too slow.
            # Increasing by 20x (was 0.0005 -> 0.01)
            rot_scale = APP_CONFIG["sensitivity"]["rotation"]
            
            tx, ty, tz = event.motion.x, event.motion.y, event.motion.z
            rx, ry, rz = event.motion.rx, event.motion.ry, event.motion.rz

            if self.horizon_locked:
                # User request: "zoom in/out and rotation blocked, only pan left/right and up down allowed"
                tz = 0
                rx = ry = rz = 0


            # AXIS REMAPPING (Feedback Round 7)
            # Zoom "not working"? Maybe sensitivity or axis issue.
            # Rot Z "inverted".
            
            trans_vec = np.array([-tx, -ty, -tz], dtype=np.float32) * adaptive_scale

            # INPUT DEBUGGING
            # if abs(tx) > 10 or abs(ty) > 10 or abs(tz) > 10:
            #      logging.info(f"Input: t=({tx}, {ty}, {tz}) r=({rx}, {ry}, {rz})")
            #      logging.info(f"TransVec: {trans_vec} (Scale: {adaptive_scale})")
            
            # Rotations:
            # X (Pitch): rx 
            # Y (Roll): ry 
            # Z (Spin): -rz 
            
            # Manually compute Rotation Matrix from Euler XYZ (degrees)
            # angles = np.array([rx, ry, -rz]) * rot_scale
            # R_delta_cam = transform.Rotation.from_euler("xyz", angles, degrees=True).as_matrix()
            
            # Optimization: Use NumPy for individual axis rotations
            rx_rad = np.radians(rx * rot_scale)
            ry_rad = np.radians(ry * rot_scale)
            rz_rad = np.radians(-rz * rot_scale)
            
            cx, sx = np.cos(rx_rad), np.sin(rx_rad)
            cy, sy = np.cos(ry_rad), np.sin(ry_rad)
            cz, sz = np.cos(rz_rad), np.sin(rz_rad)
            
            # Rx
            Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
            # Ry
            Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            # Rz
            Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
            
            # R = Rx @ Ry @ Rz (Intrinsic x-y-z)
            R_delta_cam = Rx @ Ry @ Rz
            
            # Apply Discrete Spin if pending
            if self.pending_rot_z != 0:
                theta = np.radians(self.pending_rot_z)
                c, s = np.cos(theta), np.sin(theta)
                # Determine Axis from Config
                axis = APP_CONFIG.get("spin_axis", "z").lower()
                
                if axis == "x":
                    R_spin = np.array([
                        [1, 0,  0],
                        [0, c, -s],
                        [0, s,  c]
                    ], dtype=np.float32)
                elif axis == "y":
                    R_spin = np.array([
                        [ c, 0, s],
                        [ 0, 1, 0],
                        [-s, 0, c]
                    ], dtype=np.float32)
                else: # Default Z
                    R_spin = np.array([
                        [c, -s, 0],
                        [s,  c, 0],
                        [0,  0, 1]
                    ], dtype=np.float32)
                
                # Combine: Apply spin AFTER mouse delta? Or before?
                # R_delta_cam = R_spin @ R_delta_cam (Spin in Camera Frame)
                R_delta_cam = R_spin @ R_delta_cam
                self.pending_rot_z = 0

            
            # World rotation update
            # Note: If frames are permuted, we might need to adjust R_world logic foundation,
            # but usually R_cam handles the frame transform.
            R_world = R_cam @ R_delta_cam @ R_cam.T

            rot_delta = np.eye(4, dtype=np.float32)
            rot_delta[:3, :3] = R_world

            trans_delta = np.eye(4, dtype=np.float32)
            trans_delta[3, :3] = trans_vec

            # 3. Apply to Affine
            pivot_pos, pivot_neg = self.get_affine_pivot_matrices(model_extents)
            
            new_affine = trans_delta @ curr_affine @ (pivot_neg @ rot_delta @ pivot_pos)

            # 4. Write back
            await self.remote_write("motion", True)
            
            if not perspective:
                extents = await self.remote_read("view.extents")
                if extents:
                    # Adaptive zoom for Ortho too?
                    # Scale based on current extent size (extents[2] is usually width/height?)
                    # Let's use max extent dimension.
                    view_size = max([abs(e) for e in extents])
                    
                    # Zoom delta relative to view size
                    zoom_delta = tz * APP_CONFIG["sensitivity"]["zoom"] # Inverted and boosted
                    
                    scale = 1.0 + zoom_delta
                    new_extents = [c * scale for c in extents]
                    await self.remote_write("view.extents", new_extents)

            await self.remote_write("view.affine", new_affine.reshape(-1).tolist())
            
        except Exception as e:
            logging.error(f"Error in process_motion: {e}")

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
                # UInput handles press/release in combo? 
                # Our simple combo is press+release. For modifiers as "hold", we need different logic.
                # But current usage is single press actions mostly. User wanted Modifiers as keys?
                # If mapped to "Shift_L", press_combo("Shift_L") does press and release.
                # If the user wants to HOLD shift while moving mouse, that's complex.
                # Status Quo: Just press it once (likely toggles or useless).
                # Re-implementing as simple key press for now.
                if vkab:
                     vkab.press_combo(value)
                     logging.info(f"Button {bnum}: Modifier {value}")
                
            elif action == "logic" and is_press:
                if value == "lock_horizon":
                    self.horizon_locked = not self.horizon_locked
                    logging.info(f"Horizon Lock: {self.horizon_locked}")
                    
                elif value == "spin_90":
                     self.pending_rot_z -= 90
                     logging.info(f"Spin 90 Clockwise Triggered. Pending: {self.pending_rot_z}")
                     # Fix: Force a motion update to apply rotation immediately
                     # Create a dummy zero-motion event to trigger process_motion
                     dummy_motion = spnav.SpnavEventMotion(
                         type=spnav.SPNAV_EVENT_MOTION, 
                         x=0, y=0, z=0, rx=0, ry=0, rz=0, period=0, data=None
                     )
                     dummy_event = spnav.SpnavEvent(type=spnav.SPNAV_EVENT_MOTION, motion=dummy_motion)
                     await self.process_motion(dummy_event)


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
            await self.ws.send(json.dumps(event_msg))
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

async def process_request(connection, request):
    logging.info(f"Req: {request.path}")
    
    if request.path == "/config":
        # Serve the Config UI HTML
        try:
            with open("config_ui/index.html", "rb") as f:
                content = f.read()
            headers = Headers({"Content-Type": "text/html", "Access-Control-Allow-Origin": "*"})
            return Response(http.HTTPStatus.OK, "OK", headers, content)
        except Exception as e:
            logging.error(f"Failed to serve config UI: {e}")
            return Response(http.HTTPStatus.INTERNAL_SERVER_ERROR, "Error", Headers({}), b"500 Internal Error")

    if request.path.startswith("/3dconnexion/nlproxy") or request.path == "/":
         if "Upgrade" in request.headers and request.headers["Upgrade"].lower() == "websocket":
             return None
         # Identity
         response_body = json.dumps({"port": 8181, "version": "1.4.8.21486"}).encode("utf-8")
         headers = Headers({"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"})
         return Response(http.HTTPStatus.OK, "OK", headers, response_body)
    return None

async def handle_websocket(websocket):
    global APP_CONFIG
    logging.info(f"New connection: {websocket.remote_address}")
    
    # Create controller instance for this socket
    # Metadata will be populated later
    controller = Controller(websocket, {})
    connected_controllers[websocket] = controller

    try:
        # 1. Send WELCOME
        session_id = _rand_id()
        # [0, sessionID, 1, ident]
        await websocket.send(json.dumps([WAMP_WELCOME, session_id, 1, "AntigravityBridge"]))
        
        async for message in websocket:
            try:
                data = json.loads(message)
                if not isinstance(data, list): continue
                
                msg_type = data[0]
                
                if msg_type == WAMP_PREFIX:
                    pass # Ignore
                    
                elif msg_type == WAMP_CALL:
                    # [2, callID, procURI, args]
                    call_id = data[1]
                    proc = data[2]
                    args = data[3:]
                    
                    if "create" in proc:
                        if args and "3dmouse" in args[0]:
                             await websocket.send(json.dumps([WAMP_CALLRESULT, call_id, {"connexion": "mouse0"}]))
                        elif args and "3dcontroller" in args[0]:
                             # Extract metadata
                             meta = args[2] if len(args) > 2 else {}
                             controller.client_metadata = meta
                             logging.info(f"Client Metadata: {meta}")
                             await websocket.send(json.dumps([WAMP_CALLRESULT, call_id, {"instance": "controller0"}]))
                    
                    elif "update" in proc:
                        # [..., [uri, {focus: true}]]
                        # args might be nested list? WAMP args are list.
                        # so args = [uri, props]
                        await controller.handle_update(args)
                        await websocket.send(json.dumps([WAMP_CALLRESULT, call_id, None]))

                    elif "config.get" in proc:
                        # Return current APP_CONFIG
                        await websocket.send(json.dumps([WAMP_CALLRESULT, call_id, APP_CONFIG]))

                    elif "config.set" in proc:
                        # Update APP_CONFIG and save
                        try:
                            # Args[0] should be the new config dict
                            new_conf = args[0]
                            APP_CONFIG = new_conf
                            
                            with open(CONFIG_PATH, "w") as f:
                                json.dump(APP_CONFIG, f, indent=4)
                                
                            logging.info("Config updated via RPC")
                            await websocket.send(json.dumps([WAMP_CALLRESULT, call_id, "OK"]))
                        except Exception as e:
                            logging.error(f"Config update failed: {e}")
                            await websocket.send(json.dumps([WAMP_CALLERROR, call_id, str(e)]))
                        
                    else:
                        logging.warning(f"Unknown call: {proc}")
                        await websocket.send(json.dumps([WAMP_CALLRESULT, call_id, None]))

                elif msg_type == WAMP_SUBSCRIBE:
                    topic = data[1]
                    logging.info(f"Subscribed to: {topic}")
                    controller.subscribed_topic = topic
                    
                elif msg_type == WAMP_CALLRESULT:
                    # [3, callID, result]
                    call_id = data[1]
                    res = data[2]
                    controller.resolve_rpc(call_id, res)
                    
                elif msg_type == WAMP_CALLERROR:
                    # [4, callID, errorURI, desc]
                    call_id = data[1]
                    err = data[2]
                    controller.resolve_rpc(call_id, None, error=err)
                    
            except Exception as e:
                logging.error(f"Error handling msg: {e}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in connected_controllers:
            del connected_controllers[websocket]

# ---------------------------------------------------------
# Spacenav Handler (Thread)
# ---------------------------------------------------------

def spacenav_thread_func():
    logging.info("Opening spacenavd...")
    try:
        spnav.spnav_open()
    except spnav.SpnavError:
        logging.error("No spacenavd.")
        return

    while True:
        event = spnav.spnav_wait_event()
        if event:
            if event.type == SPNAV_EVENT_MOTION or event.type == SPNAV_EVENT_BUTTON:
                if event_queue_loop:
                     asyncio.run_coroutine_threadsafe(event_queue.put(event), event_queue_loop)
        else:
            # Prevent infinite CPU loop if spnavd disconnects or returns error
            time.sleep(0.5)

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


def ensure_ssl_certs(cert_file="cert.pem", key_file="key.pem"):
    """
    Checks for existence of SSL certs. If missing, generates a self-signed cert
    using OpenSSL to allow the WSS server to start securely.
    """
    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        logging.warning("SSL certificates not found. Generating self-signed certificate...")
        try:
            # Generate key and cert in one go (valid for 365 days)
            # openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
            cmd = [
                "openssl", "req", "-x509",
                "-newkey", "rsa:2048",
                "-keyout", key_file,
                "-out", cert_file,
                "-days", "365",
                "-nodes",
                "-subj", "/CN=localhost"
            ]
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info("Self-signed certificate generated successfully.")
        except Exception as e:
            logging.error(f"Failed to generate SSL certs: {e}")
            raise

async def main():
    global event_queue_loop
    event_queue_loop = asyncio.get_running_loop()
    
    init_environment()
    
    ensure_ssl_certs()

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")

    server = await websockets.serve(
        handle_websocket, "0.0.0.0", 8181, ssl=ssl_context,
        process_request=process_request, subprotocols=["wamp"]
    )
    logging.info("Bridge Running.")

    # Start broadcast consumer
    asyncio.create_task(broadcast_loop())
    
    # Initialize Virtual Keyboard
    global vkab
    vkab = VirtualKeyboard()
    
    # Start input producer thread
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, spacenav_thread_func)



    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
