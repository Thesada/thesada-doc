---
title: ESPHome Config
parent: OWB Monitor
nav_order: 2
---

# OWB Monitor — ESPHome Config

{: .warning }
> This configuration is not actively developed. The OWB monitor runs [custom firmware (thesada-fw)](../../firmware/fw-architecture.md) instead.
>
> ESPHome was evaluated for this node but the LILYGO T-SIM7080-S3 hardware requires low-level control of the AXP2101 PMU and SIM7080G modem that ESPHome cannot provide without significant custom component work. The custom firmware handles these directly.

---

## Config File

Location in repo: [`thesada-cfg/esphome/thesada-owb.yaml`](https://github.com/Thesada/thesada-cfg/blob/main/esphome/thesada-owb.yaml)

---

## secrets.yaml

The config references secrets that must be present in `secrets.yaml` in the ESPHome dashboard. Never commit this file — only [`secrets.yaml.example`](https://github.com/Thesada/thesada-cfg/blob/main/esphome/secrets.yaml.example) is tracked in the repo.

---

## Key Config Notes

**`mqtt:`**
Unlike the SHT31 monitor which uses the ESPHome native API, the OWB monitor publishes via MQTT. This allows remote nodes on cellular to reach the broker at `mqtt.thesada.app` over port 8883 without requiring a direct connection to the HA instance.

**`one_wire:`**
All four DS18B20 sensors share a single GPIO pin using the 1-Wire protocol. Each sensor has a unique 64-bit address burned into the chip at the factory.

**DS18B20 addresses**
> **TODO:** Run a 1-Wire scan after sensors arrive to get the actual addresses. Replace the placeholder `0x000000000000000X` values in the config before flashing.

To run the scan, flash the node with `logger: level: DEBUG` and read the boot log — ESPHome will print all detected 1-Wire addresses.

**`ads1115:`**
The ADS1115 runs at I2C address `0x48` (default — ADDR pin to GND). Two differential channels are used: `A0_A1` for the house pump and `A2_A3` for the barn pump.

**Collection vs publish interval**
Sensors collect every 60 seconds. The `sliding_window_moving_average` filter accumulates 60 readings and publishes once per hour. This reduces MQTT traffic while preserving local data resolution.

```yaml
filters:
  - sliding_window_moving_average:
      window_size: 60
      send_every: 60
```

**`web_server:`**
The node runs a lightweight web server on port 80. This provides a local dashboard accessible on the same network showing all sensor readings in real time — no Home Assistant or MQTT required. Useful for on-site diagnostics.

```yaml
web_server:
  port: 80
```

**`api: encryption: key:`**
Required as of ESPHome 2026.1. Generate with `openssl rand -base64 32`.

**`ota: platform: esphome:`**
Required format as of ESPHome 2026.x. Once the device is online, all subsequent firmware updates are wireless.

---

## SD Card Logging

> **TODO:** Implement local CSV logging to MicroSD. The LILYGO T-SIM7080-S3 has a MicroSD slot. ESPHome does not have native CSV logging — this requires a custom lambda component.

Draft approach:

```yaml
# Draft — not yet validated
esphome:
  on_boot:
    then:
      - lambda: |-
          // Mount SD card
          // Open or create CSV file
          // Write header if new file

interval:
  - interval: 60s
    then:
      - lambda: |-
          // Append row: timestamp, house_supply, house_return,
          //   barn_supply, barn_return, house_current, barn_current
```

CSV format:

```
timestamp,house_supply_temp,house_return_temp,barn_supply_temp,barn_return_temp,house_pump_current,barn_pump_current
2026-03-15T14:32:00,74.3,58.1,71.2,54.6,2.34,2.31
```

This provides local data recovery if MQTT connectivity is lost. The SD card can be pulled and reviewed independently of the network.

---

## GPIO Pin Assignments

| Function | GPIO (placeholder) |
|---|---|
| 1-Wire (DS18B20) | GPIO12 |
| I2C SDA (ADS1115) | GPIO1 |
| I2C SCL (ADS1115) | GPIO2 |

---

## First Flash

See [ESPHome Setup](../../getting-started/esphome.md) for the full first-flash process via CLI. OTA handles all subsequent updates.

---

## Debugging

To see the 1-Wire scan and sensor readings in the log, temporarily set:

```yaml
logger:
  level: DEBUG
  baud_rate: 115200
```

Revert to `INFO` and remove `baud_rate` for production.