import logging
import time
from evdev import UInput, ecodes as e

class VirtualKeyboard:
    def __init__(self):
        try:
            self.ui = UInput()
            logging.info("Virtual Keyboard Initialized (uinput)")
        except Exception as err:
            logging.error(f"Failed to initialize uinput: {err}. Ensure permissions on /dev/uinput.")
            self.ui = None


    def press_combo(self, key_str):
        """
        Presses a key combo defined by string, e.g. "ctrl+1", "f", "space".
        """
        if not self.ui:
            return

        if not key_str:
            return

        parts = key_str.lower().split('+')
        keys = []
        
        # Mapping logic
        for p in parts:
            if not p: continue
            if p == "ctrl" or p == "control":
                keys.append(e.KEY_LEFTCTRL)
            elif p == "alt":
                keys.append(e.KEY_LEFTALT)
            elif p == "shift":
                keys.append(e.KEY_LEFTSHIFT)
            elif p == "esc" or p == "escape":
                keys.append(e.KEY_ESC)
            elif p == "space":
                keys.append(e.KEY_SPACE)
            elif p == "f":
                keys.append(e.KEY_F)
            elif p.isdigit():
                # KEY_0, KEY_1, ...
                # getattr(e, f"KEY_{p}") usually works
                k = getattr(e, f"KEY_{p}", None)
                if k: keys.append(k)
            else:
                # Try generic lookup
                k = getattr(e, f"KEY_{p.upper()}", None)
                if k: 
                    keys.append(k)
                else:
                    logging.warning(f"Unknown key in mapping: {p}")

        # Execute
        try:
            # Hold modifiers
            for k in keys:
                self.ui.write(e.EV_KEY, k, 1)
            self.ui.syn()
            
            # Short delay for the OS to register the keystroke
            time.sleep(0.05)
            
            # Release all (LIFO/FIFO doesn't strictly matter for release but usually reverse)
            for k in reversed(keys):
                self.ui.write(e.EV_KEY, k, 0)
            self.ui.syn()
            
        except Exception as err:
            logging.error(f"Failed to press keys: {err}")

    def close(self):
        if self.ui:
            self.ui.close()
