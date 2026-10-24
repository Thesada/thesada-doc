---
title: blink-led
parent: Examples
nav_order: 3
description: "Starter output module: one GPIO toggled on a non-blocking millis() timer, with the pin and interval read from config."
---

# blink-led

The periodic output shape. One GPIO, toggled on a timer, nothing published. `lib/thesada-mod-example-blink-led/` on the firmware `dev` branch; ships with the next release.

## What it demonstrates

| Thing | Where in the code |
|---|---|
| Config in `begin()`, nothing in the constructor | `begin()` reads `pin` and `interval_ms` and sets the pin up as an output |
| A non-blocking `loop()` | compare `millis()` against the interval, return early, toggle when due. No `delay()`, so every other module keeps running between toggles |
| Output only | no MQTT publish, no bus event, no shell command; the pin level is the whole result |
| `module.status` | one line: `pin=2 state=on interval_ms=500` |
| Registration | `MODULE_REGISTER(ExampleBlinkLed, PRIORITY_OUTPUT)`, guarded by `ENABLE_EXAMPLE_BLINK_LED` |

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-blink-led/src/ExampleBlinkLed.cpp match="\[\"pin\"\]\s+\| 2;" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-blink-led/src/ExampleBlinkLed.cpp match="\[\"interval_ms\"\]\s+\| 500;" -->
A missing key falls back to the default in `begin()`: pin 2, 500 ms.

## Config

```json
"example_blink_led": {
  "enabled":     true,
  "pin":         2,
  "interval_ms": 500
}
```

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ModuleRegistry.cpp match="registry.module_skip priority=%d name=%s reason=disabled" -->
`enabled` is required: optional modules default off, and without `"enabled": true` the registry logs `registry.module_skip ... reason=disabled` instead of starting the module.

<!-- claim: repo=thesada-fw file=lib/thesada-mod-ads1115/src/ADS1115Module.cpp match="\[\"i2c_scl\"\]\s+\| 2;" -->
> **Pin 2 is the ADS1115 clock on some builds.** `esp32-owb`, `esp32-owb-debug` and `esp32-s3-carrier` compile the ADS1115 module, and its I2C SCL defaults to GPIO 2 (`ads1115.i2c_scl`). With `ads1115` enabled on those, set `pin` to a free GPIO, or the blink takes over the I2C clock line.

## Turn it on

Uncomment `ENABLE_EXAMPLE_BLINK_LED` in `src/thesada_config.h`, build and flash as for any module. Boot log:

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Module.h match="PRIORITY_OUTPUT   = 60" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-blink-led/src/ExampleBlinkLed.cpp match="example_blink\.ready pin=%d interval_ms=%u" -->
```text
[INF][Registry] registry.module_init priority=60 name=ExampleBlinkLed
[INF][ExBlink] example_blink.ready pin=2 interval_ms=500
```

## Expected output

The pin flips every `interval_ms`, so with the defaults an LED on pin 2 blinks at 1 Hz. Toggles are not logged. `module.status` shows the current level, one line among the other modules:

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-blink-led/src/ExampleBlinkLed.cpp match="pin=%d state=%s interval_ms=%u" -->
```text
module.status
  ExampleBlinkLed pin=2 state=on interval_ms=500
```

## The code

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-example-blink-led/src/ExampleBlinkLed.cpp match="MODULE_REGISTER\(ExampleBlinkLed, PRIORITY_OUTPUT\)" -->
`src/ExampleBlinkLed.h`:

```cpp
// thesada-fw - ExampleBlinkLed.h
// Starter module: blink an LED on a configurable timer. The periodic output
// shape - config in begin(), non-blocking timer in loop(), status() output.
// SPDX-License-Identifier: GPL-3.0-only
#pragma once

#include <Arduino.h>
#include <Module.h>

class ExampleBlinkLed : public Module {
public:
  void begin() override;
  void loop() override;
  const char* name() override { return "ExampleBlinkLed"; }
  const char* configKey() override { return "example_blink_led"; }
  void status(ShellOutput out) override;

private:
  uint32_t _intervalMs = 500;
  uint32_t _last       = 0;
  int      _pin        = 2;
  bool     _on         = false;
};
```

`src/ExampleBlinkLed.cpp`:

```cpp
// thesada-fw - ExampleBlinkLed.cpp
// SPDX-License-Identifier: GPL-3.0-only
#include <thesada_config.h>
#include "ExampleBlinkLed.h"
#include <Config.h>
#include <Log.h>
#include <ModuleRegistry.h>
#include <ArduinoJson.h>
#include <stdio.h>

#ifdef ENABLE_EXAMPLE_BLINK_LED

static const char* TAG = "ExBlink";

// Read pin and interval from config, initialize the GPIO.
// in: config block example_blink_led (pin, interval_ms).
// out: GPIO configured as OUTPUT.
void ExampleBlinkLed::begin() {
  JsonObject cfg = Config::get();
  _intervalMs = cfg["example_blink_led"]["interval_ms"] | 500;
  _pin        = cfg["example_blink_led"]["pin"]         | 2;

  pinMode(_pin, OUTPUT);
  digitalWrite(_pin, _on ? HIGH : LOW);

  Log::kvf(TAG, "example_blink.ready pin=%d interval_ms=%u", _pin, (unsigned)_intervalMs);
}

// Non-blocking toggle driven by millis().
// in: millis(). out: pin level toggled every interval_ms.
void ExampleBlinkLed::loop() {
  if (millis() - _last < _intervalMs) {
    return;
  }
  _last = millis();
  _on = !_on;
  digitalWrite(_pin, _on ? HIGH : LOW);
}

// One line for `module.status`.
// in: out sink. out: "pin=<n> state=on|off interval_ms=<n>".
void ExampleBlinkLed::status(ShellOutput out) {
  char line[64];
  snprintf(line, sizeof(line), "pin=%d state=%s interval_ms=%u", _pin, _on ? "on" : "off", (unsigned)_intervalMs);
  out(line);
}

MODULE_REGISTER(ExampleBlinkLed, PRIORITY_OUTPUT)

#endif  // ENABLE_EXAMPLE_BLINK_LED
```
