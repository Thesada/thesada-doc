---
title: ESPHome Config (Deprecated)
parent: OWB Monitor
nav_order: 4
description: "Deprecated - the OWB monitor now runs thesada-fw custom firmware, not ESPHome."
---

# OWB Monitor - ESPHome Config (Deprecated)

{: .warning }
> **This page is deprecated.** The OWB monitor runs [thesada-fw custom firmware](../../firmware/fw-index.md), not ESPHome. The ESPHome YAML config is preserved in [`thesada-cfg/esphome/thesada-owb.yaml`](https://github.com/Thesada/thesada-cfg/blob/main/esphome/thesada-owb.yaml) for reference only.

ESPHome was evaluated for this node but the LILYGO T-SIM7080-S3 requires low-level control of the AXP2101 PMU and SIM7080G modem that ESPHome cannot provide without significant custom component work.

For the current OWB firmware setup, see [OWB Firmware Config](owb-firmware-config.md).
