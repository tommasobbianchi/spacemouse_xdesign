import ctypes
from ctypes import Structure, Union, c_int, c_uint, c_void_p, c_char_p, c_float

# Load libspnav
try:
    libspnav = ctypes.CDLL("libspnav.so")
except OSError:
    try:
        libspnav = ctypes.CDLL("libspnav.so.0")
    except OSError:
        raise OSError("Could not find libspnav.so. Please ensure spacenavd and libspnav are installed.")

# Constants
SPNAV_EVENT_ANY = 0
SPNAV_EVENT_MOTION = 1
SPNAV_EVENT_BUTTON = 2

# Structures
class SpnavEventMotion(Structure):
    _fields_ = [
        ("type", c_int),
        ("x", c_int),
        ("y", c_int),
        ("z", c_int),
        ("rx", c_int),
        ("ry", c_int),
        ("rz", c_int),
        ("period", c_uint),
        ("data", c_void_p), # pointer to X11 event if applicable, usually NULL
    ]

class SpnavEventButton(Structure):
    _fields_ = [
        ("type", c_int),
        ("press", c_int),
        ("bnum", c_int),
    ]

class SpnavEvent(Union):
    _fields_ = [
        ("type", c_int),
        ("motion", SpnavEventMotion),
        ("button", SpnavEventButton),
        # Pad to ensure size is enough for largest event (usually motion)
        ("pad", c_char_p * 20), 
    ]

# Function Prototypes
libspnav.spnav_open.argtypes = []
libspnav.spnav_open.restype = c_int

libspnav.spnav_close.argtypes = []
libspnav.spnav_close.restype = c_int

libspnav.spnav_fd.argtypes = []
libspnav.spnav_fd.restype = c_int

libspnav.spnav_poll_event.argtypes = [ctypes.POINTER(SpnavEvent)]
libspnav.spnav_poll_event.restype = c_int

libspnav.spnav_wait_event.argtypes = [ctypes.POINTER(SpnavEvent)]
libspnav.spnav_wait_event.restype = c_int

# Pythonic API
class SpnavError(Exception):
    pass

def spnav_open():
    if libspnav.spnav_open() == -1:
        raise SpnavError("Failed to connect to spacenavd daemon")

def spnav_close():
    libspnav.spnav_close()

def spnav_poll_event():
    event = SpnavEvent()
    if libspnav.spnav_poll_event(ctypes.byref(event)):
        return event
    return None

def spnav_wait_event():
    event = SpnavEvent()
    if libspnav.spnav_wait_event(ctypes.byref(event)):
        return event
    return None

def spnav_fd():
    return libspnav.spnav_fd()
