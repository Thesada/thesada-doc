---
title: Testing
parent: Firmware
nav_order: 2
---

# Firmware Testing

`thesada-fw` runs on embedded hardware — there is no unit test framework. Tests are manual, performed against a live device over serial and the web dashboard.

---

## Test Environment

- Device: LILYGO T-SIM7080-S3
- Serial monitor: 115200 baud (PlatformIO monitor or any serial terminal)
- Web dashboard: `http://[device-ip]/`
- MQTT monitor: `mosquitto_sub -h mqtt.thesada.app -p 8883 --cafile isrg-x1.pem -u mqtt -P <pass> -t 'thesada/node/#' -v`

---

## 1. Boot + Config

| Check | Expected |
|---|---|
| Serial shows `thesada-fw vX.Y.Z` on boot | Version matches `config.h` |
| Serial shows `[INF][Config]` (no error) | config.json parsed OK |
| Serial shows `[INF][WiFi] Connected to <ssid>` | WiFi connects to strongest configured SSID |
| Serial shows `[INF][WiFi] NTP sync started` | NTP initiated after WiFi connect |
| After ~5 s: `time()` returns year ≥ 2024 (check SD timestamps) | NTP synced |
| Serial shows `[INF][MQTT] Connected` | MQTT broker reachable |

---

## 2. Web Dashboard

| Check | Expected |
|---|---|
| GET `http://[ip]/api/info` (no auth) | Returns `{"version":"...","build":"...","device":"..."}` |
| GET `http://[ip]/` with wrong password | Browser shows 401 / re-prompts |
| GET `http://[ip]/` with correct password | Dashboard loads |
| Dashboard footer shows version + build date + device name | Footer text populated |
| Dashboard table shows sensor values | Temperature °C, voltage V visible |
| Sensor values update every ~60 s | Timestamp refreshes in browser |

---

## 3. Config Editor + Auth

| Check | Expected |
|---|---|
| Click Config tab | `config.json` content loads in textarea |
| POST `/api/config` with wrong password (curl or modified JS) | 401 response; file NOT overwritten |
| Edit a non-critical field (e.g. `device.friendly_name`), click Save | Device restarts; new name appears in footer |
| POST `/api/config` with correct password | 200 `{"ok":true}`, device restarts |

**Curl test for auth (should return 401, config unchanged):**
```bash
curl -X POST http://[ip]/api/config \
  -u admin:wrongpassword \
  -H 'Content-Type: application/json' \
  -d '{"device":{"name":"hacked"}}'
```

---

## 4. OTA

| Check | Expected |
|---|---|
| Upload wrong-password via OTA tab | 401 response; device keeps running current firmware |
| Upload valid `.bin` via OTA tab with correct password | `Done — device rebooting`; new version on next boot |
| Serial shows `[INF][WebServer] OTA upload complete` then reboot | Clean OTA without LoadProhibited crash |

---

## 5. Temperature Alerts

Set `temp_high_c` in an alert rule to a value just below current room temperature to trigger immediately.

| Check | Expected |
|---|---|
| Enable one alert rule in config.json, save + restart | Serial shows `Ready — 1 alert rule(s) enabled` |
| Temperature reading exceeds `temp_high_c` | Serial: `[overheat] sensor: XX.XX°C — OVERHEAT...` |
| MQTT monitor receives `thesada/node/alert` | Payload: `{"value":"[overheat] ..."}` |
| Alert fires only once, not every 60 s | Hysteresis: second reading doesn't re-trigger |
| Temperature drops below threshold | Serial: `back to normal`; MQTT alert fires again |
| Set `enabled: false` in alert rule | No alerts fire even when threshold crossed |

---

## 6. Webhook

Set `webhook.url` to a local netcat listener to verify payload:

```bash
nc -l 8080
```

Set config: `"webhook": { "url": "http://[your-mac-ip]:8080/test", "message_template": "{{value}}" }`

Trigger an alert. Netcat should receive:
```
POST /test HTTP/1.1
Content-Type: application/json
...
{"value":"[overheat] sensor: ..."}
```

---

## 7. SD Card Logging

| Check | Expected |
|---|---|
| SD card inserted, device boots | Serial: `[INF][SD] Mounted — X.X MB` + `Logging to /log00N.csv` |
| After first sensor read | CSV row appended: `2025-03-21T14:32:00Z,temperature,{...}` |
| Timestamp is ISO 8601 (not `ms/...`) | NTP sync completed before first read |
| Set `"sd": { "enabled": false }` | Serial: `[INF][SD] Disabled in config` — no mount, no logging |
| Config backup button in Config tab | SD root contains `config_backup.json` with current config |

---

## 8. Cellular Fallback

| Check | Expected |
|---|---|
| Remove WiFi credentials (or move out of range) | Serial: `All networks failed — handing off to cellular` |
| Serial shows LTE-M registration | `Registered — HOME` or `ROAMING` |
| MQTT publishes arrive via cellular | Check MQTT monitor — same topics as WiFi |
| Re-add WiFi / bring back in range | After `wifi_check_interval_s` seconds, device reconnects to WiFi |
| Second `Cellular::begin()` call (on re-init attempt) | No `PMU init failed` error — guarded by `_started` flag |

---

## 9. WebSocket Terminal

Open browser at `http://[ip]/`, click Terminal tab.

| Check | Expected |
|---|---|
| Terminal shows `[connected]` | WebSocket connected |
| Log lines appear as device runs | `[INF][...]` lines stream to browser |
| Type `sensors`, press Send | JSON state object returned inline |
| Type `restart`, press Send | Device reboots; terminal reconnects automatically after 3 s |
| Type `unknown`, press Send | `Unknown command: unknown` response |

---

## 10. Serial Commands

| Command | Expected |
|---|---|
| Type `restart` + Enter in serial monitor | `[INF][Boot] Serial restart requested` then reboot |

---

## Known Limitations (not bugs)

- WebSocket terminal has no auth — accessible to anyone on the local network who knows the URL. Acceptable for local-only devices; do not expose port 80 publicly.
- SCT current sensors may show near-zero values if clamp is not around a live conductor.
- Webhook HTTPS requires TLS 1.2 — `setInsecure()` is used, so cert is not verified. Use `http://` for local HA.
- NTP sync takes a few seconds after WiFi connect; the first sensor read (at 60 s) will typically have a valid timestamp.
