#!/bin/bash
set -e  # Exit on error

# --- Configuration ---
APP_NAME="SpaceMouse Bridge for xDesign"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$APP_DIR/venv"
ICON_SRC="$APP_DIR/assets/icon.png"
ICON_DEST="$HOME/.local/share/icons/hicolor/512x512/apps/spacemouse-xdesign.png"
DESKTOP_FILE="$HOME/.local/share/applications/spacemouse-xdesign.desktop"
TRAY_DESKTOP_FILE="$HOME/.config/autostart/spacemouse-tray.desktop"
SERVICE_NAME="spacemouse-bridge.service"
SERVICE_DEST="$HOME/.config/systemd/user/$SERVICE_NAME"

echo "=== Installing $APP_NAME ==="
echo "Detected App Directory: $APP_DIR"

# --- 1. Python Environment ---
echo "--- Setting up Python Environment ---"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Ensure pip is up to date and install requirements
"$VENV_DIR/bin/pip" install --upgrade pip
echo "Installing dependencies from requirements.txt..."
"$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"


# --- 2. Systemd Service ---
echo "--- Configuring Systemd Service ---"
mkdir -p "$HOME/.config/systemd/user"

# Generate Service File Dynamically
cat > "$APP_DIR/$SERVICE_NAME" << EOF
[Unit]
Description=$APP_NAME (User Service)
After=gnome-session.target network.target

[Service]
Type=simple
# Connect to the specific venv python interpreter
ExecStart=$VENV_DIR/bin/python3 $APP_DIR/main.py
WorkingDirectory=$APP_DIR
Restart=always
RestartSec=2
# Ensure GUI access for pystray (Tray Icon) if run as service, although tray usually runs separately
Environment=PYTHONUNBUFFERED=1
Environment=DISPLAY=$DISPLAY
Environment=XAUTHORITY=$XAUTHORITY

[Install]
WantedBy=default.target
EOF

echo "Generated service file at $APP_DIR/$SERVICE_NAME"

# Link/Copy to systemd user directory
ln -sf "$APP_DIR/$SERVICE_NAME" "$SERVICE_DEST"

# Reload and Restart
echo "Reloading systemd daemon..."
systemctl --user daemon-reload
echo "Enabling and restarting service..."
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

# Check status briefly
if systemctl --user is-active --quiet "$SERVICE_NAME"; then
    echo "Service is ACTIVE and RUNNING."
else
    echo "WARNING: Service failed to start. Check 'journalctl --user -u $SERVICE_NAME'"
fi


# --- 3. Desktop Integration ---
echo "--- Configuring Desktop Integration ---"

# Install Icon
mkdir -p "$(dirname "$ICON_DEST")"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DEST"
    echo "Icon installed."
else
    echo "WARNING: Icon not found at $ICON_SRC"
fi

# Generate Desktop File for the Config UI / Launcher
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SpaceMouse xDesign
Comment=Configure your SpaceMouse for Web 3D Apps
Exec=xdg-open https://localhost:8181/config
Icon=spacemouse-xdesign
Terminal=false
Categories=Utility;Settings;
Actions=StartService;RestartService;StopService;

[Desktop Action StartService]
Name=Start Service
Exec=systemctl --user start $SERVICE_NAME

[Desktop Action RestartService]
Name=Restart Service
Exec=systemctl --user restart $SERVICE_NAME

[Desktop Action StopService]
Name=Stop Service
Exec=systemctl --user stop $SERVICE_NAME
EOF
echo "Desktop launcher created."

# Tray Autostart (Optional - if the main service doesn't handle tray)
# Note: In our current architecture, tray.py is separate or part of main? 
# If tray.py is separate, we need to autostart it. 
# Assuming tray.py is the tray indicator.

echo "Setting up Tray Indicator Autostart..."
mkdir -p "$(dirname "$TRAY_DESKTOP_FILE")"

cat > "$TRAY_DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=SpaceMouse Tray
Exec=$VENV_DIR/bin/python3 $APP_DIR/tray.py
Icon=spacemouse-xdesign
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

# Make executable just in case
chmod +x "$TRAY_DESKTOP_FILE"
echo "Tray autostart configured."

# --- Finalize ---
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null

echo "=== Installation Complete! ==="
echo "1. Service is running."
echo "2. You can launch the Config UI from your applications menu ('SpaceMouse xDesign')."
echo "3. Tray indicator will start on next login (or you can run './venv/bin/python3 tray.py' now)."
