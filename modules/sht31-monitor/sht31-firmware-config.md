---
title: Firmware Config
parent: SHT31 Monitor
nav_order: 2
description: "Firmware configuration for the SHT31 temperature and humidity monitor on thesada-fw."
---

# SHT31 Monitor - Firmware Config

The SHT31 node runs thesada-fw with the `ENABLE_SHT31` module. No external library needed - raw I2C communication with the sensor.

**PIO environment:** `esp32-s3-debug` (BOARD_S3_BARE auto-enables SHT31)

---

## Config

Add the `sht31` section to `config.json`:

```json
{
  "sht31": {
    "sda": 11,
    "scl": 12,
    "address": 68,
    "interval_s": 30
  },
  "temperature": {
    "unit": "C"
  }
}
```

- `sda` / `scl` - I2C pins (Freenove S3: SDA=11, SCL=12)
- `address` - I2C address in decimal (0x44 = 68, 0x45 = 69)
- `interval_s` - read interval in seconds
- `temperature.unit` - "C" or "F" (affects MQTT published value)

---

## Build and flash

```bash
cd base
pio run -e esp32-s3-debug --target upload
pio run -e esp32-s3-debug --target uploadfs
```

---

## Verify

Shell command:
```
sht31
19.7C  57.8%
```

MQTT topics:
```
thesada/sht31/sensor/temperature/sht31  19.7
thesada/sht31/sensor/humidity/sht31     57.8
```