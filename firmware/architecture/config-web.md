---
title: Config & Web UI
parent: Architecture
grand_parent: Firmware
nav_order: 6
description: "Compile-time config.h, runtime config.json, web dashboard, SD card logging, and log format."
---

# Config & Web UI

## Compile-time config (`config.h`)

```cpp
#define FIRMWARE_VERSION "1.x"

// Enable/disable modules
#define ENABLE_TEMPERATURE
#define ENABLE_ADS1115
#define ENABLE_BATTERY       // AXP2101 battery monitoring (requires PowerManager)
#define ENABLE_SD
#define ENABLE_CELLULAR
#define ENABLE_TELEGRAM
// #define ENABLE_PWM

// Board selection
#define BOARD_LILYGO_T_SIM7080_S3

// MQTT TLS (port comes from config.json)
#define MQTT_TLS true
```

---

## Runtime config (`data/config.json`)

See `data/config.json.example` for all fields. Key sections:

```json
{
  "device":      { "name": "thesada-node", "friendly_name": "Thesada Node", "heartbeat_s": -1, "charging_led": true },
  "web":         { "user": "admin", "password": "changeme" },
  "wifi":        { "networks": [...], "timeout_per_ssid_s": 10, "wifi_check_interval_s": 900, "ap_password": "", "ap_timeout_s": 300 },
  "ntp":         { "server": "pool.ntp.org", "tz_offset_s": 3600 },
  "mqtt":        { "broker": "...", "port": 8883, "user": "...", "password": "...",
                   "topic_prefix": "thesada/node", "send_interval_s": 0 },
  "temperature": { "pin": 12, "interval_s": 60, "auto_discover": true, "sensors": [] },
  "ads1115":     { "i2c_sda": 1, "i2c_scl": 2, "address": 72, "interval_s": 60, "channels": [...] },
  "cellular":    { "apn": "OSC", "sim_pin": "", "rf_settle_ms": 15000, "reg_timeout_ms": 180000 },
  "sd":          { "enabled": true, "pin_clk": 38, "pin_cmd": 39, "pin_data": 40 },
  "telegram":    { "bot_token": "", "chat_ids": [], "cooldown_s": 300, "alerts": [...] },
  "webhook":     { "url": "", "message_template": "..." },
  "battery":     { "enabled": true, "interval_s": 60, "low_pct": 20, "charge_ma": 300, "charge_v": 4.2 },
  "sleep":       { "enabled": false, "sleep_s": 300, "wake_s": 30 },
  "ota":         { "enabled": true, "manifest_url": "...", "check_interval_s": 21600, "cmd_topic": "thesada/node/cmd/ota" }
}
```

---

## Web Interface

Accessible at `http://[device-ip]/` - requires login (credentials from `web` config).

| Route | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | public | Live sensor dashboard with MQTT status bar |
| `/api/info` | GET | public | Firmware version, build date, device name |
| `/api/state` | GET | public | Current sensor readings as JSON (includes `_mqtt` metadata) |
| `/api/config` | GET | yes | Read `config.json` |
| `/api/config` | POST | yes | Write `config.json`, restart device (page auto-refreshes after 10s) |
| `/api/backup` | POST | yes | Copy `config.json` to SD card |
| `/api/cmd` | POST | yes | Run any Shell command, get JSON output |
| `/api/restart` | POST | yes | Reboot device |
| `/api/ws/token` | GET | yes | Issue a 30 s IP-bound WS auth grant (required before opening WebSocket) |
| `/ota` | POST | yes | Upload firmware `.bin` (push OTA, page auto-refreshes after 10s) |
| `/ws/serial` | WS | token | Bidirectional terminal - log stream + all Shell commands |

![Sensor dashboard]({{ site.baseurl }}/assets/img/firmware/dashboard-sensors.png)

**Dashboard** - public read-only view:
- Sensor table polls `/api/state` every 5 s - shows temperature, current, and battery (%, voltage, charge state)
- MQTT status bar: green/red dot, connected state, last publish timestamp (from `_mqtt` key in `/api/state`)
- Battery rows color-coded: green when charging, red when below 20%

**Admin terminal** - auth-gated WebSocket terminal:
- Streams all firmware log lines in real time
- Log level filter: ALL / INF / WRN / ERR / DBG (client-side, 500-line ring buffer)
- Clear button; auto-reconnects on disconnect
- WebSocket auth: JS fetches `/api/ws/token` (Basic Auth) before opening the socket; the server grants the caller IP 30 s access; `WS_EVT_CONNECT` verifies and closes unauthenticated connections immediately

**WebSocket / serial terminal commands:** all Shell built-ins (see Shell & Scripting page). Type `help` for the full list.

---

## SD Card Logging

Logs sensor events as CSV. A new file is opened on each boot; when `sd.max_file_kb` is exceeded the module rotates to the next file automatically.

**File naming:** `/log001.csv`, `/log002.csv`, ... up to `/log999.csv`.

**CSV format:** `timestamp,sensor,json_data`

Timestamp is ISO 8601 UTC (`2026-03-22T14:32:00Z`) when NTP is synced; falls back to `ms/<millis>` before sync.

**Logrotate config** (`config.json`):
```json
"sd": {
  "enabled":     true,
  "max_file_kb": 1024
}
```
- `max_file_kb: 1024` - rotate to the next file when current exceeds 1 MB
- `max_file_kb: 0` - no size limit (file grows indefinitely until next boot)

When a rotation happens the log shows:
```
[INF][SD] Rotating - /log001.csv full
[INF][SD] Logging to /log002.csv
```

Disable logging entirely via `"sd": { "enabled": false }`.
Config backup via `/api/backup` copies `config.json` to `/config_backup.json` on SD.

---

## Logging

All `Log::info/warn/error` calls write to:
1. **Serial** (USB CDC, 115200 baud)
2. **WebSocket** `/ws/serial` - all connected terminal clients receive each log line

**Format - before NTP sync:**
```
[INF][TAG] message
[WRN][TAG] message
[ERR][TAG] message
```

**Format - after NTP sync** (epoch > 1700000000):
```
[INF][2026-03-22T14:32:00Z][TAG] message
```

The timestamp is inserted between the log level and the tag. `Log::write()` checks `time(nullptr)` on every call; the format switches automatically once the clock is set. Run the `ntp` shell command to see the current sync status and whether log timestamps are active.
