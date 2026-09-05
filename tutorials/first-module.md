---
title: Build your first module
parent: Tutorials
nav_order: 1
description: "Write a soil-moisture module from scratch: register it, read config, publish on the event bus and MQTT, then react to it from Lua without a reflash."
---

# Build your first module

A module is the unit of work in this firmware. Every sensor, radio and output in the tree is one, and the ones you leave off cost nothing in the binary. This page takes you from an empty directory to a soil-moisture reading on your MQTT broker and a Lua rule that reacts to it. About an hour, most of it reading.

You need a flashed `esp32-s3-debug` board from [Getting started]({{ site.baseurl }}/getting-started.html), a capacitive soil-moisture probe (any 3.3 V analog one), and the probe's signal wire on an ADC1 pin. GPIO 4 is the default below.

## 1. What a module is

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Module.h match="virtual void begin\(\) = 0" -->
A module is a class with three required methods and four optional ones:

```cpp
class Module {
public:
  virtual void begin() = 0;                       // hardware and config setup
  virtual void loop()  = 0;                       // called every main-loop pass
  virtual const char* name() = 0;                 // for logs and module.list
  virtual void status(ShellOutput out) { out("ok"); }  // one line for module.status
  virtual void selftest(ShellOutput out) {}       // hook for the selftest command
  virtual const char* configKey() { return name(); }  // the config.json subtree
  virtual bool coreModule() { return false; }     // true: on unless disabled
};
```

Two things decide whether your module is in a build and whether it runs:

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ModuleRegistry.cpp match="\[\"enabled\"\] \| m->coreModule\(\)" -->
| Gate | Where | What it does |
|---|---|---|
| `ENABLE_<NAME>` | `src/thesada_config.h`, compile time | leaves the module out of the binary entirely when unset |
| `"enabled": true` | your block in `config.json`, runtime | the registry skips a module whose block lacks it; only core modules default on |

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Module.h match="Constructor must be trivial" -->
The constructor must stay empty. The registry builds every module before `Config` has loaded, so anything with a side effect goes in `begin()`.

## 2. Pick a problem

Read a capacitive soil probe and publish moisture as a percent. It is analog, so no driver library, and the interesting part is the same as for every sensor: a calibrated read on a timer, published in two shapes.

## 3. The skeleton

Create `lib/thesada-mod-soil/` with three files. `library.json` is what makes PlatformIO see the directory as a library:

```json
{"name":"thesada-mod-soil","version":"0.1.0","build":{"libCompatMode":"off"}}
```

`src/SoilModule.h`:

```cpp
// thesada-fw - SoilModule.h
// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <Arduino.h>
#include <Module.h>

class SoilModule : public Module {
public:
  void begin() override;
  void loop() override;
  const char* name() override { return "SoilModule"; }
  const char* configKey() override { return "soil"; }
  void status(ShellOutput out) override;

private:
  void readAndPublish();

  int      _pin        = 4;
  int      _dry        = 3000;
  int      _wet        = 1200;
  uint32_t _intervalMs = 60000;
  uint32_t _lastRead   = 0;
  int      _percent    = -1;
  char     _name[32]   = "bed1";
};
```

`src/SoilModule.cpp`, all of it:

```cpp
// thesada-fw - SoilModule.cpp
// SPDX-License-Identifier: GPL-3.0-only
#include <thesada_config.h>
#include "SoilModule.h"
#include <Config.h>
#include <EventBus.h>
#include <MQTTClient.h>
#include <Log.h>
#include <SensorRegistry.h>
#include <ModuleRegistry.h>
#include <ArduinoJson.h>

#ifdef ENABLE_SOIL

static const char* TAG = "Soil";

// Read the config block, register under `sensors`. No hardware work in the
// constructor: the registry builds every module before Config exists.
// in: config block soil (pin, dry, wet, interval_s, name). out: ready to loop.
void SoilModule::begin() {
  JsonObject cfg = Config::get();
  _pin        = cfg["soil"]["pin"]        | 4;
  _dry        = cfg["soil"]["dry"]        | 3000;
  _wet        = cfg["soil"]["wet"]        | 1200;
  _intervalMs = (uint32_t)(cfg["soil"]["interval_s"] | 60) * 1000;
  strlcpy(_name, cfg["soil"]["name"] | "bed1", sizeof(_name));

  SensorRegistry::add("soil", "capacitive soil moisture",
    [](ShellOutput out, void* ctx) {
      SoilModule* m = static_cast<SoilModule*>(ctx);
      char line[48];
      snprintf(line, sizeof(line), "  %s: %d %%", m->_name, m->_percent);
      out(line);
    }, this, true);

  Log::kvf(TAG, "soil.ready pin=%d dry=%d wet=%d interval_s=%lu",
           _pin, _dry, _wet, (unsigned long)(_intervalMs / 1000));
}

// One read per interval, never blocking.
// in: none. out: readAndPublish() when due.
void SoilModule::loop() {
  uint32_t now = millis();
  if (now - _lastRead < _intervalMs) return;
  _lastRead = now;
  readAndPublish();
}

// Raw ADC to percent between the two calibration points, then out both doors.
// in: none. out: <prefix>/sensor/soil/<name> and EventBus "soil".
void SoilModule::readAndPublish() {
  int raw  = analogRead(_pin);
  int span = _dry - _wet;
  _percent = span > 0 ? constrain((_dry - raw) * 100 / span, 0, 100) : 0;

  JsonObject  cfg    = Config::get();
  const char* prefix = cfg["mqtt"]["topic_prefix"] | "thesada/node";
  char topic[96];
  snprintf(topic, sizeof(topic), "%s/sensor/soil/%s", prefix, _name);
  char val[8];
  snprintf(val, sizeof(val), "%d", _percent);
  MQTTClient::publish(topic, val);

  JsonDocument doc;
  doc["name"]    = _name;
  doc["raw"]     = raw;
  doc["percent"] = _percent;
  EventBus::publish("soil", doc.as<JsonObject>());
}

// One line for `module.status`.
// in: out sink. out: "name=<n> percent=<p>".
void SoilModule::status(ShellOutput out) {
  char line[48];
  snprintf(line, sizeof(line), "name=%s percent=%d", _name, _percent);
  out(line);
}

MODULE_REGISTER(SoilModule, PRIORITY_SENSOR)

#endif  // ENABLE_SOIL
```

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ModuleRegistry.h match="define MODULE_REGISTER\(CLASS, PRIO\)" -->
The last line is the registration. `MODULE_REGISTER(Class, Priority)` creates one static instance and adds it to the registry before `setup()` runs, so `main.cpp` never includes a module.

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Module.h match="PRIORITY_SENSOR   = 50" -->
The priority orders `begin()` calls at boot: power (10), network (20), services (30), the Lua engine (40), sensors (50), outputs (60). A sensor wants `PRIORITY_SENSOR`, so the engine that will run rules against its events is already up when it first publishes.

<!-- claim: repo=thesada-fw file=platformio.ini match="LDF can't discover them automatically" -->
Two build-system lines make the module real. In `platformio.ini`, under `lib_deps`, add `thesada-mod-soil` next to the other local modules. In `src/thesada_config.h`, add the compile-time gate next to the sensor modules:

```cpp
#define ENABLE_SOIL          // capacitive soil moisture on an ADC pin
```

Every module lists itself in `lib_deps` because self-registering code is never reached from `main.cpp`, so the library dependency finder cannot discover it.

## 4. The config block

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Config.h match="static JsonObject get\(\)" -->
`Config::get()` returns the whole `config.json` as a JSON object; `cfg["soil"]["pin"] | 4` reads a key with a default. Add the block to `data/config.json`:

```json
"soil": {
  "enabled":    true,
  "pin":        4,
  "dry":        3000,
  "wet":        1200,
  "interval_s": 60,
  "name":       "bed1"
}
```

`dry` and `wet` are the raw ADC readings of the probe in air and in water; measure yours once with `sensors soil` and write them back. The percent is linear between them and clamped.

## 5. The loop hook

`loop()` runs every pass of the main loop alongside every other module, so it must never block. The pattern in the file is the whole scheduler: compare `millis()` against the interval, return early, do the work when it is due. That is the periodic shape. A one-shot module does its work in `begin()`, or on the first `loop()` pass behind a flag, and returns immediately after. An event-driven module skips the timer altogether: an output that reacts to a command registers it with `Shell::registerCommand` in `begin()`, or subscribes on the event bus, and leaves `loop()` empty.

## 6. Publishing

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/EventBus.h match="static void publish\(const std::string& event, JsonObject data\)" -->
The read goes out two doors on purpose. `MQTTClient::publish` puts a bare number on `<prefix>/sensor/soil/bed1`, which is what Home Assistant and a dashboard want. `EventBus::publish("soil", ...)` hands the same reading, as JSON, to anything on the board that subscribed: Lua rules, the SD logger, a display. The module knows nothing about who listens, which is what keeps it at seventy lines.

`SensorRegistry::add` in `begin()` is the third, smaller door: it puts the reading under the `sensors` shell command, so `sensors soil` on serial, HTTP or MQTT prints it without a broker round trip.

## 7. Build, flash, watch

```bash
pio run -e esp32-s3-debug --target upload
pio run -e esp32-s3-debug --target uploadfs
pio device monitor -e esp32-s3-debug
```

Boot logs show the registry pick it up, then the module report in:

```text
[INF][Registry] registry.module_init priority=50 name=SoilModule
[INF][Soil] soil.ready pin=4 dry=3000 wet=1200 interval_s=60
```

From the serial console, `module.list` shows it compiled and enabled, `sensors soil` prints the live percent. On the broker:

```bash
mosquitto_sub -t 'thesada/+/sensor/soil/#' -v
```

If `module.list` shows it but `registry.module_skip ... reason=disabled` is in the log, the config block is missing `"enabled": true`. If it is not listed at all, `ENABLE_SOIL` is not defined for the environment you built.

## 8. React to it from Lua, no reflash

The event-bus door pays off here. This rule alerts when the bed dries out, with the same JSON envelope the platform ingests:

```lua
local prefix = Config.get("mqtt.topic_prefix")

EventBus.subscribe("soil", function(d)
  if d.percent < 20 then
    MQTT.publish(prefix .. "/alert", string.format(
      '{"severity":"warn","code":"soil_dry","message":"%s at %d%%"}',
      d.name, d.percent))
  end
end)
```

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="fs.append" -->
Append it to `/scripts/rules.lua` and reload, all over MQTT. `fs.append` takes the path, a newline, then the content as one raw payload (`fs.write` has the same shape but truncates the file first):

```bash
prefix=thesada/sht31
printf '/scripts/rules.lua\n%s' "$(cat soil-rule.lua)" | mosquitto_pub -t "$prefix/cli/fs.append" -s
mosquitto_pub -t "$prefix/cli/lua.reload" -m ''
```

Pull the probe out of the soil and the alert lands on `<prefix>/alert` within one interval. Iterate on the rule the same way; the firmware never changes again.

## Where next

- The alert rule wants sustain and cooldown before it goes near a phone. [Alerts]({{ site.baseurl }}/firmware/architecture/alerts.html) has the pattern.
- A command of your own for an output module: `Shell::registerCommand` in `begin()`, and the same handler answers on serial, HTTP and MQTT. See [CLI Reference]({{ site.baseurl }}/firmware/cli-reference.html#adding-new-commands).
- Why the framework is shaped like this at all: [Why this way]({{ site.baseurl }}/firmware/architecture/why-this-way.html).
