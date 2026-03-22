---
title: Architecture
parent: Firmware
nav_order: 1
---

# Firmware Architecture

`thesada-fw` is built on C++17 with the Arduino framework, compiled via PlatformIO for the LILYGO T-SIM7080-S3 (ESP32-S3). It uses a **Module Registry** pattern with a lightweight **Event Bus** for inter-module communication.

---

## Design Principles

- **Modular** — each sensor or peripheral is a self-contained module
- **Config-driven** — compile-time enables via `config.h`, runtime values via `config.json` on LittleFS
- **Event-driven** — modules communicate via an internal Event Bus, not direct calls
- **Pluggable** — adding a new module requires creating one folder and one line in `config.h`
- **Resilient** — automatic WiFi → cellular fallback; MQTT queue survives short disconnects
- **Scriptable** — Lua 5.3 runtime with hot-reloadable rules; no recompile needed for logic changes

---

## Repository Structure

```
thesada-fw/base/
├── platformio.ini                  ← build targets + library deps
├── config.h                        ← compile-time module enables + version
├── TODO.md                         ← project task list
├── scripts/
│   ├── generate_manifest.py        ← post-build: build/firmware.json with SHA256 + version
│   └── copy_firmware.py            ← post-build: copies .bin to build/
├── tests/
│   └── test_firmware.py            ← automated + manual test suite (pyserial)
├── lib/
│   └── AsyncTCP/                   ← vendored AsyncTCP v3.3.2 (null-PCB crash fixes)
├── data/
│   ├── config.json                 ← runtime config (LittleFS)
│   ├── config.json.example         ← template with all fields documented
│   ├── ca.crt                      ← TLS CA cert (required for cert verification)
│   └── scripts/
│       ├── main.lua                ← Lua boot script (runs once at startup)
│       └── rules.lua               ← Lua event rules (hot-reloadable)
└── src/
    ├── main.cpp
    ├── core/
    │   ├── Module.h                ← base class for all modules
    │   ├── ModuleRegistry.h/.cpp   ← instantiates + drives all modules
    │   ├── EventBus.h/.cpp         ← pub/sub between modules
    │   ├── Config.h/.cpp           ← config.json loader (LittleFS)
    │   ├── Log.h/.cpp              ← serial + WebSocket log relay
    │   ├── WiFiManager.h/.cpp      ← multi-SSID, RSSI-ranked, NTP sync
    │   ├── MQTTClient.h/.cpp       ← TLS MQTT, publish queue, subscription dispatch
    │   ├── OTAUpdate.h/.cpp        ← HTTP(S) pull OTA with SHA256 verify
    │   ├── Shell.h/.cpp            ← unified CLI (serial + WebSocket share same handlers)
    │   ├── ScriptEngine.h/.cpp     ← Lua 5.3 runtime with EventBus + MQTT bindings
    │   ├── Cellular.h/.cpp         ← SIM7080G modem-native MQTT over TLS
    │   └── WebServer.h/.cpp        ← dashboard, config editor, file browser, terminal
    └── modules/
        ├── temperature/            ← DS18B20 one-wire sensors
        ├── ads1115/                ← ADS1115 differential current sensing
        ├── cellular/               ← cellular module (alert routing via LTE)
        ├── sd/                     ← SD card CSV logger
        ├── telegram/               ← temperature threshold alerts + webhook
        ├── current/                ← current sensor module
        └── pwm/                    ← PWM output
```

---

## Boot Sequence

```
setup()
  Config::load()          → mounts LittleFS, parses config.json
  WiFiManager::begin()    → scans, ranks by RSSI, connects, starts NTP
  if WiFi ok:
    MQTTClient::begin()   → TLS MQTT to broker; registers cmd/ota subscription
    OTAUpdate::begin()    → registers MQTT cmd/ota handler, optional periodic check
  else:
    Cellular::begin()     → PMU, modem, SIM, network, modem-MQTT
  WebServer::begin()      → HTTP dashboard + WebSocket terminal
  Shell::begin()          → registers all 27 built-in commands
  ScriptEngine::begin()   → Lua state, executes main.lua + rules.lua
                            registers MQTT cmd/lua/reload handler
  ModuleRegistry::begin() → begin() on all enabled modules

loop()
  Serial shell            → reads characters, executes line on newline via Shell::execute()
  WiFiManager::loop()     → reconnect / recheck
  MQTTClient::loop() or Cellular::loop()
  OTAUpdate::loop()       → periodic interval check (WiFi only)
  WebServer::loop()       → handle deferred restarts
  ModuleRegistry::loop()  → loop() on all enabled modules
```

---

## Module Base Class

Every module inherits from `Module`:

```cpp
class Module {
public:
  virtual void begin() = 0;
  virtual void loop()  = 0;
  virtual const char* name() = 0;
  virtual ~Module() {}
};
```

The `ModuleRegistry` calls `begin()` once at startup and `loop()` every cycle. Modules should never block in `loop()`.

---

## Event Bus

Modules never call each other directly. They publish events with a JSON payload and subscribe to events from other modules. The Event Bus is synchronous — subscribers run inline when `publish()` is called.

```cpp
// Publish a temperature reading (in TemperatureModule)
JsonDocument doc;
JsonArray sensors = doc["sensors"].to<JsonArray>();
JsonObject s = sensors.add<JsonObject>();
s["name"]   = "barn_supply";
s["temp_c"] = 18.4;
EventBus::publish("temperature", doc.as<JsonObject>());

// Subscribe (in TelegramModule or any other module)
EventBus::subscribe("temperature", [](JsonObject data) {
  JsonArray sensors = data["sensors"].as<JsonArray>();
  for (JsonObject s : sensors) {
    float temp = s["temp_c"] | -999.0f;
    // react to reading
  }
});
```

**Standard event names and payload schemas:**

| Event | Publisher | Payload |
|---|---|---|
| `temperature` | TemperatureModule | `{ "sensors": [ { "name": "x", "address": "...", "temp_c": 18.4 } ] }` |
| `current` | ADS1115Module | `{ "channels": [ { "name": "x", "voltage_v": 0.012, "raw": 123 } ] }` |
| `alert` | TelegramModule | `{ "value": "alert message text" }` |

---

## Shell (CLI)

`Shell` is a unified command-line interface. The same command handlers run for both the serial terminal and the WebSocket web terminal — there is no duplicate logic.

**Transport wiring:**
- Serial: `main.cpp` reads characters, calls `Shell::execute(line, serialOut)` on newline
- WebSocket: `WebServer.cpp` receives WS data, calls `Shell::execute(cmd, [client](line){ client->text(line); })`

**Registering a command:**
```cpp
Shell::registerCommand("name", "one-line help text", [](int argc, char** argv, ShellOutput out) {
  out("response line");
});
```

**Built-in commands:**

| Group | Commands |
|---|---|
| System | `help`, `version`, `restart`, `heap`, `uptime`, `sensors`, `selftest` |
| Filesystem | `ls`, `cat`, `rm`, `write`, `mv`, `df` |
| Config | `config.get`, `config.set`, `config.save`, `config.reload`, `config.dump` |
| Network | `ifconfig`, `ping`, `ntp`, `mqtt` |
| Modules | `module.list`, `module.status` |
| Lua | `lua.exec`, `lua.load`, `lua.reload` |

Paths prefixed with `/sd/` are routed to SD_MMC; all others go to LittleFS.

---

## Lua Scripting (ScriptEngine)

Lua 5.3 runtime via the [ESP-Arduino-Lua](https://github.com/sfranzyshen/ESP-Arduino-Lua) library (GPL-3.0).

**Scripts on LittleFS:**
- `/scripts/main.lua` — runs once at boot (setup tasks, one-time subscriptions)
- `/scripts/rules.lua` — event-driven rules, hot-reloadable without restart

**Lua API:**

| Function | Description |
|---|---|
| `Log.info(msg)` | Log at INFO level (tag: Lua) |
| `Log.warn(msg)` | Log at WARN level |
| `Log.error(msg)` | Log at ERROR level |
| `EventBus.subscribe(event, func)` | Subscribe to named event; func receives a table |
| `MQTT.publish(topic, payload)` | Publish a message to MQTT |
| `Config.get(key)` | Read config value by dot-notation key (e.g. `"mqtt.broker"`) |
| `Node.restart()` | Reboot the device |
| `Node.version()` | Returns firmware version string |
| `Node.uptime()` | Returns `millis()` as number |

**Hot reload:**
`ScriptEngine::reload()` bumps a generation counter, destroys the Lua state, creates a fresh one, and re-executes both scripts. Stale EventBus callbacks check the generation counter and silently skip. Reload is triggered by:
- Shell command: `lua.reload`
- MQTT message to `<topic_prefix>/cmd/lua/reload`

**Example rules.lua:**
```lua
EventBus.subscribe("temperature", function(data)
  local sensors = data.sensors
  for i = 1, #sensors do
    local s = sensors[i]
    if s.temp_c > 40 then
      Log.warn("High temp: " .. s.name .. " " .. s.temp_c .. "C")
      MQTT.publish("thesada/node/alert", s.name .. " overheating")
    end
  end
end)
```

---

## OTA Update (OTAUpdate)

HTTP(S) pull-based OTA. The device fetches a JSON manifest, compares semver, and streams + verifies the firmware binary.

**Manifest format** (`build/firmware.json`, generated by `scripts/generate_manifest.py`):
```json
{
  "version": "1.0.9",
  "url": "https://example.com/firmware.bin",
  "sha256": "abc123..."
}
```

**Triggers:**
1. Periodic interval check (default 6 h, configurable via `ota.check_interval_s`)
2. MQTT message to `<topic_prefix>/cmd/ota` (any payload)

**TLS:** loads `/ca.crt` from LittleFS; falls back to `setInsecure()` with a warning if absent.

**config.json keys:**
```json
"ota": {
  "manifest_url":     "https://example.com/firmware.json",
  "check_interval_s": 21600
}
```

---

## MQTT Subscriptions

`MQTTClient::subscribe(topic, callback)` stores subscriptions and re-applies them automatically on reconnect. Callbacks are dispatched by exact topic match in `onMessage()`.

Built-in subscriptions registered at boot:

| Topic | Handler |
|---|---|
| `<prefix>/cmd/ota` | Trigger OTA manifest check |
| `<prefix>/cmd/lua/reload` | Hot-reload Lua scripts |

Modules and Lua scripts can add further subscriptions via `MQTTClient::subscribe()` or `MQTT.publish()` / `EventBus.subscribe()`.

---

## Temperature Alerts (TelegramModule)

The `TelegramModule` subscribes to `temperature` events and fires alerts when readings cross configured thresholds. Alerts are sent via:
1. **MQTT** — published to `<topic_prefix>/alert` as `{ "value": "..." }`
2. **HTTP webhook** — optional POST to `webhook.url` with configurable message template
3. **Home Assistant** — subscribes to the MQTT alert topic and forwards to Telegram

Alert config in `config.json`:

```json
"telegram": {
  "alerts": [
    { "enabled": true,  "name": "overheat", "temp_high_c": 40.0 },
    { "enabled": true,  "name": "freeze",   "temp_low_c":  2.0  },
    { "enabled": false, "name": "custom",   "temp_high_c": 60.0, "temp_low_c": -5.0 }
  ]
}
```

- Each rule has an independent enable toggle
- `temp_high_c` fires when **any** sensor exceeds the threshold
- `temp_low_c` fires when **any** sensor drops below the threshold
- **Hysteresis**: alert fires only on state transition — no repeated messages

Alert state per `ruleName:sensorName`: `0` = normal, `1` = high, `-1` = low.

Message format: `[overheat] barn_supply: 42.10°C — OVERHEAT (>= 40.0°C)`

---

## Webhook

Optional HTTP POST fired on every alert:

```json
"webhook": {
  "url":              "http://homeassistant.local:8123/api/webhook/thesada-alert",
  "message_template": "{{value}}"
}
```

`{{value}}` is replaced with the full alert message. Supports `http://` and `https://` (`setInsecure()`). Leave `url` empty to disable.

**Home Assistant automation for MQTT alerts:**

```yaml
automation:
  - alias: "Thesada Node Alert → Telegram"
    trigger:
      - platform: mqtt
        topic: thesada/node/alert
    action:
      - service: notify.telegram
        data:
          message: "{{ trigger.payload_json.value }}"
```

---

## Connectivity

### WiFi path (normal)
- Multi-SSID: configure a list of networks; ranked by RSSI at scan time
- NTP synced on connect (`pool.ntp.org` by default, configurable)
- PubSubClient MQTT over TLS (port 8883)
- Optional minimum send interval: `mqtt.send_interval_s`
- Optional static IP: `wifi.static_ip` / `gateway` / `subnet` / `dns`

### Cellular fallback (LTE-M/NB-IoT)
- Activates when all WiFi networks fail
- SIM7080G modem-native MQTT over TLS via AT+SM* commands
- Periodic WiFi recheck every 15 min (configurable); reverts to WiFi when available

### CA certificate
No certificate is compiled in. Place your CA cert PEM as `data/ca.crt` and upload to LittleFS (`pio run --target uploadfs`). Both WiFi MQTT and the cellular modem load it at boot. If absent, TLS connects without certificate verification and a warning is logged.

### AsyncTCP (vendored)
AsyncTCP v3.3.2 is vendored in `lib/AsyncTCP/` with null-pointer guards added to `_accept`, `_s_accept`, and `_s_accepted`. These prevent `LoadProhibited` crashes (EXCVADDR 0x00000030) when lwIP calls TCP callbacks with a null PCB or freed server pointer.

---

## Compile-time config (`config.h`)

```cpp
#define FIRMWARE_VERSION "1.0.9"

// Enable/disable modules
#define ENABLE_TEMPERATURE
#define ENABLE_ADS1115
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
  "device":   { "name": "thesada-node", "friendly_name": "Thesada Node" },
  "web":      { "user": "admin", "password": "changeme" },
  "wifi":     { "networks": [...], "timeout_per_ssid_s": 10, "wifi_check_interval_s": 900 },
  "ntp":      { "server": "pool.ntp.org", "tz_offset_s": 3600 },
  "mqtt":     { "broker": "...", "port": 8883, "user": "...", "password": "...",
                "topic_prefix": "thesada/node", "send_interval_s": 0 },
  "ota":      { "manifest_url": "", "check_interval_s": 21600 },
  "lua":      { "reload_topic": "" },
  "temperature": { "pin": 45, "interval_s": 60, "auto_discover": true, "sensors": [] },
  "ads1115":  { "i2c_sda": 1, "i2c_scl": 2, "address": 72, "interval_s": 60, "channels": [...] },
  "cellular": { "apn": "OSC", "sim_pin": "", "rf_settle_ms": 15000, "reg_timeout_ms": 180000 },
  "sd":       { "enabled": true, "pin_clk": 38, "pin_cmd": 39, "pin_data": 40 },
  "telegram": { "alerts": [ { "enabled": true, "name": "overheat", "temp_high_c": 40.0 } ] },
  "webhook":  { "url": "", "message_template": "{{value}}" }
}
```

---

## Web Interface

Accessible at `http://[device-ip]/` — requires login (credentials from `web` config).

| Route | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | public | Live sensor dashboard |
| `/api/info` | GET | public | Firmware version, build date, device name |
| `/api/state` | GET | public | Current sensor readings as JSON |
| `/api/config` | GET | yes | Read `config.json` |
| `/api/config` | POST | yes | Write `config.json`, restart device |
| `/api/backup` | POST | yes | Copy `config.json` to SD card |
| `/api/restart` | POST | yes | Reboot device |
| `/ota` | POST | yes | Upload firmware `.bin` (push OTA) |
| `/ws/serial` | WS | public | Bidirectional terminal — log stream + all Shell commands |

**WebSocket / serial terminal commands:** all Shell built-ins (see Shell section above). Type `help` for the full list.

---

## SD Card Logging

Logs sensor events as CSV to `/log001.csv`, `/log002.csv`, ... (new file each boot).

CSV format: `timestamp,sensor,json_data`

Timestamp is ISO 8601 UTC (`2025-03-21T14:32:00Z`) when NTP is synced; falls back to `ms/<millis>` before sync.

Disable via `"sd": { "enabled": false }` in config.json.
Config backup via `/api/backup` copies `config.json` to `/config_backup.json` on SD.

---

## Logging

All `Log::info/warn/error` calls write to:
1. **Serial** (USB CDC, 115200 baud)
2. **WebSocket** `/ws/serial` — all connected terminal clients receive each log line

Format: `[INF][TAG] message` / `[WRN][TAG] message` / `[ERR][TAG] message`

---

## Adding a New Module

1. Create `src/modules/newmodule/NewModule.h` and `NewModule.cpp`
2. Inherit from `Module`, implement `begin()`, `loop()`, `name()`
3. Use `EventBus::publish()` to emit data, `EventBus::subscribe()` to react
4. Add `#define ENABLE_NEWMODULE` to `config.h`
5. Add config block to `data/config.json` if needed
6. Add one `#ifdef ENABLE_NEWMODULE` block to `ModuleRegistry.cpp`

No other files touched.

---

## Dependencies

| Library | Purpose |
|---|---|
| Arduino framework (ESP32) | Base framework |
| ArduinoJson v7 | JSON config + event payloads |
| LittleFS | Filesystem (config, CA cert, Lua scripts) |
| PubSubClient | WiFi MQTT client |
| ESPAsyncWebServer + AsyncTCP | Web server + WebSocket |
| ESP-Arduino-Lua | Lua 5.3 runtime (GPL-3.0) |
| TinyGSM | AT command modem driver |
| XPowersLib | AXP2101 PMU control |
| DallasTemperature + OneWire | DS18B20 sensors |
| Adafruit ADS1X15 | ADS1115 ADC |
| HTTPClient + WiFiClientSecure | OTA manifest fetch + TLS |
| mbedtls (built-in) | SHA256 verification for OTA |
