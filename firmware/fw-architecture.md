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

---

## Repository Structure

```
thesada-fw/base/
├── platformio.ini                  ← build targets + library deps
├── config.h                        ← compile-time module enables + TLS flag
├── TODO.md                         ← project task list
├── scripts/
│   └── copy_firmware.py            ← post-build: copies .bin to build/
├── lib/
│   └── AsyncTCP/                   ← vendored AsyncTCP v3.3.2 (null-PCB crash fixes)
├── data/
│   ├── config.json                 ← runtime config (LittleFS)
│   ├── config.json.example         ← template with all fields documented
│   └── ca.crt                      ← TLS CA cert (required for cert verification)
└── src/
    ├── main.cpp
    ├── core/
    │   ├── Module.h                ← base class for all modules
    │   ├── ModuleRegistry.h/.cpp   ← instantiates + drives all modules
    │   ├── EventBus.h/.cpp         ← pub/sub between modules
    │   ├── Config.h/.cpp           ← config.json loader (LittleFS)
    │   ├── Log.h/.cpp              ← serial + WebSocket log relay
    │   ├── WiFiManager.h/.cpp      ← multi-SSID, RSSI-ranked, NTP sync
    │   ├── MQTTClient.h/.cpp       ← TLS MQTT, publish queue, backoff
    │   ├── Cellular.h/.cpp         ← SIM7080G modem-native MQTT over TLS
    │   ├── WebServer.h/.cpp        ← dashboard, config editor, OTA, terminal
    │   └── ScriptEngine.h/.cpp     ← Lua runtime stub (future)
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
    MQTTClient::begin()   → TLS MQTT to broker
  else:
    Cellular::begin()     → PMU, modem, SIM, network, modem-MQTT
  WebServer::begin()      → HTTP dashboard + WebSocket terminal
  ModuleRegistry::begin() → begin() on all enabled modules

loop()
  WiFiManager::loop()     → reconnect / recheck
  MQTTClient::loop() or Cellular::loop()
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
| `current` | ADS1115Module | `{ "channels": [ { "name": "x", "voltage_v": 0.012 } ] }` |
| `alert` | TelegramModule | `{ "value": "alert message text" }` |

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
- A single rule can have both — it fires the relevant one
- **Hysteresis**: alert fires only on state transition (high → normal, normal → high, etc.) — no repeated messages

Alert state machine per `ruleName:sensorName`:
- `0` = normal
- `1` = high (overheat active)
- `-1` = low (freeze active)

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

`{{value}}` is replaced with the full alert message. Supports `http://` and `https://` (self-signed certs accepted via `setInsecure()`). Leave `url` empty to disable.

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
- Optional minimum send interval: `mqtt.send_interval_s` — messages within the window are queued, not dropped
- Optional static IP: `wifi.static_ip` / `gateway` / `subnet` / `dns`

### Cellular fallback (LTE-M/NB-IoT)
- Activates when all WiFi networks fail
- SIM7080G modem-native MQTT over TLS via AT+SM* commands
- Periodic WiFi recheck every 15 min (configurable); reverts to WiFi when available
- `Cellular::begin()` is guarded — calling it again after init is a no-op

### CA certificate
No certificate is compiled in. Place your CA cert PEM as `data/ca.crt` and upload to LittleFS (`pio run --target uploadfs`). Both WiFi MQTT and the cellular modem load it at boot. If absent, TLS connects without certificate verification and a warning is logged.

### AsyncTCP (vendored)
AsyncTCP v3.3.2 is vendored in `lib/AsyncTCP/` with null-pointer guards added to `_accept`, `_s_accept`, and `_s_accepted`. These prevent `LoadProhibited` crashes (EXCVADDR 0x00000030) when lwIP calls TCP callbacks with a null PCB or freed server pointer. The upstream patch script (`scripts/patch_asynctcp.py`) has been removed — the fix is now permanent in the vendored source.

---

## compile-time config (`config.h`)

```cpp
#define FIRMWARE_VERSION "1.0.7"

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
  "mqtt":     { "broker": "...", "port": 8883, "user": "...", "password": "...", "topic_prefix": "thesada/node" },
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
| `/` | GET | yes | Live sensor dashboard |
| `/api/info` | GET | no | Firmware version, build date, device name |
| `/api/state` | GET | yes | Current sensor readings as JSON |
| `/api/config` | GET | yes | Read `config.json` |
| `/api/config` | POST | yes | Write `config.json`, restart device |
| `/api/backup` | POST | yes | Copy `config.json` to SD card |
| `/api/restart` | POST | yes | Reboot device |
| `/ota` | POST | yes | Upload firmware `.bin` |
| `/ws/serial` | WS | no | Bidirectional serial terminal (log stream + commands) |

**WebSocket terminal commands:** `restart`, `sensors`

---

## SD Card Logging

Logs sensor events as CSV to `/log001.csv`, `/log002.csv`, … (new file each boot).

CSV format: `timestamp,sensor,json_data`

Timestamp is ISO 8601 UTC (`2025-03-21T14:32:00Z`) when NTP is synced; falls back to `ms/<millis>` before sync.

Disable via `"sd": { "enabled": false }` in config.json.

Config backup via `/api/backup` copies `config.json` to `/config_backup.json` on the SD card.

---

## Logging

All `Log::info/warn/error` calls write to:
1. **Serial** (USB CDC, 115200 baud)
2. **WebSocket** `/ws/serial` — all connected terminal clients receive each log line

Serial commands (typed in any serial terminal or web terminal): `restart`

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
| LittleFS | Filesystem (config, CA cert) |
| PubSubClient | WiFi MQTT client |
| ESPAsyncWebServer + AsyncTCP | Web server + WebSocket |
| TinyGSM | AT command modem driver |
| XPowersLib | AXP2101 PMU control |
| DallasTemperature + OneWire | DS18B20 sensors |
| Adafruit ADS1X15 | ADS1115 ADC |
