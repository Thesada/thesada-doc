---
title: Testing
parent: Firmware
nav_order: 2
description: "Manual and automated test checklist for thesada-fw firmware -- API, OTA, MQTT, sensors, and WebSocket verification."
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

The script runs 13 test groups - 6 fully automated (parses serial output), 7 manual/assisted (prompts you to confirm what you observe). See `tests/README.md` for the full group list.

---

## Test Environment

- Device: LILYGO T-SIM7080-S3
- Serial monitor: 115200 baud (`pio device monitor` from a real terminal - not VSCode integrated terminal)
- Web dashboard: `http://[device-ip]/`
- MQTT monitor: `mosquitto_sub -h <broker> -p 8883 --cafile ca.crt -u <user> -P <pass> -t 'thesada/node/#' -v`

---

## 0. Pre-flight: CA Certificate + First Flash

Before first flash, ensure `data/ca.crt` contains the correct root CA. For Let's Encrypt brokers (including `mqtt.thesada.app`) and GitHub OTA, the ISRG Root X1 covers both:

```bash
curl -s https://letsencrypt.org/certs/isrgrootx1.pem -o base/data/ca.crt
```

Verify:
```bash
openssl x509 -in base/data/ca.crt -noout -subject -issuer
# subject=CN=ISRG Root X1
# issuer=CN=ISRG Root X1  (self-signed root - correct)
```

Upload filesystem (includes `ca.crt` and `config.json`):
```bash
pio run -e esp32-s3-dev --target uploadfs
```

If `ca.crt` is absent or wrong, TLS still connects but logs `[WRN][MQTT] No CA cert - insecure`. MQTT and OTA will work but without certificate verification.

---

## 1. Boot + Config

| Check | Expected |
|---|---|
| Serial shows `thesada-fw vX.Y.Z` | Version matches `config.h` |
| Serial shows `[INF][Config]` (no error) | `config.json` parsed OK |
| Serial shows `[INF][WiFi] Connected to <ssid>` | WiFi connects to strongest configured SSID |
| Serial shows `[INF][MQTT] Connected` | MQTT broker reachable |
| Serial shows `[INF][Shell] Shell ready - 27 commands` | Shell initialized |
| Serial shows `[INF][Lua] /scripts/main.lua executed` | Lua boot script ran |
| Serial shows `[INF][Lua] /scripts/rules.lua executed` | Lua rules loaded |
| Serial shows `[INF][Boot] Ready. Type 'help' for commands.` | Boot complete |

**NTP log timestamps:** once NTP syncs, log lines gain an ISO 8601 timestamp between the level and the tag:
```
[INF][2026-03-22T14:32:00Z][WiFi] Connected to myssid
```
Before sync the format is `[INF][WiFi] ...`. Run `ntp` to confirm - it reports `log timestamps: active` or `log timestamps: pending sync`.

**Quick check via shell:**
```
selftest
```
Should show all `[PASS]` with at most a few `[WARN]` for optional items.

---

## 2. Heartbeat LED

| Check | Expected |
|---|---|
| `config.get device.heartbeat_s` returns `-1` | LED stays off - disabled |
| Set `device.heartbeat_s` to `10`, restart | `[INF][Heartbeat] Ready - every 10s` in boot log |
| Wait 10–12 s | Blue CHGLED pulses once (~150 ms) |
| Set `device.heartbeat_s` to `3` (below minimum) | Clamped to 5 s automatically |
| Set `device.heartbeat_s` to `-1`, restart | `[INF][Heartbeat] Disabled` - LED stays off |

---

## 3. Shell (serial + WebSocket)

The same commands work in both the serial terminal and the web terminal.

| Command | Expected output |
|---|---|
| `help` | Lists all 27 commands with descriptions |
| `version` | `thesada-fw vX.Y.Z (date time)` |
| `heap` | `Free: XXXXXX B  Min: XXXXXX B  Max alloc: XXXXXX B` |
| `uptime` | `0d 00:05:12` |
| `ifconfig` | `WiFi: connected` + IP, SSID, RSSI, MAC |
| `ping 8.8.8.8` | `8.8.8.8 resolved to 8.8.8.8` |
| `ntp` | `NTP: synced  UTC: 2026-03-22T...` + `log timestamps: active` |
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

## 4. Web Dashboard

| Check | Expected |
|---|---|
| GET `http://[ip]/api/info` (no auth) | `{"version":"...","build":"...","device":"..."}` |
| GET `http://[ip]/` with wrong password | 401, no dashboard |
| Dashboard loads with correct password | Sensor table visible |
| Sensor values update every ~60 s | Timestamp refreshes |
| Battery %, Battery V, Battery Charge State rows visible | Shows percent, voltage, Charging/Discharging |
| Battery % red when <= 20%, green when charging | Color coding works |
| MQTT status bar visible above sensor table | Green dot + `MQTT connected` + last publish time |
| MQTT disconnected state | Red dot + `MQTT disconnected` |
| Admin → Terminal tab | `[connected]` appears; live log lines flow in |
| Log level filter set to `WRN` | Only `[WRN]` lines visible; others hidden |
| Log level filter set to `ALL` | All log lines visible again |
| Clear button | Terminal output cleared |
| Admin → Terminal → type `version` | Firmware version returned via WebSocket |
| Admin → Terminal → type `help` | All commands listed |

---

## 5. /api/cmd (HTTP Shell)

All Shell commands are available over HTTP. Requires auth. Run the test script with `--web-pass` to enable automated checks, or test manually with curl:

```bash
# version command
curl -s -u admin:changeme \
  -X POST http://[ip]/api/cmd \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"version"}'
# → {"ok":true,"output":["thesada-fw v1.x ..."]}

# wrong password → 401
curl -s -u admin:wrong \
  -X POST http://[ip]/api/cmd \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"version"}'
# → {"ok":false,"error":"Unauthorized"}
```

| Check | Expected |
|---|---|
| POST `/api/cmd` `{"cmd":"version"}` with correct password | `{"ok":true,"output":["thesada-fw v1.x ..."]}` |
| POST `/api/cmd` `{"cmd":"heap"}` | `{"ok":true,"output":["Free: XXXXXX B ..."]}` |
| POST `/api/cmd` `{"cmd":"xyzzy"}` | `{"ok":true,"output":["Unknown command: xyzzy"]}` |
| POST `/api/cmd` with wrong password | `401 Unauthorized` |
| POST `/api/cmd` with malformed JSON body | `400` / `{"ok":false,"error":"..."}` |

**Test script:**
```bash
python tests/test_firmware.py --web-pass changeme
```

---

## 6. Security

**Rate limiting** - 5 failed logins lock out the source IP for 30 s:

```bash
for i in $(seq 1 6); do
  curl -s -u admin:wrong http://[ip]/api/auth/check
  echo
done
# Attempts 1-5 → {"ok":false,"error":"Unauthorized"}
# Attempt 6   → {"ok":false,"error":"Too many attempts - wait 30s"}
```

**WebSocket auth** - unauthenticated direct connections are rejected:

```bash
curl -i http://[ip]/ws/serial \
  -H "Upgrade: websocket" \
  -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlc2FtcGxlbm9uY2U=" \
  -H "Sec-WebSocket-Version: 13"
# → 101 (handshake completes), then immediately receives WS close frame
# Serial log shows: [WRN][WebServer] WS: rejected - not pre-authorized
```

**WS token endpoint** - requires auth:

```bash
curl http://[ip]/api/ws/token
# → {"ok":false,"error":"Unauthorized"}

curl -u admin:changeme http://[ip]/api/ws/token
# → {"ok":true}
```

---

## 7. Config Editor

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

## 8. Lua Scripting

| Check | Expected |
|---|---|
| `lua.exec return 42` | `42` |
| `lua.exec Log.info("test")` | `OK` (plus `[INF][Lua] test` in log) |
| `lua.exec bad syntax!!!` | `Error: ...` |
| `lua.reload` | `Lua scripts reloaded` + scripts re-execute |
| Modify `/scripts/rules.lua`, run `lua.reload` | New rule behavior active immediately |
| MQTT message to `<prefix>/cmd/lua/reload` | Same as `lua.reload` |

---

## 9. OTA (pull-based)

| Check | Expected |
|---|---|
| `config.get ota.manifest_url` returns empty | `[WRN][OTA] No manifest_url` logged at boot |
| Set `ota.manifest_url` to a valid URL, restart | `[INF][OTA] Ready - checking every 6h` |
| Publish any payload to `<prefix>/cmd/ota` | `[INF][OTA]` check logged; fetches manifest |
| Manifest version matches current | `[INF][OTA] Already at latest` |
| Manifest version is newer | Download + verify + install + reboot |
| Manifest SHA256 mismatch | `[ERR][OTA] SHA256 mismatch` - no flash |

---

## 10. OTA (push via web)

| Check | Expected |
|---|---|
| Upload wrong password via Admin → OTA | 401, device keeps running |
| Upload valid `.bin` with correct password | `Done - device rebooting`; new version boots |
| Serial shows `[INF][WebServer] OTA upload complete` | Clean OTA |

**Using the upload script (recommended for development):**

`scripts/ota_upload.py` handles access check, password prompt, and upload in one step. Run from `base/`:

```bash
# Build first
~/.platformio/penv/bin/pio run -e esp32-s3-dev

# Upload (prompts for password, does not echo it)
python3 scripts/ota_upload.py 172.16.1.212

# Custom username or binary path
python3 scripts/ota_upload.py 172.16.1.212 --user admin --bin build/firmware.bin
```

The script checks credentials before uploading and prints the current device version so you can confirm which firmware is being replaced. After a successful upload the device restarts automatically.

Verify the new version booted:
```bash
curl http://172.16.1.212/api/info
```

---

## 11. Temperature Alerts

Set `temp_high_c` just below current room temperature to trigger immediately.

| Check | Expected |
|---|---|
| Enable one alert rule, save + restart | `Ready - 1 alert rule(s) enabled` |
| Temperature exceeds `temp_high_c` | `[overheat] sensor: XX.XX°C - OVERHEAT...` |
| MQTT monitor receives `<prefix>/alert` | `{"value":"[overheat] ..."}` |
| Alert fires only once | Hysteresis - second reading doesn't re-trigger |
| Temperature drops below threshold | `back to normal`; alert fires again on next cross |
| Set `enabled: false` | No alerts fire |

---

## 12. Webhook

Set `webhook.url` to a local netcat listener:
```bash
nc -l 8080
```
Config: `"webhook": { "url": "http://[your-mac-ip]:8080/test", "message_template": "{{value}}" }`

Trigger an alert. Netcat should receive the POST with `{"value":"[overheat] ..."}`.

---

## 13. SD Card Logging

| Check | Expected |
|---|---|
| SD inserted, device boots | `[INF][SD] Mounted - X.X MB` + `Logging to /log00N.csv (max 1024 KB per file)` |
| After first sensor read | CSV row: `2026-03-22T14:32:00Z,temperature,{...}` |
| `ls /sd/` | Log files visible |
| `cat /sd/log001.csv` | CSV rows with timestamps |
| `"sd": { "enabled": false }` | `[INF][SD] Disabled` - no mount |
| Config backup button | `/config_backup.json` on SD |

**Logrotate test:**

Set `sd.max_file_kb` to a small value (e.g. `2`) and wait for a few sensor reads. The device should log:
```
[INF][SD] Rotating - /log001.csv full
[INF][SD] Logging to /log002.csv
```
Both files should appear in `ls /sd/`. Reset `max_file_kb` to `1024` when done.

---

## 14. Battery Monitoring

| Check | Expected |
|---|---|
| `sensors` command | Battery line: `batt  X.XXV  XX%  [CHG/DSG]` |
| `battery` command | `X.XXV  XX%  charging/discharging` |
| `module.status` | `battery  pmu=ok  present=yes` |
| `/api/state` includes `battery` object | `{"present":true,"voltage_v":X.XX,"percent":XX,"charging":false}` |
| Dashboard shows Battery %, V, Charge State | Three rows in sensor table |
| Set `battery.enabled` to `false`, restart | `[INF][Battery] Disabled via config` — no battery rows on dashboard |
| Set `battery.enabled` to `true`, restart | Battery monitoring resumes |

---

## 15. Cellular Fallback

| Check | Expected |
|---|---|
| Remove WiFi / move out of range | `All networks failed - handing off to cellular` |
| LTE-M registration | `Registered - HOME` or `ROAMING` |
| MQTT publishes arrive via cellular | Same topics as WiFi path |
| WiFi back in range after `wifi_check_interval_s` | Device reconnects to WiFi |

---

## Known Limitations (not bugs)

- **Serial input in VSCode** - use `pio device monitor` from a real terminal, not the VSCode integrated terminal. Input may not reach the device.
- **WebSocket terminal** - no auth; accessible to anyone on the local network. Acceptable for LAN-only devices.
- **ADS1115 near-zero readings** - expected when no load is connected to the current clamp.
- **NTP on first boot** - `pool.ntp.org` can take more than 15 s on slow networks; first sensor read may log `ms/<millis>` timestamp.
- **Cellular + WiFi simultaneous** - not supported. Cellular activates only when all WiFi networks fail.
