---
title: Firmware
nav_order: 3
has_children: true
description: "thesada-fw - custom ESP32-S3 firmware with MQTT over TLS, cellular fallback, OTA updates, Lua scripting, and SD card logging."
---

# Firmware

Custom firmware (`thesada-fw`) for all Thesada nodes. Supports multiple ESP32 board variants with compile-time module selection. This section documents the firmware architecture, configuration, and testing.

![Sensor dashboard]({{ site.baseurl }}/assets/img/firmware/dashboard-sensors.png)

---

## Quick links

| | |
|---|---|
| [Architecture]({{ site.baseurl }}/firmware/fw-architecture/) | Module design, boot sequence, Shell, Lua, OTA, connectivity |
| [CLI Reference]({{ site.baseurl }}/firmware/cli-reference/) | Every shell command across serial, WebSocket, and MQTT |
| [MQTT Topics]({{ site.baseurl }}/firmware/mqtt-topics/) | Every topic the firmware publishes or subscribes to |
| [Chunked File I/O]({{ site.baseurl }}/firmware/chunked-io/) | Read and write device files larger than the MQTT buffer |
| [Lua Scripting]({{ site.baseurl }}/firmware/lua-scripting/) | Lua 5.3 runtime, EventBus, alert patterns, hot-reload |
| [Config Management]({{ site.baseurl }}/firmware/config/) | config.json shape, save/reload, drift hashes, recovery |
| [Provisioning]({{ site.baseurl }}/firmware/provisioning/) | Configure a new device, set the topic prefix, verify first connection |
| [Build and Field Notes]({{ site.baseurl }}/firmware/build/) | Build targets, release workflow, SIM7080G cellular mTLS sequence |
| [Testing]({{ site.baseurl }}/firmware/fw-testing/) | Test script, manual checks, section-by-section verification |
| [Source](https://github.com/thesada/thesada-fw) | GitHub - GPL-3.0-only |

---

## Feature overview

| Feature | Notes |
|---|---|
| WiFi multi-SSID | Ranked by RSSI; NTP synced on connect |
| LTE-M/NB-IoT fallback | SIM7080G modem-native MQTT over TLS; reverts to WiFi automatically |
| TLS MQTT | CA cert from LittleFS (`/ca.crt`); PROGMEM bundle (Let's Encrypt + GitHub roots) takes over if the file is missing |
| MQTT connection reliability | 10 min watchdog, TCP keepalive (30s/10s/3), auto-reconnect on half-open sockets |
| HA MQTT discovery | Auto-registers all sensors in Home Assistant on connect; no manual YAML needed |
| DS18B20 temperature | OneWire, multi-sensor, auto-discovery, retry on disconnect, last-known-value fallback |
| SHT31 temperature + humidity | I2C, raw driver (no external library), configurable interval [ENABLE_SHT31] |
| ADS1115 current sensing | RMS sampling (30 samples over 2 cycles at 60Hz), outputs amps for SCT-013-030 |
| Battery monitoring | AXP2101 voltage, state of charge, charge status; MQTT publish + low-battery alert |
| SD card logging | CSV, per-boot files, configurable max file size with auto-rotation |
| Lua scripting | Lua 5.3 runtime; hot-reloadable rules, EventBus + MQTT bindings |
| Shell CLI | Commands over serial, WebSocket, HTTP (`POST /api/cmd`), and MQTT (`cli/#`) |
| OTA - push | Upload `.bin` via web dashboard or curl |
| OTA - pull | Fetch manifest, SHA256 verify, auto-install. Watchdog-safe download loop tolerates flaky wireless links without panicking mid-flash |
| OTA - PROGMEM CA fallback | Common public TLS roots baked into the firmware. OTA + MQTT stay TLS-verified even when `/ca.crt` on LittleFS is missing or wiped |
| OTA - structured events | `<prefix>/status/ota` publishes `updating`, `up-to-date`, `refused` (with kebab reason), or `failed` JSON on every OTA code path |
| OTA force mode | `ota.check --force` bypasses version check - dev iteration without version bumps, and recovery of stuck devices |
| PSRAM support | 8 MB external PSRAM on ESP32-S3 targets via `memory_type=qio_opi`; heap-hungry modules (Lua, TLS buffers) can route to PSRAM |
| Heap + PSRAM telemetry | Free / min free / max alloc block / PSRAM free published to MQTT every 5 min with HA auto-discovery for each metric |
| Debug CLI | `ota.status` (partition + rollback state), `chip.info` (rev, flash, PSRAM, CPU freq), `net.mqtt` (subscription table + RX ring), `net.http` (auto-routed WiFi or cellular HTTPS GET), `module.list`, `module.status` |
| PowerManager LED | Blue CHGLED: heartbeat pulse, hardware charge indicator, or off |
| NTP log timestamps | ISO 8601 UTC in log lines once clock is synced |
| Temperature alerts | Threshold rules with hysteresis, MQTT + HTTP webhook |
| Low-battery alerts | Fires when battery below `battery.low_pct`; hysteresis prevents repeat alerts |

---

## Hardware

| Board | PIO environment | Notes |
|---|---|---|
| LILYGO T-SIM7080-S3 | `esp32-owb` | Primary target - all modules, cellular + PMU |
| LILYGO T-SIM7080-S3 (rescue) | `esp32-owb-rescue` | Stripped recovery build for OTA rescue - bootloader-compatible, all optional modules off |
| LILYGO T-SIM7080-S3 (debug) | `esp32-owb-debug` | Same hardware as `esp32-owb`, with CDC serial and the cellular-debug CLI commands enabled |
| ESP32-S3 bare devkit | `esp32-s3-debug` | USB CDC serial, no LILYGO peripherals - bench bring-up target |
| ESP32-S3 bare devkit (rescue) | `esp32-s3-debug-rescue` | Stripped recovery build for the bare S3 devkit |

Board-specific module overrides are in `src/thesada_config.h`. The default build targets the LILYGO T-SIM7080-S3; `-DBOARD_S3_BARE` switches to the bare ESP32-S3 devkit, `-DBOARD_OWB_RESCUE` strips every optional module for a minimum-flash recovery image.
