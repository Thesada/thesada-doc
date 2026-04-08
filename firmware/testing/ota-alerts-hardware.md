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

Set an alert rule with `function: "gte"` and `value` just below current room temperature to trigger immediately.

| Check | Expected |
|---|---|
| Enable one alert rule, save + restart | `Ready - 1 alert rule(s) enabled` |
| Reading crosses threshold (function/value) | `[overheat] sensor: XX.XX C - OVERHEAT (>= YY.Y C)` |
| MQTT monitor receives `<prefix>/alert` | `{"value":"[overheat] ..."}` |
| Alert fires only once | Hysteresis - second reading doesn't re-trigger |
| Reading returns to normal | `back to normal`; alert fires again on next cross |
| Cooldown: re-trigger within `cooldown_s` | Alert suppressed until cooldown expires |
| Recovery: back to normal during cooldown | Recovery always sends immediately |
| `sensors: ["temp_1"]` filter | Only temp_1 triggers, other sensors ignored |
| `sensors: []` (empty) | All sensors trigger (default) |
| Custom `message` field | Alert label matches config value |
| Set `enabled: false` | No alerts fire |

## 11a. MQTT Config Set/Push

| Check | Expected |
|---|---|
| Publish `{"path":"telegram.cooldown_s","value":"600"}` to `<prefix>/cmd/config/set` | Config updated, saved to disk, reloaded |
| Verify via API: `GET /api/file?path=/config.json&source=littlefs` | Value changed |
| Publish full config JSON to `<prefix>/cmd/config/push` | Config replaced, saved, reloaded |
| Push invalid JSON | Error logged, config rolls back to file on disk |
| Set non-existent path | Error logged, no crash |

## 11b. Fallback AP

| Check | Expected |
|---|---|
| Set WiFi SSID to invalid, restart | AP appears: `<device.name>-setup` |
| Connect phone to AP SSID | Captive portal redirects to dashboard |
| Dashboard loads at 192.168.4.1 | Sensor table, config editor, terminal all functional |
| `ap_password` set (min 8 chars) | AP is WPA2 protected |
| `ap_timeout_s` expires | AP stops, WiFi scan retries |
| Fix WiFi SSID via config editor in AP mode | Node connects to WiFi on next cycle |

## 11c. NTP Manual Time Set

| Check | Expected |
|---|---|
| `net.ntp set 1774674000` | `Time set to 2026-03-28T05:00:00Z (epoch 1774674000)` |
| `net.ntp set 2026-03-28T05:00:00Z` | Same result via ISO 8601 |
| `net.ntp set 0` | `Invalid time` error |
| `net.ntp` (no args) | Shows current UTC time, server, offset |

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
| `fs.ls /sd/` | Log files visible |
| `fs.cat /sd/log001.csv` | CSV rows with timestamps |
| `"sd": { "enabled": false }` | `[INF][SD] Disabled` - no mount |
| Config backup button | `/config_backup.json` on SD |

**Logrotate test:**

Set `sd.max_file_kb` to a small value (e.g. `2`) and wait for a few sensor reads. The device should log:
```
[INF][SD] Rotating - /log001.csv full
[INF][SD] Logging to /log002.csv
```
Both files should appear in `fs.ls /sd/`. Reset `max_file_kb` to `1024` when done.

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
