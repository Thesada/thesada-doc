---
layout: home
title: Home
nav_order: 1
description: "Modular ESP32 firmware framework for production IoT products - OTA with rollback, telemetry, runtime config, MQTT, Lua."
---

# Thesada Documentation

Thesada is an open-source modular ESP32 firmware framework for building production IoT products. Custom C++ firmware gives you OTA with rollback, telemetry, runtime config, multi-board support, MQTT over TLS, cellular fallback, a remote shell, and a Lua runtime, so a new product is a module rather than a fork.

Property monitoring is the example application it grew out of, and the module pages below document that build.

## What the framework gives you

- **Sensors** - drivers for temperature (DS18B20, SHT31), current (ADS1115 + CT clamp), battery voltage and charge state
- **Alerts** - Lua-defined alert rules with sustain, cooldown, and hysteresis via MQTT, Telegram, or webhook
- **Logs** - CSV data to SD card, logrotate included
- **Updates** - over-the-air over WiFi or cellular, with rollback on a failed boot; HTTP push or pull (TLS-verified, SHA256 checked, PROGMEM CA fallback)
- **Scripted** - Lua 5.3 runtime for custom rules without recompiling

## Where to start

- [Getting started]({{ site.baseurl }}/getting-started.html) - flash a board and publish in 30 minutes
- [Firmware architecture]({{ site.baseurl }}/firmware/)
- [Modules]({{ site.baseurl }}/modules/)
- [Web App]({{ site.baseurl }}/app/)
- [Source code](https://github.com/Thesada/thesada-fw)
