---
title: temperature-mqtt
parent: Examples
nav_order: 1
description: "Starter sensor module: one DS18B20 read on a timer, published as a bare value on MQTT and as JSON on the event bus."
---

# temperature-mqtt

The smallest sensor module in the tree. One DS18B20 probe on a 1-Wire pin, read every interval, published two ways. `lib/thesada-mod-example-temperature-mqtt/` on the firmware `dev` branch; ships with the next release.

## What it demonstrates

| Thing | Where in the code |
|---|---|
| Config in `begin()`, nothing in the constructor | `begin()` reads `pin`, `interval_s`, `name` and allocates the bus driver there |
| The periodic `loop()` shape | compare `millis()` against the interval, return early, work when due. Two phases: the conversion is requested in one pass and read 800 ms later, so `loop()` never blocks |
| Two publish paths | a bare number on `<prefix>/sensor/temperature/<name>` for dashboards, a JSON event named `temperature` on the bus for Lua rules and the SD logger |
| `module.status` | one line: `name=<n> last_c=<c>` |
| Registration | `MODULE_REGISTER(ExampleTemperatureMqtt, PRIORITY_SENSOR)`, guarded by `ENABLE_EXAMPLE_TEMPERATURE_MQTT` so an unbuilt example costs nothing |

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-temperature-mqtt/src/ExampleTemperatureMqtt.cpp match="sensor/temperature/%s" -->
<!-- claim: repo=thesada-fw file=lib/thesada-mod-temperature/src/TemperatureModule.cpp match="obj\[\"address\"\]" -->
The event payload is a subset of what the full temperature module publishes: `sensors[]` with `name`, `temp_c` and `temp`, without the `address` the full module adds. A rule that reads those three fields works against either.

## Config

```json
"example_temperature_mqtt": {
  "enabled":    true,
  "pin":        12,
  "interval_s": 60,
  "name":       "example"
}
```

`name` becomes the last topic segment. `enabled` is required: optional modules default off.

## Turn it on

In `src/thesada_config.h`, uncomment the define under Example modules, then build and flash as for any module ([tutorial, step 7]({{ site.baseurl }}/tutorials/first-module.html#7-build-flash-watch)). Boot log:

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Module.h match="PRIORITY_SENSOR   = 50" -->
```text
[INF][Registry] registry.module_init priority=50 name=ExampleTemperatureMqtt
[INF][ExTemp] example_temp.ready pin=12 interval_s=60 name=example
```

If the probe is missing, `example_temp.sensor_disconnected` is logged each interval and nothing publishes.

## Expected output

```bash
mosquitto_sub -t 'thesada/+/sensor/temperature/example' -v
```

```text
thesada/sht31/sensor/temperature/example 21.37
```

## The code

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-temperature-mqtt/src/ExampleTemperatureMqtt.cpp match="MODULE_REGISTER\(ExampleTemperatureMqtt, PRIORITY_SENSOR\)" -->
`src/ExampleTemperatureMqtt.h`:

```cpp
// thesada-fw - ExampleTemperatureMqtt.h
// Starter module: read one DS18B20 and publish it. The sensor module shape in
// its smallest form - config in begin(), a timer in loop(), one publish path.
// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <Arduino.h>
#include <Module.h>

class OneWire;
class DallasTemperature;

class ExampleTemperatureMqtt : public Module {
public:
  void begin() override;
  void loop() override;
  const char* name() override { return "ExampleTemperatureMqtt"; }
  const char* configKey() override { return "example_temperature_mqtt"; }
  void status(ShellOutput out) override;

private:
  void readAndPublish();

  OneWire*           _wire    = nullptr;
  DallasTemperature* _sensors = nullptr;
  // 12-bit DS18B20 conversion takes up to 750 ms; wait a little longer.
  static constexpr uint32_t kConversionMs = 800;

  uint32_t           _intervalMs  = 60000;
  uint32_t           _lastRead    = 0;
  uint32_t           _requestedAt = 0;   // 0 = no conversion in flight
  float              _lastC      = 0.0f;   // set to the driver sentinel in begin()
  char               _name[32]   = "example";
};
```

`src/ExampleTemperatureMqtt.cpp`:

```cpp
// thesada-fw - ExampleTemperatureMqtt.cpp
// SPDX-License-Identifier: GPL-3.0-only
#include <thesada_config.h>
#include "ExampleTemperatureMqtt.h"
#include <Config.h>
#include <EventBus.h>
#include <MQTTClient.h>
#include <Log.h>
#include <ModuleRegistry.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <string.h>

#ifdef ENABLE_EXAMPLE_TEMPERATURE_MQTT

static const char* TAG = "ExTemp";

// Everything with a side effect lives here, never in the constructor: the
// registry constructs every module at static-init time, before Config exists.
// in: config block example_temperature_mqtt (pin, interval_s, name).
// out: bus + driver allocated, first read on the next loop() after interval.
void ExampleTemperatureMqtt::begin() {
  JsonObject cfg = Config::get();
  int pin     = cfg["example_temperature_mqtt"]["pin"]        | 12;
  _intervalMs = (uint32_t)(cfg["example_temperature_mqtt"]["interval_s"] | 60) * 1000;
  strlcpy(_name, cfg["example_temperature_mqtt"]["name"] | "example", sizeof(_name));
  _lastC = DEVICE_DISCONNECTED_C;

  _wire    = new OneWire(pin);
  _sensors = new DallasTemperature(_wire);
  _sensors->begin();
  // Never block loop(): request the conversion, come back for the result.
  _sensors->setWaitForConversion(false);

  Log::kvf(TAG, "example_temp.ready pin=%d interval_s=%lu name=%s",
           pin, (unsigned long)(_intervalMs / 1000), _name);
}

// loop() runs every main-loop pass, so it must not block. Two phases per
// interval: kick the conversion, then read it once the probe has had its
// conversion time. The timer is the whole scheduler.
// in: none. out: one readAndPublish() per interval, ~800 ms after the request.
void ExampleTemperatureMqtt::loop() {
  uint32_t now = millis();
  if (_requestedAt != 0) {
    if (now - _requestedAt < kConversionMs) return;
    _requestedAt = 0;
    readAndPublish();
    return;
  }
  if (now - _lastRead < _intervalMs) return;
  _lastRead = now;
  _sensors->requestTemperatures();
  _requestedAt = now ? now : 1;
}

// Read the first probe on the bus and publish it on MQTT and the event bus.
// in: none. out: <prefix>/sensor/temperature/<name> + EventBus "temperature".
void ExampleTemperatureMqtt::readAndPublish() {
  float c = _sensors->getTempCByIndex(0);
  if (c == DEVICE_DISCONNECTED_C) {
    Log::kvfw(TAG, "example_temp.sensor_disconnected");
    return;
  }
  _lastC = roundf(c * 100.0f) / 100.0f;

  // Two outputs, same as the full temperature module: a plain value on a
  // per-sensor topic for Home Assistant, and a JSON event on the bus so Lua
  // rules and the SD logger see it without knowing about MQTT.
  JsonObject  cfg    = Config::get();
  const char* prefix = cfg["mqtt"]["topic_prefix"] | "thesada/node";
  char topic[96];
  int n = snprintf(topic, sizeof(topic), "%s/sensor/temperature/%s", prefix, _name);
  if (n < 0 || n >= (int)sizeof(topic)) {
    Log::kvfw(TAG, "example_temp.topic_too_long prefix_len=%u", (unsigned)strlen(prefix));
    return;
  }
  char val[16];
  snprintf(val, sizeof(val), "%.2f", _lastC);
  MQTTClient::publish(topic, val);

  JsonDocument doc;
  JsonObject s = doc["sensors"].add<JsonObject>();
  s["name"]   = _name;
  s["temp_c"] = _lastC;
  s["temp"]   = _lastC;
  EventBus::publish("temperature", doc.as<JsonObject>());
}

// One line for `module.status`.
// in: out sink. out: "name=<n> last_c=<c>".
void ExampleTemperatureMqtt::status(ShellOutput out) {
  char line[64];
  snprintf(line, sizeof(line), "name=%s last_c=%.2f", _name, _lastC);
  out(line);
}

MODULE_REGISTER(ExampleTemperatureMqtt, PRIORITY_SENSOR)

#endif  // ENABLE_EXAMPLE_TEMPERATURE_MQTT
```
