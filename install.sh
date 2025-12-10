#!/bin/bash

# Definition of paths
APP_DIR=$(pwd)
ICON_SRC="$APP_DIR/assets/icon.png"
ICON_DEST="$HOME/.local/share/icons/hicolor/512x512/apps/spacemouse-xdesign.png"
DESKTOP_FILE="$HOME/.local/share/applications/spacemouse-xdesign.desktop"

# Ensure icon directory exists
mkdir -p "$HOME/.local/share/icons/hicolor/512x512/apps/"

# Install Icon
echo "Installing icon to $ICON_DEST..."
cp "$ICON_SRC" "$ICON_DEST"

# Create Desktop File
echo "Generating $DESKTOP_FILE..."
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
Exec=systemctl --user start spacemouse-bridge.service

[Desktop Action RestartService]
Name=Restart Service
Exec=systemctl --user restart spacemouse-bridge.service

[Desktop Action StopService]
Name=Stop Service
Exec=systemctl --user stop spacemouse-bridge.service
EOF

# Refresh DB
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null

echo "Done! You can now find 'SpaceMouse xDesign' in your app grid."
