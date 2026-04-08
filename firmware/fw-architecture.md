---
title: Architecture
parent: Firmware
nav_order: 1
has_children: true
description: "thesada-fw firmware architecture - ModuleRegistry, EventBus, Shell, PowerManager, OTA, Lua scripting, and MQTT over TLS on ESP32-S3."
---

# Firmware Architecture

`thesada-fw` is built on C++17 with the Arduino framework, compiled via PlatformIO for the LILYGO T-SIM7080-S3 (ESP32-S3). It uses a **Module Registry** pattern with a lightweight **Event Bus** for inter-module communication.

This section is split into sub-pages for easier navigation.
