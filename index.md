---
title: Home
nav_order: 1
description: "Open-source ESP32 property monitoring platform - firmware, MQTT, Home Assistant, and hardware documentation for rural and off-grid deployments."
---

# Thesada Documentation

Thesada is an open-source modular property monitoring platform built on ESP32 hardware with custom C++ firmware, MQTT over TLS, cellular fallback, and Home Assistant integration. Designed for rural and off-grid deployments where reliability matters.

Every build on [Foothills Builds](https://youtube.com/@FoothillsBuilds) gets fully documented here.

## What it does

- **Monitors** - temperature (DS18B20), current (ADS1115 + CT clamp), battery voltage and charge state
- **Alerts** - threshold alerts with hysteresis via MQTT and webhook, forwarded to Telegram through Home Assistant
- **Logs** - CSV data to SD card, logrotate included
- **Updates** - over-the-air via GitHub Releases (TLS-verified, SHA256 checked)
- **Scripted** - Lua 5.3 runtime for custom rules without recompiling

## Where to start

- New to Thesada? Start with [Getting Started](getting-started/overview.md)
- Looking for a specific module? See [Modules](modules/)
- Want the firmware source? See [GitHub](https://github.com/Thesada/thesada-fw)
