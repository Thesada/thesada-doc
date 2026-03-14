---
title: Architecture
parent: Firmware
nav_order: 1
---

# Firmware Architecture

`thesada-fw` is built on C++17 with the Arduino framework, compiled via PlatformIO. It uses a **Module Registry** pattern with a lightweight **Event Bus** for inter-module communication, and an embedded **Lua scripting engine** for rules and automation logic.

---

## Design Principles

- **Modular** — each sensor or peripheral is a self-contained module
- **Config-driven** — compile-time enables via `config.h`, runtime values via `config.json` on LittleFS
- **Event-driven** — modules communicate via an internal Event Bus, not direct calls
- **Pluggable** — adding a new module requires creating one folder and one line in `config.h`
- **Scriptable** — Lua scripts on LittleFS handle rules and automation logic without recompiling

---

## Naming Conventions

Standard C++ conventions used throughout `thesada-fw`:

| Thing | Convention | Example |
|---|---|---|
| Classes | PascalCase | `ModuleRegistry`, `EventBus` |
| Methods | camelCase | `begin()`, `addModule()` |
| Variables | camelCase | `mqttBroker`, `sensorValue` |
| Constants / `#define` | UPPER_SNAKE_CASE | `ENABLE_TEMPERATURE`, `MAX_MODULES` |
| Files | Match class name | `ModuleRegistry.h` / `ModuleRegistry.cpp` |
| Namespaces | lowercase | `thesada::core` |

---

## Repository Structure

```
thesada-fw/
├── platformio.ini                  ← build targets
├── config.h                        ← compile-time module enables
├── data/
│   ├── config.json                 ← runtime values (LittleFS)
│   └── scripts/
│       ├── main.lua                ← runs on boot
│       ├── rules.lua               ← event-driven rules
│       └── [custom].lua
└── src/
    ├── main.cpp
    ├── core/
    │   ├── Module.h                ← base class
    │   ├── ModuleRegistry.h/.cpp   ← holds + calls all modules
    │   ├── EventBus.h/.cpp         ← pub/sub
    │   ├── Config.h/.cpp           ← config.json loader
    │   ├── WiFiManager.h/.cpp
    │   ├── MQTTClient.h/.cpp       ← TLS MQTT port 8883
    │   ├── Cellular.h/.cpp         ← SIM7080G fallback
    │   ├── WebServer.h/.cpp        ← OTA + editors (baked in)
    │   └── ScriptEngine.h/.cpp     ← Lua runtime + bindings
    └── modules/
        ├── temperature/
        ├── current/
        ├── pwm/
        └── cellular/
```

---

## Module Base Class

Every module inherits from `Module`. The `ModuleRegistry` calls `begin()` once at boot and `loop()` every cycle.

```cpp
// core/Module.h
class Module {
public:
  virtual void begin() = 0;
  virtual void loop() = 0;
  virtual const char* name() = 0;
  virtual ~Module() {}
};
```

---

## Module Registry

`main.cpp` calls `ModuleRegistry::begin()` and `ModuleRegistry::loop()` — it has no knowledge of individual modules. The registry reads `config.h` defines at compile time to know which modules to instantiate.

---

## Event Bus

Modules never call each other directly. They publish events with a JSON payload and subscribe to events from other modules.

```cpp
// Publish a temperature reading
StaticJsonDocument<64> doc;
doc["value"] = 74.3;
doc["sensor"] = "house_supply";
EventBus::publish("temperature", doc.as<JsonObject>());

// Subscribe (e.g. in PWMModule)
EventBus::subscribe("temperature", [](JsonObject data) {
  float temp = data["value"];
  if (temp > 70) PWM::setLevel(1.0);
});
```

---

## Config

**Compile-time (`config.h`)** — enables modules and sets constants:

```cpp
#define ENABLE_TEMPERATURE
// #define ENABLE_PWM
#define MQTT_PORT 8883
#define MQTT_TLS  true
```

**Runtime (`data/config.json`)** — loaded from LittleFS at boot:

```json
{
  "device": { "name": "thesada-owb" },
  "mqtt": {
    "broker": "mqtt.thesada.cloud",
    "port": 8883
  },
  "temperature": {
    "interval_s": 60,
    "alert_low_c": 40.0
  }
}
```

---

## Scripting (Lua)

Scripts live in `data/scripts/` on LittleFS. They are loaded at boot and can be hot-reloaded via MQTT command or web UI without reflashing.

Available bindings:

```lua
EventBus.subscribe("event", function(data) end)
EventBus.publish("event", { key = value })
MQTT.publish("topic", "payload")
Log.info("message")
Config.get("temperature.alert_low_c")
```

Example `rules.lua`:

```lua
EventBus.subscribe("temperature", function(data)
  if data.sensor == "house_supply" and data.value < 40 then
    MQTT.publish("thesada/owb/alert", "Supply temp low: " .. data.value .. "C")
  end
end)
```

---

## Web Server

Always enabled. Accessible at `http://[device-ip]/` on the local network.

| Path | Description |
|---|---|
| `/` | Live sensor dashboard |
| `/config` | Edit `config.json` in browser |
| `/scripts` | Edit `.lua` scripts in browser |
| `/ota` | OTA firmware update |
| `/api/state` | JSON sensor state endpoint |
| `/api/log` | Live log stream |

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

| Library | Licence | Purpose |
|---|---|---|
| Arduino framework (ESP32) | LGPL 2.1 | Base framework |
| ESP-IDF | Apache 2.0 | Low-level ESP32 |
| ArduinoJSON | MIT | JSON config + event payloads |
| LittleFS | BSD 3-Clause | Filesystem |
| Lua 5.4 | MIT | Scripting engine |
| PubSubClient or AsyncMQTT | MIT | MQTT client |
| ESPAsyncWebServer | LGPL 2.1 | Web server |

All dependencies are compatible with GPL 3.0.
