---
title: Testing
parent: Firmware
nav_order: 2
---

# Firmware Testing

`thesada-fw` runs on embedded hardware. Tests are performed against a live device over serial and the web dashboard. An automated + manual test script is provided in `tests/test_firmware.py`.

---

## Test Script (recommended)

```bash
pip install pyserial

# Auto-detect port, run all tests
python tests/test_firmware.py

# Skip hardware-dependent manual groups
python tests/test_firmware.py --skip ota,cellular,ads1115

# Automated checks only
python tests/test_firmware.py --skip sensors,ads1115,mqtt,ota,websocket,sd,cellular
```

The script runs 13 test groups — 6 fully automated (parses serial output), 7 manual/assisted (prompts you to confirm what you observe). See `tests/README.md` for the full group list.

---

## Test Environment

- Device: LILYGO T-SIM7080-S3
- Serial monitor: 115200 baud (`pio device monitor` from a real terminal — not VSCode integrated terminal)
- Web dashboard: `http://[device-ip]/`
- MQTT monitor: `mosquitto_sub -h <broker> -p 8883 --cafile ca.crt -u <user> -P <pass> -t 'thesada/node/#' -v`

---

## 1. Boot + Config

| Check | Expected |
|---|---|
| Serial shows `thesada-fw vX.Y.Z` | Version matches `config.h` |
| Serial shows `[INF][Config]` (no error) | `config.json` parsed OK |
| Serial shows `[INF][WiFi] Connected to <ssid>` | WiFi connects to strongest configured SSID |
| Serial shows `[INF][MQTT] Connected` | MQTT broker reachable |
| Serial shows `[INF][Shell] Shell ready — 27 commands` | Shell initialized |
| Serial shows `[INF][Lua] /scripts/main.lua executed` | Lua boot script ran |
| Serial shows `[INF][Lua] /scripts/rules.lua executed` | Lua rules loaded |
| Serial shows `[INF][Boot] Ready. Type 'help' for commands.` | Boot complete |

**Quick check via shell:**
```
selftest
```
Should show all `[PASS]` with at most a few `[WARN]` for optional items.

---

## 2. Shell (serial + WebSocket)

The same commands work in both the serial terminal and the web terminal.

| Command | Expected output |
|---|---|
| `help` | Lists all 27 commands with descriptions |
| `version` | `thesada-fw vX.Y.Z (date time)` |
| `heap` | `Free: XXXXXX B  Min: XXXXXX B  Max alloc: XXXXXX B` |
| `uptime` | `0d 00:05:12` |
| `ifconfig` | `WiFi: connected` + IP, SSID, RSSI, MAC |
| `ping 8.8.8.8` | `8.8.8.8 resolved to 8.8.8.8` |
| `ntp` | `NTP: synced  UTC: 2026-03-22T...` |
| `mqtt` | `MQTT: connected  broker: ...:8883` |
| `module.list` | Lists enabled modules with `[x]` |
| `ls /` | LittleFS root listing |
| `cat /config.json` | Config JSON content |
| `write /test.txt hello` | `Wrote 5 bytes to /test.txt` |
| `cat /test.txt` | `hello` |
| `rm /test.txt` | `Removed` |
| `df` | LittleFS + SD usage |
| `config.get mqtt.broker` | Broker hostname |
| `config.dump` | Full config JSON |
| `selftest` | `[PASS]` / `[WARN]` lines + `=== X passed, Y failed ===` |
| `unknown` | `Unknown command: unknown` |

---

## 3. Web Dashboard

| Check | Expected |
|---|---|
| GET `http://[ip]/api/info` (no auth) | `{"version":"...","build":"...","device":"..."}` |
| GET `http://[ip]/` with wrong password | 401, no dashboard |
| Dashboard loads with correct password | Sensor table visible |
| Sensor values update every ~60 s | Timestamp refreshes |
| Admin → Terminal → type `version` | Firmware version returned via WebSocket |
| Admin → Terminal → type `help` | All commands listed |

---

## 4. Config Editor

| Check | Expected |
|---|---|
| Admin → Config tab | `config.json` loads in editor |
| Edit `device.friendly_name`, save | Device restarts; new name in footer |
| POST `/api/config` with wrong password | 401, file unchanged |

**Curl test (should return 401):**
```bash
curl -X POST http://[ip]/api/config \
  -u admin:wrongpassword \
  -H 'Content-Type: application/json' \
  -d '{"device":{"name":"hacked"}}'
```

---

## 5. Lua Scripting

| Check | Expected |
|---|---|
| `lua.exec return 42` | `42` |
| `lua.exec Log.info("test")` | `OK` (plus `[INF][Lua] test` in log) |
| `lua.exec bad syntax!!!` | `Error: ...` |
| `lua.reload` | `Lua scripts reloaded` + scripts re-execute |
| Modify `/scripts/rules.lua`, run `lua.reload` | New rule behavior active immediately |
| MQTT message to `<prefix>/cmd/lua/reload` | Same as `lua.reload` |

---

## 6. OTA (pull-based)

| Check | Expected |
|---|---|
| `config.get ota.manifest_url` returns empty | `[WRN][OTA] No manifest_url` logged at boot |
| Set `ota.manifest_url` to a valid URL, restart | `[INF][OTA] Ready — checking every 6h` |
| Publish any payload to `<prefix>/cmd/ota` | `[INF][OTA]` check logged; fetches manifest |
| Manifest version matches current | `[INF][OTA] Already at latest` |
| Manifest version is newer | Download + verify + install + reboot |
| Manifest SHA256 mismatch | `[ERR][OTA] SHA256 mismatch` — no flash |

---

## 7. OTA (push via web)

| Check | Expected |
|---|---|
| Upload wrong password via Admin → OTA | 401, device keeps running |
| Upload valid `.bin` with correct password | `Done — device rebooting`; new version boots |
| Serial shows `[INF][WebServer] OTA upload complete` | Clean OTA |

---

## 8. Temperature Alerts

Set `temp_high_c` just below current room temperature to trigger immediately.

| Check | Expected |
|---|---|
| Enable one alert rule, save + restart | `Ready — 1 alert rule(s) enabled` |
| Temperature exceeds `temp_high_c` | `[overheat] sensor: XX.XX°C — OVERHEAT...` |
| MQTT monitor receives `<prefix>/alert` | `{"value":"[overheat] ..."}` |
| Alert fires only once | Hysteresis — second reading doesn't re-trigger |
| Temperature drops below threshold | `back to normal`; alert fires again on next cross |
| Set `enabled: false` | No alerts fire |

---

## 9. Webhook

Set `webhook.url` to a local netcat listener:
```bash
nc -l 8080
```
Config: `"webhook": { "url": "http://[your-mac-ip]:8080/test", "message_template": "{{value}}" }`

Trigger an alert. Netcat should receive the POST with `{"value":"[overheat] ..."}`.

---

## 10. SD Card Logging

| Check | Expected |
|---|---|
| SD inserted, device boots | `[INF][SD] Mounted — X.X MB` + `Logging to /log00N.csv` |
| After first sensor read | CSV row: `2026-03-22T14:32:00Z,temperature,{...}` |
| `ls /sd/` | Log files visible |
| `cat /sd/log001.csv` | CSV rows with timestamps |
| `"sd": { "enabled": false }` | `[INF][SD] Disabled` — no mount |
| Config backup button | `/config_backup.json` on SD |

---

## 11. Cellular Fallback

| Check | Expected |
|---|---|
| Remove WiFi / move out of range | `All networks failed — handing off to cellular` |
| LTE-M registration | `Registered — HOME` or `ROAMING` |
| MQTT publishes arrive via cellular | Same topics as WiFi path |
| WiFi back in range after `wifi_check_interval_s` | Device reconnects to WiFi |

---

## Known Limitations (not bugs)

- **Serial input in VSCode** — use `pio device monitor` from a real terminal, not the VSCode integrated terminal. Input may not reach the device.
- **WebSocket terminal** — no auth; accessible to anyone on the local network. Acceptable for LAN-only devices.
- **ADS1115 near-zero readings** — expected when no load is connected to the current clamp.
- **NTP on first boot** — `pool.ntp.org` can take more than 15 s on slow networks; first sensor read may log `ms/<millis>` timestamp.
- **Cellular + WiFi simultaneous** — not supported. Cellular activates only when all WiFi networks fail.
