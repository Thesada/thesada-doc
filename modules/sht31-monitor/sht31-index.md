---
title: SHT31 Monitor
parent: Modules
nav_order: 1
description: "SHT31 indoor temperature and humidity monitor - thesada-fw on Freenove ESP32-S3."
has_children: true
---

# SHT31 Monitor

A temperature and humidity monitoring node built on the Freenove ESP32-S3 WROOM and SHT31 sensor. Runs thesada-fw with the SHT31 module (ENABLE_SHT31). Publishes readings via MQTT over TLS.

**Hardware:**
- Freenove ESP32-S3 WROOM
- SHT31 temperature and humidity sensor module (I2C, address 0x44)
- Jumper wires (SDA=GPIO11, SCL=GPIO12)

**What it measures:**
- Temperature (C or F, configurable)
- Relative humidity (%)

**Update interval:** 30 seconds (configurable via sht31.interval_s)

**MQTT topics:**
- `<prefix>/sensor/temperature/sht31` - temperature reading
- `<prefix>/sensor/humidity/sht31` - humidity reading

**Shell command:** `sht31` - live reading

**Config:**
```json
"sht31": {
  "sda": 11,
  "scl": 12,
  "address": 68,
  "interval_s": 30
}
```
