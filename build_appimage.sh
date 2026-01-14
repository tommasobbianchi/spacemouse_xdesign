#!/bin/bash
set -e

APP_NAME="SpaceMouseBridge"
APP_DIR_NAME="AppDir"
DIST_DIR="dist"
BUILD_TOOL="appimagetool-x86_64.AppImage"
BUILD_TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

echo "=== Building AppImage for $APP_NAME ==="

# 1. Check Binaries
if [ ! -f "$DIST_DIR/SpaceMouseBridge" ] || [ ! -f "$DIST_DIR/SpaceMouseTray" ]; then
    echo "Error: Binaries not found in $DIST_DIR/. Run PyInstaller build first."
    exit 1
fi

# 2. Prepare AppDir
echo "Creating AppDir structure..."
rm -rf "$APP_DIR_NAME"
mkdir -p "$APP_DIR_NAME/usr/bin"
mkdir -p "$APP_DIR_NAME/usr/share/icons/hicolor/512x512/apps"

# Copy Binaries
cp "$DIST_DIR/SpaceMouseBridge" "$APP_DIR_NAME/usr/bin/"
cp "$DIST_DIR/SpaceMouseTray" "$APP_DIR_NAME/usr/bin/"

# Copy Icon
ICON_SRC="assets/icon.png"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APP_DIR_NAME/spacemouse.png"
    cp "$ICON_SRC" "$APP_DIR_NAME/.DirIcon"
    cp "$ICON_SRC" "$APP_DIR_NAME/usr/share/icons/hicolor/512x512/apps/spacemouse.png"
else
    echo "Warning: Icon not found at $ICON_SRC"
    touch "$APP_DIR_NAME/spacemouse.png" # Placeholder
fi

# Create Desktop File
cat > "$APP_DIR_NAME/spacemouse.desktop" <<EOF
[Desktop Entry]
Name=SpaceMouse xDesign
Exec=AppRun
Icon=spacemouse
Type=Application
Categories=Utility;
Comment=Bridge for 3Dconnexion SpaceMouse in xDesign
EOF

# Create AppRun
cat > "$APP_DIR_NAME/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
export PATH="\$HERE/usr/bin:\$PATH"

# Start Bridge in background
echo "Starting SpaceMouse Bridge..."
SpaceMouseBridge &
BRIDGE_PID=\$!

# Start Tray in foreground
echo "Starting SpaceMouse Tray..."
SpaceMouseTray

# Cleanup
echo "Stopping Bridge (PID \$BRIDGE_PID)..."
kill \$BRIDGE_PID 2>/dev/null || true
EOF

chmod +x "$APP_DIR_NAME/AppRun"
chmod +x "$APP_DIR_NAME/usr/bin/"*

# 3. Get AppImageTool
if [ ! -f "$BUILD_TOOL" ]; then
    echo "Downloading appimagetool..."
    wget -q "$BUILD_TOOL_URL" -O "$BUILD_TOOL"
    chmod +x "$BUILD_TOOL"
fi

# 4. Build
echo "Generating AppImage..."
# Use ARCH=x86_64 explicitly
export ARCH=x86_64
./"$BUILD_TOOL" "$APP_DIR_NAME" "SpaceMouse_xDesign-x86_64.AppImage"

echo "=== Done! ==="
echo "Output: SpaceMouse_xDesign-x86_64.AppImage"
