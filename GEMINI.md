# 🌐 AsusRouter Home Assistant Integration - Developer Guide

This document provides developer guidelines, architecture references, testing procedures, and safety rules for developing and maintaining the `asusrouter` custom component for Home Assistant within this workspace.

---

## 🏛️ Architecture & Upstream Tracking

- **Upstream Repository:** [`Vaskivskyi/ha-asusrouter`](https://github.com/Vaskivskyi/ha-asusrouter)
- **Local Fork Remote:** `origin -> git@github.com:stevene1919/ha-asusrouter.git`
- **Upstream Tracking:** `upstream -> https://github.com/Vaskivskyi/ha-asusrouter.git`
- **Local Fork Branch:** `feature/wan-switch` (branched from upstream `main`, v0.40.1)
- **API & Firmware Architecture Docs:** [`docs/api_architecture.md`](docs/api_architecture.md)
- **Dependencies:** `asusrouter>=1.21.0` (installed in `.venv`)
- **Virtual Environment:** `homeassistant/custom_components/asusrouter/.venv` (managed with `uv`)

### 📡 Target Device Reference
- **Device Codename:** `asus`
- **Model:** ASUS DSL-AX82U AX5400 Dual Band WiFi 6 VDSL/ADSL Modem Router
- **Firmware:** Asuswrt-Merlin-Gnuton `388.10_2`
- **IP Address:** `192.168.1.1`
- **Uplink:** Aussie Broadband NBN FTTN (VDSL2 PPPoE)
- **HA Device Name:** `Front Room DSL-AX82U`

---

## 🔌 Internet Switch (`ARInternetSwitch`)

The Internet Switch exposes an on/off entity in Home Assistant to cleanly disconnect and reconnect the router's WAN uplink.

### Entity Details
- **Entity ID:** `switch.<router_name>_internet` (e.g. `switch.front_room_dsl_ax82u_internet`)
- **Device Class:** `SwitchDeviceClass.SWITCH`
- **Entity Category:** `EntityCategory.CONFIG`
- **Default State Source:** Coordinator keys `internet_link` with fallback to `0_state`

### Command Architecture & CGI Protocol
When toggling the switch:

1. **Model Detection & DSL Handling:**
   - Detects whether the target device is a DSL router (e.g. `DSL-AX82U`) via `router.bridge.model` or `router._conf_name`.
   - **DSL Routers:**
     - Connect: `rc_service: "start_dslwan_if 0"`, `dslx_link_enable: "1"`, `wan_enable: "1"`, `wan0_enable: "1"`, `freeze_duck: "0"`
     - Disconnect: `rc_service: "stop_dslwan_if 0"`, `dslx_link_enable: "0"`, `wan_enable: "0"`, `wan0_enable: "0"`, `freeze_duck: "0"`
   - **Standard Ethernet Routers:**
     - Connect: `rc_service: "start_wan"`, `wan_enable: "1"`, `wan0_enable: "1"`, `freeze_duck: "0"`
     - Disconnect: `rc_service: "stop_wan"`, `wan_enable: "0"`, `wan0_enable: "0"`, `freeze_duck: "0"`
2. **NVRAM Synchronization:**
   - Synchronizes `dslx_link_enable`, `wan0_enable`, and `wan_enable` simultaneously. This prevents the Asus Web UI's Network Map (`internet.asp`, which reads `wan0_enable`) from displaying an inconsistent toggle state.
3. **Why Not `device-map/wan_action.asp`:**
   - The Asus diagnostic endpoint `/device-map/wan_action.asp?wanaction=Disconnect` sets `freeze_duck=1`, freezing the `wanduck` watchdog daemon.
   - When `freeze_duck=1`, the router's Web UI enters a locked state and refuses to reconnect from the browser, requiring an SSH shell command (`service start_wan`) to recover.
   - By calling `applyapp.cgi` with `freeze_duck="0"`, `wanduck` remains active, NVRAM `wan_enable` is updated cleanly, and the Web UI continues to function normally.
4. **Fallback Method:**
   - If `async_api_command` raises an exception, the switch falls back to `api.async_run_service` passing the appropriate `service` and NVRAM argument dictionary.
5. **Optimistic State Management:**
   - AussieBB VDSL PPPoE sessions require 2–5 seconds to tear down or re-negotiate.
   - Immediate coordinator refreshes were removed to prevent state bouncing.
   - `_handle_coordinator_update` maintains `_attr_is_on` until the coordinator's reported native telemetry matches the target state.

---

## 🛡️ Mandatory Safety Rules (CRITICAL)

> [!CAUTION]
> **STRICT PROHIBITION ON UNAPPROVED WAN TOGGLES:**
> Disconnecting the WAN connection on `asus` drops internet access for the entire household and **immediately severs remote LLM agent connectivity**.
> - **NEVER** call `async_turn_off`, invoke the `switch.turn_off` service, or toggle the Internet switch in live environments without Steven's explicit real-time approval.
> - **Emergency Recovery:** If WAN disconnects unexpectedly and the router does not auto-reconnect, SSH from `gw` (`192.168.50.1`):
>   ```bash
>   ssh admin@192.168.1.1 "service start_wan"
>   ```

---

## 🛠️ Testing & Deployment Workflow

### 1. Code Quality & Unit Tests
Run within `homeassistant/custom_components/asusrouter`:
```bash
# Linting
.venv/bin/ruff check custom_components/asusrouter/switch.py tests/test_internet_switch.py

# Run unit tests
.venv/bin/pytest tests/test_internet_switch.py
```

### 2. Sync to Vodka
```bash
rsync -avz --exclude='tests' --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' \
  /home/steven/projects/homelab/homeassistant/custom_components/asusrouter/custom_components/asusrouter/ \
  steven@192.168.50.200:/opt/usb/homeassistant/custom_components/asusrouter/
```

### 3. Syntax Verification & Restart
1. Run syntax check: `ha_config_check()` via `homelab` MCP.
2. Obtain Steven's confirmation before restarting Home Assistant.
3. Restart container via `docker_restart(host="vodka", container="homeassistant")`.
4. Set a 60-second cooldown timer (`schedule(DurationSeconds=60, ...)`).
5. Verify post-restart logs:
   ```python
   docker_logs(host="vodka", container="homeassistant", grep="asusrouter", tail=100)
   ```
