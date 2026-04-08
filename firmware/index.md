---
title: Firmware
nav_order: 1
has_children: true
description: "thesada-fw - custom ESP32 firmware with MQTT over TLS, cellular fallback, OTA updates, Lua scripting, TFT/OLED display, and multi-board support."
---

# Firmware

Custom firmware (`thesada-fw`) for all Thesada nodes. Supports multiple ESP32 board variants with compile-time module selection. This section documents the firmware architecture, configuration, and testing.

![Sensor dashboard]({{ site.baseurl }}/assets/img/firmware/dashboard-sensors.png)

---

## Quick links

| | |
|---|---|
| [Architecture](fw-architecture.md) | Module design, boot sequence, Shell, Lua, OTA, connectivity |
| [Testing](fw-testing.md) | Test script, manual checks, section-by-section verification |
| [Source](https://github.com/thesada/thesada-fw) | GitHub - GPL-3.0-only |

---

## Feature overview

| Feature | Notes |
|---|---|
| WiFi multi-SSID | Ranked by RSSI; NTP synced on connect |
| LTE-M/NB-IoT fallback | SIM7080G modem-native MQTT over TLS; reverts to WiFi automatically |
| TLS MQTT | CA cert from LittleFS (`/ca.crt`); ISRG Root X1 works for Let's Encrypt brokers |
| MQTT connection reliability | 10 min watchdog, TCP keepalive (30s/10s/3), auto-reconnect on half-open sockets |
| HA MQTT discovery | Auto-registers all sensors in Home Assistant on connect; no manual YAML needed |
| DS18B20 temperature | OneWire, multi-sensor, auto-discovery, retry on disconnect, last-known-value fallback |
| SHT31 temperature + humidity | I2C, raw driver (no external library), configurable interval [ENABLE_SHT31] |
| ADS1115 current sensing | RMS sampling (30 samples over 2 cycles at 60Hz), outputs amps for SCT-013-030 |
| Battery monitoring | AXP2101 voltage, state of charge, charge status; MQTT publish + low-battery alert |
| SD card logging | CSV, per-boot files, configurable max file size with auto-rotation |
| Lua scripting | Lua 5.3 runtime; hot-reloadable rules, EventBus + MQTT + Display bindings |
| SSD1306 OLED display | 128x64 I2C, Lua-driven rendering via Display.* bindings [ENABLE_DISPLAY] |
| ILI9341 TFT + touch | CYD board (ESP32-2432S028R), XPT2046 IRQ-driven touch, Lua Display.* [ENABLE_TFT] |
| Shell CLI | Commands over serial, WebSocket, HTTP (`POST /api/cmd`), and MQTT (`cli/#`) |
| OTA - push | Upload `.bin` via web dashboard or curl |
| OTA - pull | Fetch manifest from GitHub Releases, SHA256 verify, auto-install |
| PowerManager LED | Blue CHGLED: heartbeat pulse, hardware charge indicator, or off |
| NTP log timestamps | ISO 8601 UTC in log lines once clock is synced |
| Temperature alerts | Threshold rules with hysteresis, MQTT + HTTP webhook |
| Low-battery alerts | Fires when battery below `battery.low_pct`; hysteresis prevents repeat alerts |

---

## Hardware

| Board | PIO environment | Notes |
|---|---|---|
| LILYGO T-SIM7080-S3 | `esp32-owb` | Primary target - all modules, cellular + PMU |
| ESP32-S3 bare devkit | `esp32-s3-debug` | USB CDC serial, no LILYGO hardware |
| ESP32-WROOM-32 | `esp32-wroom` | No cellular/PMU/SD - OLED display, WiFi, MQTT |
| CYD (ESP32-2432S028R) | `esp32-cyd` | 2.8" TFT touch, LiteServer (OTA + config + WiFi setup) |
| WT32-ETH01 | `esp32-eth` | LAN8720A Ethernet, WiFi fallback |

Board-specific module overrides are in `thesada_config.h`. Each board auto-enables/disables modules to match its hardware.
