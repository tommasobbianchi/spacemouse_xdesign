# SpaceMouse Bridge for xDesign

A professional, standalone bridge connecting 3DConnexion SpaceMouse devices to SolidWorks xDesign (and other web-based CAD) on Linux.

## Features
-   **Native Device Support**: Integrates with `spacenavd` for smooth 6DoF control.
-   **Virtual Keyboard**: Maps buttons to complex key macros (Ctrl+Z, Ctrl+Shift+S, etc.).
-   **Web Configuration UI**: Modern, dark-mode Interface for customizing sensitivity and button mapping in real-time.
-   **User Service Architecture**: Runs as a localized systemd user service, seamlessly integrating with your Wayland/X11 session and browser.
-   **Secure**: Auto-configures TLS/SSL for secure local coordination.

## Installation

### Prerequisites
-   `spacenavd` (installed and running)
-   `python3`
-   `firefox` (for Config UI)

### Quick Start (User Service)
1.  **Clone the repository**:
    ```bash
    git clone https://github.com/tommaso/spacemouse_xdesign.git
    cd spacemouse_xdesign/spacemouse_bridge
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Install the User Service**:
    ```bash
    cp spacemouse-bridge-user.service ~/.config/systemd/user/spacemouse-bridge.service
    systemctl --user daemon-reload
    systemctl --user enable --now spacemouse-bridge.service
    ```

4.  **Usage**:
    -   Press the **Menu** button on your SpaceMouse to open the Configuration UI.
    -   Access manually at `https://localhost:8181/config`.

## Architecture
The bridge operates as a WebSocket (WAMP) server that translates raw `spacenav` events into application-specific RPC calls. It uses `uinput` for keyboard simulation and infers the active desktop environment to launch GUI tools correctly.
