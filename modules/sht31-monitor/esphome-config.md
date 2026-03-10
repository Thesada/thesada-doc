---
title: ESPHome Config
parent: SHT31 Monitor
nav_order: 2
---

# SHT31 Monitor — ESPHome Config

Full ESPHome YAML configuration for the SHT31 monitor node.

---

## Config File

Location in repo: [`thesada-cfg/esphome/thesada-sht31.yaml`](https://github.com/Thesada/thesada-cfg/blob/main/esphome/thesada-sht31.yaml)

---

## secrets.yaml

The config references secrets that must be present in `secrets.yaml` in the ESPHome dashboard. Never commit this file — only [`secrets.yaml.example`](https://github.com/Thesada/thesada-cfg/blob/main/esphome/secrets.yaml.example) is tracked in the repo.

---

## Key Config Notes

**`captive_portal:`**
When the board cannot connect to WiFi it creates a fallback AP with a captive portal page for updating credentials. Low RAM cost, useful recovery mechanism.

**`api: encryption: key:`**
Required as of ESPHome 2026.1. The API key must be a 32-byte base64 string. Generate with `openssl rand -base64 32`. The old `api: password:` format is no longer supported.

**`ota: platform: esphome:`**
Required format as of ESPHome 2026.x. Once the device is online, all subsequent firmware updates are wireless — no USB cable needed.

**`i2c: scan: true`**
Logs all detected I2C addresses at boot. Useful for verifying the SHT31 is wired correctly. Remove or set to `false` in production to reduce log noise.

**`sht3xd`**
ESPHome's platform name for the SHT31 and SHT35 family. Uses I2C address `0x44` by default.

---

## First Flash

See [ESPHome Setup](../../getting-started/esphome.md) for the full first-flash process via CLI. OTA handles all subsequent updates.

---

## Debugging

To see I2C scan output and sensor readings in the log, temporarily set:

```yaml
logger:
  level: DEBUG
  baud_rate: 115200
```

This forces logs to serial even after WiFi connects, allowing you to see boot output including the I2C scan. Revert to `INFO` and remove `baud_rate` for production.