---
title: Firmware
nav_order: 5
has_children: true
---

# Firmware

Thesada nodes run one of two firmware approaches depending on the use case:

**ESPHome** is used for simpler sensor nodes where its built-in components cover the requirements. Configuration lives in `thesada-cfg/esphome/`. See the [Getting Started](../getting-started/esphome.md) guide and each module's ESPHome Config page.

**Custom firmware** (`thesada-fw`) is used where ESPHome lacks coverage — cellular fallback, Lua scripting, complex inter-module logic, or full control over the build. This section documents the custom firmware architecture.

## Source

[github.com/thesada/thesada-fw](https://github.com/thesada/thesada-fw)

Licence: GPL-3.0-only
