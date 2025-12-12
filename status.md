# Project Status

## Current Focus
**Distribution & Maintenance**.
The SpaceMouse Bridge is fully functional and has been **submitted to Flathub** (PR #7293).

## Completed Tasks
- **Spin 90 Fix**: Implemented immediate rotation logic (dummy motion event) to eliminate lag.
- **Service Hardening**: Added `RestartSec=2` and connection retry loop for better stability.
- **View Shortcuts**: Fixed by switching to **uinput/evdev** virtual keyboard driver (bypasses Wayland security) with 50ms input delay (fixes registration issues).
- **Menu Button**: Mapped to **"g"** key (correct xDesign shortcut) on Button 4.
- **Configuration**: Added `config.json` for sensitivity and button mapping.
- **Service Installation**: Installed `spacemouse-bridge.service` and resolved conflict with `spacenav-ws`.
- **Connectivity**: Resolved SSL certificate issues.

## Packaging & Distribution
- **Flatpak**: Full manifest `io.github.tommaso.spacemouse_xdesign.yml` created.
- **Dependencies**: Bundled `libspnav` (C) and Python env (numpy, etc) fully sandboxed.
- **Submission**: PR opened on Flathub [#7293](https://github.com/flathub/flathub/pull/7293).

## Status Details
- **Architecture**: Stable.
- **Motion**: Fluid. Sensitivity tunable via config.
- **Buttons**: Fully configurable.
- **System**: Auto-starts on login.

## Next Steps
- Enjoy using the SpaceMouse!
- (Optional) Refine "Lock Horizon" logic if needed in the future.
- (Optional) Add more RPC calls if discovered.
