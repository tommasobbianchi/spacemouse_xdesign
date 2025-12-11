# SpaceMouse Bridge for xDesign - User Guide

This guide explains how to install, configure, and use the SpaceMouse Bridge to enable 6DOF navigation in Dassault Systèmes 3DEXPERIENCE xDesign (and other web apps) on Linux.

---

## 🔒 Prerequisites

1.  **Hardware**: 3DConnexion SpaceMouse (any model).
2.  **Driver**: `spacenavd` must be installed and running.
    ```bash
    # Arch Linux (Manjaro)
    sudo pacman -S libspnav
    # Install spacenavd from AUR or ensure it is running
    sudo systemctl enable --now spacenavd
    ```
3.  **Permissions**: Your user must have access to `uinput` for keyboard shortcuts.
    ```bash
    sudo usermod -aG input $USER
    # Log out and back in for this to take effect!
    ```

---

## 📦 Installation

You can install the bridge as a standard user service (Recommended) or build it as a Flatpak.

### Method A: Standard Installation (Recommended)
This runs the bridge in a local Python virtual environment managed by systemd.

1.  **Navigate to the bridge directory**:
    ```bash
    cd spacemouse_bridge
    ```
2.  **Run the automated installer**:
    ```bash
    ./install.sh
    ```
    This script will:
    - Create a Python venv.
    - Install dependencies.
    - Create and start the user service (`spacemouse-bridge.service`).
    - Create a desktop launcher ("SpaceMouse xDesign").

### Method B: Flatpak Installation (Advanced)
Since this app is not yet on Flathub, you must build it locally. This runs the app in a sandbox.

1.  **Install Builder Tools**:
    ```bash
    sudo pacman -S flatpak flatpak-builder git base-devel
    ```

2.  **Get the Pip Generator** (Required to freeze Python dependencies):
    ```bash
    wget https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator
    chmod +x flatpak-pip-generator
    ```

3.  **Generate Dependencies**:
    Run this from the `spacemouse_bridge` directory:
    ```bash
    ./flatpak/flatpak-pip-generator --output flatpak/python3-requirements.json --requirements requirements.txt
    ```

4.  **Build and Install**:
    ```bash
    flatpak-builder --user --install --force-clean build-dir flatpak/io.github.tommaso.spacemouse_xdesign.yml
    ```

5.  **Run**:
    ```bash
    flatpak run io.github.tommaso.spacemouse_xdesign
    ```

---

## 🚀 Usage

### Starting the Service
- **Standard**: The service starts automatically on login.
    - Restart: `systemctl --user restart spacemouse-bridge`
    - Status: `systemctl --user status spacemouse-bridge`
- **Flatpak**: Run the command manually or create a custom shortcut.

### Configuration UI
1.  Open your browser and go to: **[https://localhost:8181/config](https://localhost:8181/config)**
2.  **Security Warning**: You will see a "Potential Security Risk" warning because the bridge uses a self-signed certificate (required for secure WebSockets).
    - **Firefox**: Click *Advanced* -> *Accept the Risk and Continue*.
    - **Chrome**: Click *Advanced* -> *Proceed to localhost (unsafe)*.
3.  **Features**:
    - Adjust Sensitivity (Pan/Zoom/Rotate).
    - Map Buttons (e.g., "Spin 90", "Lock Horizon").

### Using in xDesign (or Onshape/others)
1.  Open xDesign in your browser.
2.  The bridge emulates the 3DConnexion WebSocket protocol.
3.  **Spin 90**: Press the mapped button to rotate the view 90 degrees instantly.
4.  **Lock Horizon**: Toggles horizon locking (prevents rolling the view).

---

## 🛠️ Troubleshooting

- **"Service failed to start"**:
    Check logs: `journalctl --user -u spacemouse-bridge -n 50`
- **"Device not found"**:
    Ensure `spacenavd` is running: `systemctl status spacenavd`
- **"Connection Refused" in Browser**:
    Make sure you visited `https://localhost:8181` and accepted the certificate.
