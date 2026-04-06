---
title: Home
nav_order: 1
description: "Open-source ESP32 property monitoring platform - firmware, MQTT, cellular fallback, Lua scripting, and hardware documentation."
---

# Thesada Documentation

Thesada is an open-source modular property monitoring platform built on ESP32 hardware with custom C++ firmware, MQTT over TLS, cellular fallback, and Lua scripting. Designed for rural and off-grid deployments where reliability matters.

## What it does

- **Monitors** - temperature (DS18B20), current (ADS1115 + CT clamp), battery voltage and charge state
- **Alerts** - Lua-defined alert rules with sustain, cooldown, and hysteresis via MQTT, Telegram, or webhook
- **Displays** - SSD1306 OLED or ILI9341 TFT touch (CYD board) with Lua-driven rendering
- **Logs** - CSV data to SD card, logrotate included
- **Updates** - over-the-air via HTTP push or pull (TLS-verified, SHA256 checked)
- **Scripted** - Lua 5.3 runtime for custom rules and display rendering without recompiling

## Where to start

- [Firmware architecture](firmware/fw-index.md) - design, modules, shell, Lua, OTA
- [Modules](modules/) - OWB monitor, SHT31, well pump
- [Source code](https://github.com/Thesada/thesada-fw) - GitHub (GPL-3.0)
