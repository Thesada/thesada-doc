---
title: Home Assistant
parent: SHT31 Monitor
nav_order: 3
---

# SHT31 Monitor - Home Assistant

Once the SHT31 node is flashed and online, Home Assistant auto-discovers it via MQTT integration. This page covers verifying the entities and setting up hourly Telegram alerts.

---

## Prerequisites

- SHT31 node flashed and online
- Telegram bot configured (optional, for alerts)

---

## 1. Verify MQTT Entities

1. **Settings → Integrations → MQTT**
2. Find `thesada-sht31` - it should appear automatically once the device is online
3. Click the device - you should see two entities:
   - `sensor.thesada_sht31_temperature`
   - `sensor.thesada_sht31_humidity`