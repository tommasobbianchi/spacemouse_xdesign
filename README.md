# SpaceMouse Bridge for xDesign (Linux)

![SpaceMouse xDesign](https://img.shields.io/badge/Platform-Linux-blue) ![Status](https://img.shields.io/badge/Status-Stable-green)

This project enables **3Dconnexion SpaceMouse** support for **Dassault Systèmes xDesign** (3DEXPERIENCE Platform) on Linux systems. It acts as a bridge, emulating the official Windows driver protocol via a local secure WebSocket server.

## 🚀 Purpose
Dassault Systèmes xDesign relies on a local WebSocket service to communicate with 3D hardware. While official drivers exist for Windows, Linux support is often limited or requires complex workarounds. This bridge:
1. Detects your SpaceMouse (via `libspnav`).
2. Translates motion events into the standard 3Dconnexion JSON protocol.
3. Serves these events securely to the xDesign web application aka "3DEXPERIENCE Platform".

## 📦 Installation

### Option 1: Portable AppImage (Recommended)
The easiest way to run the bridge without installing dependencies.

1. **Download** the latest `SpaceMouse_xDesign-x86_64.AppImage` from the [Releases page](../../releases).
2. **Make Executable**:
   ```bash
   chmod +x SpaceMouse_xDesign-x86_64.AppImage
   ```
3. **Setup Certificates (One-time)**:
   This is critical. xDesign requires a secure connection (`wss://`). Run the included setup script to install a trusted local certificate:
   ```bash
   # Download the script if you don't have it
   wget https://raw.githubusercontent.com/tommasobbianchi/spacemouse_xdesign/main/setup_ssl.sh
   chmod +x setup_ssl.sh
   sudo ./setup_ssl.sh
   ```
   *Follow the prompts (leave password blank if asked for NSS DB).*

4. **Run**:
   ```bash
   ./SpaceMouse_xDesign-x86_64.AppImage
   ```
   An icon will appear in your system tray.

### Option 2: Run from Source (Advanced)
If you prefer to run it as a system service or modify the code.

1. **Clone the repo**:
   ```bash
   git clone https://github.com/tommasobbianchi/spacemouse_xdesign.git
   cd spacemouse_xdesign
   ```
2. **Install**:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
   This will set up a virtual environment, compile dependencies, and register a systemd user service.
3. **Setup SSL**:
   ```bash
   sudo ./setup_ssl.sh
   ```

## 🎮 Usage

1. **Start the Bridge**:
   - If using **AppImage**: simply run it.
   - If installed as **Service**: It starts automatically on login. Verification:
     ```bash
     systemctl --user status spacemouse-bridge
     ```

2. **Open xDesign**:
   - Log in to your generic 3DEXPERIENCE dashboard.
   - Open xDesign (or xShape).
   - The application should automatically detect the "3Dconnexion" device.

3. **Configuration**:
   - Click the **Tray Icon** -> **Configure**.
   - Or open your browser to: `https://localhost:8181/config`
   - You can invert axes, adjust sensitivity, and map buttons.

## 🔧 Troubleshooting

- **"No Device Detected" in xDesign**:
  - Ensure the bridge is running (Tray icon visible?).
  - Ensure you ran `setup_ssl.sh` and accepted the certificates.
  - Try opening `https://localhost:8181/config`. If you see a privacy warning, the certificate is not fully trusted.

- **"Address already in use"**:
  - Check if another driver (e.g., official non-functioning driver or another instance) is using port `8181`.

## 🏗️ Building
To build the AppImage yourself:
```bash
./install.sh # Setup venv
./build_appimage.sh
```

---
*Disclaimer: This project is not affiliated with 3Dconnexion or Dassault Systèmes.*
