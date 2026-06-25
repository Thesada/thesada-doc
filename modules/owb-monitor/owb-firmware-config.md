---
title: Firmware Config
parent: OWB Monitor
grand_parent: Modules
nav_order: 3
description: "thesada-fw configuration for the OWB monitor node - WiFi, MQTT, sensors, alerts, and deployment."
---

# OWB Monitor - Firmware Config

The OWB monitor runs [thesada-fw]({{ site.baseurl }}/firmware/) on a LILYGO T-SIM7080-S3. This page covers the OWB-specific configuration.

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
  "read_retries": 2,
  "max_delta_c": 40,
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
- `read_retries: 2` re-reads a probe on a transient bus fault before reporting it disconnected (default 2). DS18B20 scratchpad CRC is always checked by the driver; this adds retries on top.
- `max_delta_c: 40` rejects a reading that jumps more than 40 C from the last good value and reports `disconnected` instead - guards against marginal-bus garbage (long flying leads can read wildly wrong but CRC-valid). Set `0` to disable.

**Multiple 1-Wire buses:** to drive more than one bus, replace the scalar `pin` with a `buses` list. Each bus gets its own GPIO; probes from all buses aggregate into one sensor list (DS18B20 ROM addresses are globally unique):

```json
"temperature": {
  "buses": [ { "pin": 9 }, { "pin": 10 } ],
  "auto_discover": true
}
```

The scalar `pin` form still works and is treated as a single bus.

**Live probe management:** attach or swap a probe without rebooting - run `temp.discover` over the [CLI]({{ site.baseurl }}/firmware/cli-reference/) to re-walk every bus and pick up new probes; `temp.discover --prune` drops probes that no longer respond and clears their stale entries.

**Current sensing (ADS1115 + CT clamps):**

```json
"ads1115": {
  "i2c_sda": 1,
  "i2c_scl": 2,
  "address": 72,
  "interval_s": 60,
  "line_voltage": 120,
  "channels": [
    { "name": "House Pump", "mux": "A0_A1", "gain": 0.256, "clamp_a_per_v": 30 },
    { "name": "Barn Pump", "mux": "A2_A3", "gain": 0.256, "clamp_a_per_v": 30 }
  ]
}
```

- `line_voltage: 120` - used for power (watts) calculation. Update if your supply voltage differs.
- `clamp_a_per_v: 30` - CT clamp ratio, amps per 1 V of output. SCT-013-030 = 30, SCT-013-005 = 5. Defaults to 30 if omitted.
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
printf '/scripts/rules.lua\n' > /tmp/payload.bin
cat rules.lua                >> /tmp/payload.bin
mosquitto_pub ... -t 'thesada/owb/cli/fs.write' -f /tmp/payload.bin
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
