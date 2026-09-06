---
title: remote-relay
parent: Examples
nav_order: 2
description: "Starter actuator module: a GPIO flipped by relay.set on|off|toggle over serial, HTTP or MQTT, with the state published after every change."
---

# remote-relay

The actuator shape. A GPIO, one shell command that drives it, and a state publish after every change so nothing has to poll. `lib/thesada-mod-example-remote-relay/` on the firmware `dev` branch; ships with the next release.

## What it demonstrates

| Thing | Where in the code |
|---|---|
| An event-driven module | `loop()` is empty; all the work hangs off the command |
| One command, every transport | `Shell::registerCommand("relay.set", ...)` in `begin()`; the same handler answers on the serial console, `POST /api/cmd`, and the MQTT topic `<prefix>/cli/relay.set` (anchored below) |
| The argv convention | `argv[0]` is the command name, so the argument is `argv[1]` |
| Active-low hardware | `active_low` in config flips the pin polarity without touching the logic; the idle level is written before the pin becomes an output so the load never sees a power-on pulse |
| State out both paths | `<prefix>/sensor/relay` carries `{"on":true}`, and the bus event `relay` carries the same |
| Registration | `MODULE_REGISTER(ExampleRemoteRelay, PRIORITY_OUTPUT)`, guarded by `ENABLE_EXAMPLE_REMOTE_RELAY` |

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/cli_topics.h match="CLI_TOPIC_INPUT_SEGMENT" -->
<!-- claim: repo=thesada-fw file=lib/thesada-mod-httpserver/src/HttpServer.cpp match="/api/cmd" -->
A command registered once is dispatched from every transport: the MQTT client strips `<prefix>/cli/` and hands the rest to the shell, and `/api/cmd` does the same with its JSON body.

## Config

```json
"example_remote_relay": {
  "enabled":    true,
  "pin":        4,
  "active_low": false
}
```

The relay is driven off at boot regardless of what it was before, and that first `set(false)` publishes the state like any other change.

## Turn it on

Uncomment `ENABLE_EXAMPLE_REMOTE_RELAY` in `src/thesada_config.h`, build and flash as for any module. Boot log:

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Module.h match="PRIORITY_OUTPUT   = 60" -->
```text
[INF][Registry] registry.module_init priority=60 name=ExampleRemoteRelay
[INF][ExRelay] example_relay.set on=0
[INF][ExRelay] example_relay.ready pin=4 active_low=0
```

## Expected output

Any of the three transports, same result:

```text
relay.set on
on
```

```bash
mosquitto_pub -t 'thesada/sht31/cli/relay.set' -m 'toggle'
mosquitto_sub -t 'thesada/sht31/sensor/relay' -v -C 1
```

```text
thesada/sht31/sensor/relay {"on":false}
```

A bad argument answers `Usage: relay.set on|off|toggle` and changes nothing. Each change logs `example_relay.set on=<0|1>`.

## The code

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-remote-relay/src/ExampleRemoteRelay.cpp match="registerCommand\(\"relay.set\"" -->
`src/ExampleRemoteRelay.h`:

```cpp
// thesada-fw - ExampleRemoteRelay.h
// Starter module: a GPIO that an inbound command flips. The actuator shape -
// no timer, one shell command that is reachable over serial, HTTP and MQTT
// alike, and a state publish after every change.
// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <Arduino.h>
#include <Module.h>

class ExampleRemoteRelay : public Module {
public:
  void begin() override;
  void loop() override {}
  const char* name() override { return "ExampleRemoteRelay"; }
  const char* configKey() override { return "example_remote_relay"; }
  void status(ShellOutput out) override;

private:
  void set(bool on);
  void publishState();

  int  _pin       = 4;
  bool _activeLow = false;
  bool _on        = false;
};
```

`src/ExampleRemoteRelay.cpp`:

```cpp
// thesada-fw - ExampleRemoteRelay.cpp
// SPDX-License-Identifier: GPL-3.0-only
#include <thesada_config.h>
#include "ExampleRemoteRelay.h"
#include <Config.h>
#include <EventBus.h>
#include <MQTTClient.h>
#include <Log.h>
#include <Shell.h>
#include <ModuleRegistry.h>
#include <ArduinoJson.h>
#include <string.h>

#ifdef ENABLE_EXAMPLE_REMOTE_RELAY

static const char* TAG = "ExRelay";

// Configure the pin, drive it off, and register the one command.
// in: config block example_remote_relay (pin, active_low).
// out: `relay.set` registered on the shell.
void ExampleRemoteRelay::begin() {
  JsonObject cfg = Config::get();
  _pin       = cfg["example_remote_relay"]["pin"]        | 4;
  _activeLow = cfg["example_remote_relay"]["active_low"] | false;
  // Idle level first, then output mode: an active-low load would otherwise
  // see the pin's power-on LOW as a pulse until set(false) runs.
  digitalWrite(_pin, _activeLow ? HIGH : LOW);
  pinMode(_pin, OUTPUT);
  set(false);

  // One registration covers every transport. The shell dispatches
  // `relay.set` whether it arrived on the serial console, POST /api/cmd, or
  // the MQTT topic <prefix>/cli/relay.set - the module never sees which.
  // argv[0] is the command name, so the first argument is argv[1].
  Shell::registerCommand("relay.set", "on|off|toggle - drive the example relay",
    [this](int argc, char** argv, ShellOutput out) {
      const char* arg = (argc > 1) ? argv[1] : "";
      if      (strcmp(arg, "on") == 0)     set(true);
      else if (strcmp(arg, "off") == 0)    set(false);
      else if (strcmp(arg, "toggle") == 0) set(!_on);
      else { out("Usage: relay.set on|off|toggle"); return; }
      out(_on ? "on" : "off");
    });

  Log::kvf(TAG, "example_relay.ready pin=%d active_low=%d", _pin, (int)_activeLow);
}

// Drive the pin and announce the new state.
// in: on. out: GPIO level (honouring active_low), then publishState().
void ExampleRemoteRelay::set(bool on) {
  _on = on;
  digitalWrite(_pin, (on != _activeLow) ? HIGH : LOW);
  Log::kvf(TAG, "example_relay.set on=%d", (int)on);
  publishState();
}

// Publish after every change so a dashboard never has to poll. The event
// carries the same payload for anything on the bus (Lua rules, the display).
// in: none. out: <prefix>/sensor/relay {"on":bool} + EventBus "relay".
void ExampleRemoteRelay::publishState() {
  JsonObject  cfg    = Config::get();
  const char* prefix = cfg["mqtt"]["topic_prefix"] | "thesada/node";
  char topic[96];
  int n = snprintf(topic, sizeof(topic), "%s/sensor/relay", prefix);
  if (n < 0 || n >= (int)sizeof(topic)) {
    Log::kvfw(TAG, "example_relay.topic_too_long prefix_len=%u", (unsigned)strlen(prefix));
    return;
  }
  MQTTClient::publish(topic, _on ? "{\"on\":true}" : "{\"on\":false}");

  JsonDocument doc;
  doc["on"] = _on;
  EventBus::publish("relay", doc.as<JsonObject>());
}

// One line for `module.status`.
// in: out sink. out: "pin=<n> state=on|off".
void ExampleRemoteRelay::status(ShellOutput out) {
  char line[48];
  snprintf(line, sizeof(line), "pin=%d state=%s", _pin, _on ? "on" : "off");
  out(line);
}

MODULE_REGISTER(ExampleRemoteRelay, PRIORITY_OUTPUT)

#endif  // ENABLE_EXAMPLE_REMOTE_RELAY
```
