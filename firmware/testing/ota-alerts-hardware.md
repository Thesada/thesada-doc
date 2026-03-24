---
title: OTA, Alerts & Hardware
parent: Testing
grand_parent: Firmware
nav_order: 3
description: "OTA update testing (pull and push), temperature alerts, webhook, SD card logging, battery monitoring, deep sleep, and cellular fallback."
---

# OTA, Alerts & Hardware

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
| Upload wrong password via Admin - OTA | 401, device keeps running |
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
| Temperature exceeds `temp_high_c` | `[overheat] sensor: XX.XXC - OVERHEAT...` |
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
Config: `"webhook": { "url": "http://[your-ip]:8080/test", "message_template": "{% raw %}{{value}}{% endraw %}" }`

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
| Set `battery.enabled` to `false`, restart | `[INF][Battery] Disabled via config` - no battery rows on dashboard |
| Set `battery.enabled` to `true`, restart | Battery monitoring resumes |

---

## 15. Deep Sleep

| Check | Expected |
|---|---|
| `sleep` command with sleep disabled | `Sleep: disabled  boot #1` |
| Set `sleep.enabled: true, sleep_s: 30, wake_s: 30`, restart | `[INF][Sleep] Enabled - awake 30s, sleep 30s (boot #1)` |
| Wait 30s | Device goes to sleep (unreachable for 30s) |
| Wait another 30s | Device wakes, boot count increments |
| `sleep` command after several cycles | `boot #N` incrementing, last OTA check persisted |
| Set `sleep.enabled: false`, restart | Normal continuous operation restored |

---

## 16. Cellular Fallback

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
