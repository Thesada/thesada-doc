---
title: Setup & Basics
parent: Testing
grand_parent: Firmware
nav_order: 1
description: "Test environment, CA certificate setup, boot verification, heartbeat LED, shell commands, and web dashboard checks."
---

# Setup & Basics

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

### Runtime ca.crt Upload (deployed devices)

If the device is already flashed and accessible over the network, upload `ca.crt` via the file API without reflashing:

```bash
# Upload ca.crt to LittleFS
curl -u admin:changeme -X POST \
  'http://[ip]/api/file?path=/ca.crt&source=littlefs' \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @base/data/ca.crt

# Restart to apply
curl -u admin:changeme -X POST \
  'http://[ip]/api/cmd' \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"restart"}'
```

Verify after reboot:
```bash
curl -u admin:changeme -X POST \
  'http://[ip]/api/cmd' \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"cat /ca.crt"}'
```

The PEM bundle should contain ISRG Root X1 (for Let's Encrypt / GitHub OTA) and USERTrust ECC (for github.com). Both are needed for end-to-end GitHub OTA. For cellular MQTT, the modem uses the same `/ca.crt` file - if absent, it connects without CA verification and logs a warning.

---

## 1. Boot + Config

| Check | Expected |
|---|---|
| Serial shows `thesada-fw vX.Y.Z` | Version matches `config.h` |
| Serial shows `[INF][Config]` (no error) | `config.json` parsed OK |
| Serial shows `[INF][WiFi] Connected to <ssid>` | WiFi connects to strongest configured SSID |
| Serial shows `[INF][MQTT] Connected` | MQTT broker reachable |
| Serial shows `[INF][Shell] Shell ready - xx commands` | Shell initialized - Commands available is depending on compiled modules|
| Serial shows `[INF][Lua] /scripts/main.lua executed` | Lua boot script ran |
| Serial shows `[INF][Lua] /scripts/rules.lua executed` | Lua rules loaded |
| Serial shows `[INF][Boot] Ready. Type 'help' for commands.` | Boot complete |

**NTP log timestamps:** once NTP syncs, log lines gain an ISO 8601 timestamp between the level and the tag:
```
[INF][2026-03-22T14:32:00Z][WiFi] Connected to myssid
```
Before sync the format is `[INF][WiFi] ...`. Run `net.ntp` to confirm - it reports `log timestamps: active` or `log timestamps: pending sync`.

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
| Wait 10-12 s | Blue CHGLED pulses once (~150 ms) |
| Set `device.heartbeat_s` to `3` (below minimum) | Clamped to 5 s automatically |
| Set `device.heartbeat_s` to `-1`, restart | `[INF][Heartbeat] Disabled` - LED stays off |

---

## 3. Shell (serial + WebSocket)

The same commands work in both the serial terminal and the web terminal.

| Command | Expected output |
|---|---|
| `help` | Lists all commands with descriptions |
| `version` | `thesada-fw vX.Y.Z (date time)` |
| `heap` | `Free: XXXXXX B  Min: XXXXXX B  Max alloc: XXXXXX B` |
| `uptime` | `0d 00:05:12` |
| `net.ip` | `WiFi: connected` + IP, SSID, RSSI, MAC |
| `net.ping 8.8.8.8` | `8.8.8.8 resolved to 8.8.8.8` |
| `net.ntp` | `NTP: synced  UTC: 2026-03-22T...` + `log timestamps: active` |
| `mqtt` | `MQTT: connected  broker: ...:8883` |
| `module.list` | Lists enabled modules with `[x]` |
| `fs.ls /` | LittleFS root listing |
| `fs.cat /config.json` | Config JSON content |
| `write /test.txt hello` | `Wrote 5 bytes to /test.txt` |
| `fs.cat /test.txt` | `hello` |
| `fs.rm /test.txt` | `Removed` |
| `fs.df` | LittleFS + SD usage |
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
| Admin - Terminal tab | `[connected]` appears; live log lines flow in |
| Log level filter set to `WRN` | Only `[WRN]` lines visible; others hidden |
| Log level filter set to `ALL` | All log lines visible again |
| Clear button | Terminal output cleared |
| Admin - Terminal - type `version` | Firmware version returned via WebSocket |
| Admin - Terminal - type `help` | All commands listed |
