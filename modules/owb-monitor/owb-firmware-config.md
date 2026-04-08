---
title: Firmware Config
parent: OWB Monitor
nav_order: 2
description: "thesada-fw configuration for the OWB monitor node - WiFi, MQTT, sensors, alerts, and deployment."
---

# OWB Monitor - Firmware Config

The OWB monitor runs [thesada-fw](../../firmware/index.md) on a LILYGO T-SIM7080-S3. This page covers the OWB-specific configuration.

## Hardware

| Component | Details |
|---|---|
| Board | LILYGO T-SIM7080-S3 (ESP32-S3 + SIM7080G + AXP2101) |
| Temperature | 4x DS18B20 on GPIO12 (1-Wire bus) |
| Current | ADS1115 with 2x SCT-013-030 CT clamps (I2C SDA=1, SCL=2) |
| Battery | 18650 LiPo via AXP2101, solar input |
| Connectivity | WiFi primary, LTE-M cellular fallback |

## config.json

The full config lives on LittleFS at `/config.json`. Edit via the web UI, HTTP API, or MQTT CLI.

### Key sections for OWB

**WiFi + MQTT:**

```json
"wifi": {
  "networks": [
    { "ssid": "YourIOT", "password": "your-password" }
  ],
  "ap_password": "changeme",
  "ap_timeout_s": 300
},
"mqtt": {
  "broker": "mqtt.example.com",
  "port": 8883,
  "user": "mqtt",
  "password": "your-mqtt-password",
  "topic_prefix": "thesada/owb",
  "ha_discovery": true,
  "buffer_in": 4096,
  "buffer_out": 4096
}
```

**Temperature sensors (DS18B20):**

```json
"temperature": {
  "pin": 12,
  "interval_s": 60,
  "auto_discover": true,
  "conversion_wait_ms": 850,
  "unit": "F",
  "sensors": [
    { "address": "28...", "name": "House Supply" },
    { "address": "28...", "name": "House Return" },
    { "address": "28...", "name": "Barn Supply" },
    { "address": "28...", "name": "Barn Return" }
  ]
}
```

- Set `auto_discover: true` on first boot to detect sensor addresses automatically
- After discovery, sensor addresses and names are saved to config
- `conversion_wait_ms: 850` gives reliable reads on long wire runs (default 750)
- `unit: "F"` publishes in Fahrenheit (thresholds in alert scripts always use Celsius)

**Current sensing (ADS1115 + CT clamps):**

```json
"ads1115": {
  "i2c_sda": 1,
  "i2c_scl": 2,
  "address": 72,
  "interval_s": 60,
  "line_voltage": 120,
  "channels": [
    { "name": "House Pump", "mux": "A0_A1", "gain": 0.256 },
    { "name": "Barn Pump", "mux": "A2_A3", "gain": 0.256 }
  ]
}
```

- `line_voltage: 120` - used for power (watts) calculation. Update if your supply voltage differs.
- RMS sampling: 30 samples over 2x 60Hz cycles for accurate AC current measurement

**Telegram alerts:**

```json
"telegram": {
  "bot_token": "your-bot-token",
  "chat_ids": ["your-chat-id"]
}
```

Alert logic is in `/scripts/rules.lua` on LittleFS (hot-reloadable, no recompile needed).

## Deployment

**First flash (USB):**

```bash
cd base
cp examples/config.json.example data/config.json
# edit config.json with your WiFi, MQTT, sensor names
pio run -e esp32-owb --target upload
pio run -e esp32-owb --target uploadfs
```

**Subsequent updates (OTA):**

The node checks GitHub releases every 6 hours and auto-updates. Or trigger manually:

```bash
# Via MQTT CLI
mosquitto_pub ... -t 'thesada/owb/cli/ota.check' -m ''

# Via HTTP (if on same network)
curl -u admin:changeme -X POST http://<node-ip>/ota -F 'firmware=@build/firmware.bin'
```

**Push scripts remotely:**

```bash
printf '/scripts/rules.lua\n' | cat - rules.lua | mosquitto_pub ... -t 'thesada/owb/cli/file.write' -s
mosquitto_pub ... -t 'thesada/owb/cli/lua.reload' -m ''
```

## MQTT topics

All sensor data publishes to per-sensor topics under the configured prefix:

| Topic | Value |
|---|---|
| `thesada/owb/sensor/temperature/house_supply` | `65.20` |
| `thesada/owb/sensor/temperature/house_return` | `57.10` |
| `thesada/owb/sensor/current/house_pump` | `0.70` |
| `thesada/owb/sensor/power/house_pump` | `84.0` |
| `thesada/owb/sensor/battery/percent` | `100` |
| `thesada/owb/status` | `online` / `offline` (LWT) |
| `thesada/owb/alert` | alert messages from rules.lua |

Home Assistant picks these up automatically via MQTT auto-discovery (when `ha_discovery: true`).

## Verification

After deployment, verify with the MQTT CLI:

```bash
mosquitto_pub ... -t 'thesada/owb/cli/version' -m ''
mosquitto_pub ... -t 'thesada/owb/cli/sensors' -m ''
mosquitto_pub ... -t 'thesada/owb/cli/selftest' -m ''
```

Or via the web dashboard at `http://<node-ip>/` (login: admin/changeme).
