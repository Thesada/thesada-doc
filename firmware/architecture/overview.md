---
title: Overview
parent: Architecture
grand_parent: Firmware
nav_order: 1
description: "Design principles, repository structure, boot sequence, module base class, and EventBus pub/sub system."
---

# Overview

## Design Principles

- **Modular** - each sensor or peripheral is a self-contained module
- **Config-driven** - compile-time enables via `config.h`, runtime values via `config.json` on LittleFS
- **Event-driven** - modules communicate via an internal Event Bus, not direct calls
- **Pluggable** - adding a new module requires creating one folder and one line in `config.h`
- **Resilient** - automatic WiFi to cellular fallback; MQTT queue survives short disconnects
- **Scriptable** - Lua 5.3 runtime with hot-reloadable rules; no recompile needed for logic changes

---

## Repository Structure

```
thesada-fw/base/
├── platformio.ini                  <- build targets + library deps
├── config.h                        <- compile-time module enables + version
├── scripts/
│   ├── generate_manifest.py        <- post-build: build/firmware.json with SHA256 + version
│   └── copy_firmware.py            <- post-build: copies .bin to build/
├── tests/
│   └── test_firmware.py            <- automated + manual test suite (pyserial)
├── lib/
│   └── AsyncTCP/                   <- vendored AsyncTCP v3.3.2 (null-PCB crash fixes)
├── data/
│   ├── config.json                 <- runtime config (LittleFS)
│   ├── config.json.example         <- template with all fields documented
│   ├── ca.crt                      <- TLS CA cert (required for cert verification)
│   └── scripts/
│       ├── main.lua                <- Lua boot script (runs once at startup)
│       └── rules.lua               <- Lua event rules (hot-reloadable)
└── src/
    ├── main.cpp
    ├── core/
    │   ├── Module.h                <- base class for all modules
    │   ├── ModuleRegistry.h/.cpp   <- instantiates + drives all modules
    │   ├── EventBus.h/.cpp         <- pub/sub between modules
    │   ├── Config.h/.cpp           <- config.json loader (LittleFS)
    │   ├── Log.h/.cpp              <- serial + WebSocket log relay
    │   ├── WiFiManager.h/.cpp      <- multi-SSID, RSSI-ranked, NTP sync
    │   ├── MQTTClient.h/.cpp       <- TLS MQTT, publish queue, subscription dispatch
    │   ├── OTAUpdate.h/.cpp        <- HTTP(S) pull OTA with SHA256 verify
    │   ├── Shell.h/.cpp            <- unified CLI (serial + WebSocket share same handlers)
    │   ├── ScriptEngine.h/.cpp     <- Lua 5.3 runtime with EventBus + MQTT bindings
    │   ├── Cellular.h/.cpp         <- SIM7080G modem-native MQTT over TLS
    │   ├── PowerManager.h/.cpp     <- AXP2101 PMU init, battery getters, heartbeat LED
    │   ├── WebServer.h/.cpp        <- dashboard, config editor, file browser, terminal
    │   ├── dashboard.html.h        <- PROGMEM HTML for the web dashboard
    │   └── SleepManager.h/.cpp     <- deep sleep orchestrator (RTC memory, graceful shutdown)
    └── modules/
        ├── temperature/            <- DS18B20 one-wire sensors
        ├── ads1115/                <- ADS1115 differential current sensing
        ├── battery/                <- AXP2101 battery monitoring (voltage, percent, charging)
        ├── cellular/               <- cellular module (alert routing via LTE)
        ├── sd/                     <- SD card CSV logger
        ├── telegram/               <- temperature + battery threshold alerts + webhook
        └── pwm/                    <- PWM output
```

---

## Boot Sequence

```
setup()
  Config::load()          -> mounts LittleFS, parses config.json
  WiFiManager::begin()    -> scans, ranks by RSSI, connects, starts NTP
  if WiFi ok:
    MQTTClient::begin()   -> TLS MQTT to broker; registers cmd/ota subscription
    OTAUpdate::begin()    -> registers MQTT cmd/ota handler, optional periodic check
  else:
    Cellular::begin()     -> PMU, modem, SIM, network, modem-MQTT
  WebServer::begin()      -> HTTP dashboard + WebSocket terminal
  PowerManager::begin()   -> AXP2101 init (VBUS limits, TS pin, battery ADC, charger enable), LED mode
  Shell::begin()          -> registers all built-in commands
  ScriptEngine::begin()   -> Lua state, executes main.lua + rules.lua
                            registers MQTT cmd/lua/reload handler
  ModuleRegistry::begin() -> begin() on all enabled modules
  SleepManager::begin()   -> reads sleep config, sets wake deadline, inits RTC data

loop()
  Serial shell            -> reads characters, executes line on newline via Shell::execute()
  WiFiManager::loop()     -> reconnect / recheck
  MQTTClient::loop() or Cellular::loop()
  OTAUpdate::loop()       -> periodic interval check (WiFi only)
  WebServer::loop()       -> handle deferred restarts
  ModuleRegistry::loop()  -> loop() on all enabled modules
  SleepManager::loop()    -> checks wake deadline, triggers graceful shutdown + deep sleep
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

Modules never call each other directly. They publish events with a JSON payload and subscribe to events from other modules. The Event Bus is synchronous - subscribers run inline when `publish()` is called.

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
| `battery` | BatteryModule | `{ "present": true, "voltage_v": 3.91, "percent": 35, "charging": false }` |
| `alert` | TelegramModule | `{ "value": "alert message text" }` (MQTTClient and CellularModule subscribe) |
