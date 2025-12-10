# Packaging Guide (Flatpak)

This directory contains the manifest for building the SpaceMouse Bridge as a Flatpak.

## Prerequisites
1.  **Flatpak Builder**: `sudo apt install flatpak-builder` (or equivalent).
2.  **Flatpak Pip Generator**:
    ```bash
    wget https://raw.githubusercontent.com/flatpak/flatpak-builder-tools/master/pip/flatpak-pip-generator
    chmod +x flatpak-pip-generator
    ```

## Step 1: Generate Python Dependencies
Because Flatpak builds are sandboxed without network access, we must pre-resolve all Python dependencies (`websockets`, `numpy`, `evdev`).

Run this command from the `spacemouse_bridge` root:
```bash
./flatpak/flatpak-pip-generator --output flatpak/python3-requirements.json --requirements requirements.txt
```
*Note: This will overwrite the placeholder `python3-requirements.json` with the actual download URLs.*

## Step 2: Build the Flatpak
```bash
flatpak-builder --user --install --force-clean build-dir flatpak/io.github.tommaso.spacemouse_xdesign.yml
```

## Step 3: Run
```bash
flatpak run io.github.tommaso.spacemouse_xdesign
```
*Note: Ensure `uinput` permissions are granted on your host system (usually adding user to `input` group).*
