# Asuswrt Web API & Firmware Architecture Reference

This document provides a comprehensive technical reference for the **Asuswrt Web API**, internal CGI endpoints, service dispatch routines (`rc`), and the DSL subsystem in **Asuswrt-Merlin** and **Gnuton's Asuswrt-Merlin** firmware.

---

## 🏛️ 1. Architecture Overview

```
+-------------------------------------------------------------+
|                      Client Layer                           |
|  - Asus Router Mobile App (Android / iOS)                   |
|  - Asuswrt Web UI (Browser SPA / iframes)                   |
|  - Home Assistant (`ha-asusrouter` / `asusrouter` py library)|
+------------------------------+------------------------------+
                               | HTTP / HTTPS (Port 80 / 8443)
+------------------------------v------------------------------+
|                   HTTP Daemon (`httpd`)                     |
|  • Session & Token Auth: `login.cgi`, `asus_token` cookie    |
|  • Query Dispatcher:    `appGet.cgi` (`hook=...`)           |
|  • Command Dispatcher:  `applyapp.cgi`, `start_apply2.htm`  |
+------------------------------+------------------------------+
                               | IPC / notify_rc
+------------------------------v------------------------------+
|            Resource Control Daemon (`/sbin/rc`)             |
|  • `wanduck` (WAN Watchdog & link state detector)           |
|  • `start_dslwan_if` / `stop_dslwan_if` (DSL WAN drivers)    |
|  • `restart_wan_if` / `stop_wan_if` (Ethernet WAN)          |
|  • `restart_wireless`, `restart_firewall`, `restart_vpn`    |
+------------------------------+------------------------------+
                               |
+------------------------------v------------------------------+
|            Linux Kernel & NVRAM / Broadcom Drivers          |
|  • NVRAM partition (shared key-value store)                 |
|  • Hardware PHY drivers & modulation daemons                |
+-------------------------------------------------------------+
```

### Firmware Flavors
1. **Stock Asuswrt**: Official ASUS firmware. Features internal CGI endpoints and web management interface.
2. **Asuswrt-Merlin**: Enhanced open-source continuation by Eric Sauvageau (RMerl) focusing on stability, custom user scripts (`/jffs/scripts/`), and enhanced tools for Ethernet RT-series models.
3. **Asuswrt-Merlin-Gnuton (`gnuton/asuswrt-merlin.ng`)**: Extended fork maintained by Gnuton specifically supporting DSL models (such as `DSL-AX82U` and `DSL-AC68U`) with proprietary DSL driver blobs alongside Merlin features.

---

## 🔑 2. Authentication & Session Flow

The embedded web server (`/usr/sbin/httpd`) handles user authentication via `login.cgi`:

```http
POST /login.cgi HTTP/1.1
Host: 192.168.1.1
Content-Type: application/x-www-form-urlencoded

group_id=&action_mode=&action_script=&action_wait=5&current_page=Main_Login.asp&next_page=index.asp&flag=&login_authorization=<BASE64_CREDENTIALS>
```

- **Session Token**: On successful login, the server sets an `asus_token` HTTP cookie.
- **Header Convention**: Automated API clients pass the session cookie and a mobile app User-Agent header (e.g. `asusrouter-Android-DUTUtil-1.0.0.201`) to interact with JSON endpoints.

---

## 📡 3. Query Dispatcher (`appGet.cgi`)

`appGet.cgi` dynamically queries system telemetry and NVRAM variables by evaluating C functions defined in `httpd`:

### Common Hook Calls
- `hook=nvram_get(KEY1);nvram_get(KEY2)`: Returns JSON dictionary of requested NVRAM variables.
- `hook=get_cfg_clientlist()`: Returns full active client inventory with IP, MAC, hostname, band, and RSSI.
- `hook=cpu_usage(appobj);memory_usage(appobj)`: Returns per-core CPU percentages and RAM utilization.
- `hook=netdev(appobj)`: Returns interface RX/TX byte and packet counters.
- `hook=get_wan_unit()`: Returns active primary WAN unit index.

---

## ⚙️ 4. Action & Command Dispatcher (`applyapp.cgi`)

`applyapp.cgi` executes configuration changes, updates NVRAM, and notifies the resource control daemon (`/sbin/rc`) without rendering HTML pages:

### Payload Structure
```json
{
  "action_mode": "apply",
  "rc_service": "<service_name>",
  "action_script": "<service_name>",
  "<nvram_key>": "<nvram_value>"
}
```

When received, `httpd` writes the supplied key-value pairs into NVRAM and invokes `notify_rc(rc_service)`.

---

## 🛠️ 5. Standard Service Routine Mapping

| Subsystem | `rc_service` Trigger | NVRAM Arguments | Resulting Action |
| :--- | :--- | :--- | :--- |
| **Wi-Fi Radios** | `restart_wireless` | `wl0_radio=0/1`, `wl1_radio=0/1` | Reloads wireless drivers and toggles 2.4GHz / 5GHz radios. |
| **Guest Wi-Fi** | `restart_wireless;restart_firewall` | `wl0.1_bss_enabled=0/1` | Reconfigures virtual BSSID interfaces and guest client isolation. |
| **Firewall / Parental** | `restart_firewall` | `MULTIFILTER_BLOCK_ALL=0/1`, `vts_enable=0/1` | Rebuilds `iptables` rules for port forwarding, NAT, and client filters. |
| **OpenVPN Client** | `restart_openvpn` | `vpn_client1_state=0/1` | Starts or terminates OpenVPN daemon instances. |
| **WireGuard Client** | `restart_wireguard` | `wgc_enable=0/1` | Configures WireGuard interfaces, routing tables, and peer endpoints. |
| **Ethernet WAN** | `start_wan` / `stop_wan` | `wan_enable=0/1`, `wan0_enable=0/1` | Starts or tears down standard Ethernet WAN connections. |
| **DSL WAN** | `start_dslwan_if 0` / `stop_dslwan_if 0` | `dslx_link_enable=0/1`, `wan0_enable=0/1`, `wan_enable=0/1` | Controls integrated VDSL/ADSL modem interfaces. |

---

## 🌐 6. The DSL Subsystem & Dual WAN Architecture

### WAN Indexing on DSL Routers
On combo modem routers (e.g. `DSL-AX82U`), the primary WAN unit is mapped to the internal DSL modem:
- `wans_dualwan`: Set to `"dsl none"` or `"dsl wan"`.
- `dsl_index`: Mapped to unit `0`.

### NVRAM Synchronization
To maintain consistency across both the firmware backend and the Asus Web UI:
- **`dslx_link_enable`**: Manages the physical DSL connection state (`"1"` = enabled, `"0"` = disabled).
- **`wan0_enable` & `wan_enable`**: General WAN state flags. The Web UI Network Map (`/www/device-map/internet.asp`) checks `wan0_enable` to determine toggle switch position.
- **`freeze_duck`**: Must remain `"0"`. Legacy diagnostic CGI calls (`wan_action.asp`) erroneously set `freeze_duck=1`, freezing the `wanduck` watchdog daemon and locking the web interface.

### Web UI Header Behavior
In `/www/state.js` (line 2920), Asuswrt hardcodes:
```javascript
document.getElementById("connect_status").onclick = wanConnectStatus ? function(){ openHint(24, 3); } : function(){ return false; };
```
The header status icon functions only as a disconnect shortcut when connected; when disconnected (`wanConnectStatus == false`), clicks are disabled by design.

---

## 🗺️ 7. Full Web API Feature Matrix

| Domain | Primary Endpoints | Method | Key Telemetry / Control |
| :--- | :--- | :--- | :--- |
| **Authentication** | `login.cgi`, `login_v2.cgi` | POST | Issues `asus_token` cookie. |
| **Connected Clients** | `ajax_onboarding.asp`, `update_clients.asp` | POST / GET | MAC, IP, hostname, vendor, RSSI, Wi-Fi band, transfer counters. |
| **AiMesh Network** | `ajax_onboarding.asp` | POST | Node topology, backhaul link types, signal strength, firmware levels. |
| **CPU & Memory** | `appGet.cgi` | POST | Per-core CPU utilization percentage, total/free/cached RAM. |
| **Interface Traffic** | `appGet.cgi` | POST | Real-time byte and packet throughput for WAN, LAN, and Wi-Fi. |
| **Thermal Sensors** | `ajax_coretmp.asp` | GET | Real-time temperature readings for CPU and wireless radios. |
| **Ethernet Ports** | `get_port_status.cgi`, `ajax_ethernet_ports.asp` | GET | RJ45 port link status, negotiation speed, duplex, port aggregation. |
| **Aura RGB Lighting** | `appGet.cgi`, `set_ledg.cgi` | POST | Controls RGB schemes (Rainbow, Breathing, Comet, Wave) and colors. |
| **Stealth LED Mode** | `appGet.cgi`, `applyapp.cgi` | POST | Controls front-panel physical LED indicators (`led_val`). |
| **Parental Controls** | `appGet.cgi`, `applyapp.cgi` | POST | Per-device Internet blocking and scheduled time access. |
| **Port Forwarding** | `appGet.cgi`, `applyapp.cgi` | POST | Virtual server / NAT rule configuration. |
| **Speedtest** | `appGet.cgi` | POST | Triggers native Ookla speedtest; returns latency and bandwidth. |
| **VPN Ecosystem** | `ajax_vpn_status.asp`, `appGet.cgi` | POST | OpenVPN, WireGuard, and VPN Fusion client routing policies. |
| **Dynamic DNS** | `appGet.cgi` | POST | Hostname status, WAN IP registration, provider return code. |
| **DSL Diagnostics** | `ajax_AdslStatus.asp` | GET | SNR margins, line attenuation, interleaved depth, CRC/FEC/HEC errors. |
| **WAN Link Control** | `applyapp.cgi`, `start_apply2.htm` | POST | Cleanly connects or disconnects WAN/DSL uplink. |
