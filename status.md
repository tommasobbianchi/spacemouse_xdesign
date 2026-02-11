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
- **Deployment**: Verified on Spoke (`tommaso-behemoth-1`).

## Known Installation Friction (Spoke Deployment)
During the deployment on `tommaso-behemoth-1`, several critical friction points were identified for "Casual Users":
1. **Config File**: `install.sh` does not assume a default config, leaving the user with no buttons until manual copy.
2. **Permissions**: `uinput` requires `udev` rules and a **Reboot/Logout**, which is not handled by the script.
3. **SSL Trust**: Browsers do not trust `localhost` (and especially `127.x.x.x` IPs used by xDesign) by default, requiring manual "Accept Risk" steps.
4. **Dependencies**: `libspnav` and `python3-gi` (AppIndicator) must be installed via `apt`, which is not automated for all distros.

## Next Steps
- Enjoy using the SpaceMouse!
- (Optional) Refine "Lock Horizon" logic if needed in the future.
- (Optional) Add more RPC calls if discovered.

## Migration Audit (2026-02-11)

**Location**: `/home/tommaso/projects/spacemouse_xdesign` on nativedev (100.112.35.102)
**Git**: main, clean, **no remote**, 3 commits
**Size**: 470M (339M .flatpak-builder cache, 56M build-dir, 47M .git, 28M videos)

### Related Projects
- `spacemouse-onshape` — Same hardware (SpaceMouse), different target CAD (Onshape vs xDesign)
- `svg_texture` — Also targets Onshape/CAD workflows

### Issues Found
- **No git remote** — no backup
- **.flatpak-builder/ cache is 339M** — build cache, should be gitignored/deleted
- **build-dir/ is 56M** — build output, should be gitignored
- **2 video files (28M)** — demo recordings in root, consider moving to docs/

### Recommendations
1. Create GitHub remote for backup
2. Delete .flatpak-builder/ cache (339M saved) — regenerable
3. Add build-dir/ and .flatpak-builder/ to .gitignore
4. Consider consolidating with spacemouse-onshape if shared components exist
