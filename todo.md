# To Do List

## Packaging & Distribution
- [x] Create Flatpak Manifest
- [x] Configure Build Permissions (`--device=all`, `--share=network`)
- [x] Generate AppStream Metadata (`metainfo.xml`, `.desktop`)
- [x] Submit to Flathub (PR #7293)
- [ ] Address Flathub Reviewer Feedback
- [ ] **Snap Package**: Create `snapcraft.yaml` (Critical for Ubuntu support).
    - [ ] Handle `uinput` interface plug.
    - [ ] Handle `spacenavd` socket access.

## Installation Simplification (Casual Use)
- [ ] **Fix `install.sh`**:
    - [ ] Auto-copy `config.json` from repo to `~/.config/spacemouse-bridge/`.
    - [ ] Check/Install `udev` rules for `uinput` automatically (ask for sudo).
    - [ ] Check/Install system dependencies (`apt install ...`) or warn explicitly.
- [ ] **SSL Automation**: Investigate `mkcert` or similar to install a local CA so browsers trust it automatically?
- [ ] **Packaging Research**: Evaluate AppImage vs Flatpak for "Single File" delivery.

## High Priority (Fixes)
- [x] Fix View Shortcuts
    - [x] Identify non-conflicting Hotkeys (Solved via `config.json`)
    - [x] Implement Configurable Button Mappings
- [x] Fix Spin 90 Button
    - [x] Debug `pending_rot_z` application
    - [x] Force immediate motion update

## Infrastructure
- [x] Configuration File (`config.json`)
- [x] Service Install (`spacemouse-bridge.service`)
- [x] Conflict Resolution (`spacenav-ws`)

## Improvements / Backlog
### Refine "Lock Horizon"
- [ ] Current: Hard zeroes tz, rx, ry, rz.
- [ ] Future: Ensure it snaps to nearest axis or resets roll?

### Advanced Features
- [ ] Research Direct RPC calls for Views (if hotkeys prove unreliable).
