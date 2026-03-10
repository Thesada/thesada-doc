---
title: Wiring
parent: SHT31 Monitor
nav_order: 1
---

# SHT31 Monitor — Wiring

The SHT31 communicates over I2C — four wires from the sensor to the ESP32.

---

## Pin Connections

| SHT31 Pin | Freenove ESP32-S3 WROOM Pin | Notes |
|---|---|---|
| VCC | 3.3V | Do not use 5V |
| GND | GND | |
| SDA | GPIO11 | I2C data |
| SCL | GPIO12 | I2C clock |
| ADDR | Not connected | Leaves I2C address at default 0x44 |

---

## Notes

- Use the **3.3V** pin, not 5V — the SHT31 is a 3.3V device
- Leave the **ADDR** pin floating (unconnected) for default address `0x44`
- Connect with jumper wires via pin headers — no soldering required
- The Freenove ESP32-S3 WROOM has two USB-C ports:
  - **USB port** — used for flashing and serial monitor
  - **UART port** — do not use for flashing, monitoring only

---

## I2C Address

| ADDR pin | I2C Address |
|---|---|
| Floating / GND | 0x44 (default) |
| VCC | 0x45 |

The ESPHome config uses `0x44`. If you need to run two SHT31 sensors on the same bus, connect the second sensor's ADDR pin to VCC and set `address: 0x45` in the config.