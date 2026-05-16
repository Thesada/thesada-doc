---
title: Home Assistant
parent: SHT31 Monitor
grand_parent: Modules
nav_order: 3
description: "Verify the SHT31 monitor's MQTT auto-discovered entities in Home Assistant."
---

# SHT31 Monitor - Home Assistant

The SHT31 node publishes via MQTT and Home Assistant auto-discovers it when `mqtt.ha_discovery: true` (the default). No manual YAML required.

## Verify MQTT entities

1. **Settings - Devices & Services - MQTT**.
2. Find `thesada-sht31` (or whatever `device.name` is set to). It appears automatically once the device connects.
3. Click the device. Two entities should show:
   - `sensor.thesada_sht31_temperature`
   - `sensor.thesada_sht31_humidity`

If the device is not visible: check the broker actually receives the discovery configs:

```bash
mosquitto_sub -h <broker> -p 8883 --cafile ca.crt \
  -u <user> -P <pass> \
  -t 'homeassistant/sensor/+/+/config' -v
```

Each entity references the live state topic (`thesada/sht31/sensor/temperature/sht31`, `.../humidity/sht31`) and the availability topic (`thesada/sht31/status`). Home Assistant marks the entity unavailable when the device's LWT fires.

See [MQTT Topics]({{ site.baseurl }}/firmware/mqtt-topics/) for the full topic shape and discovery payload schema.