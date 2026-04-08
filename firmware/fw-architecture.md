---
title: Architecture
parent: Firmware
nav_order: 2
has_children: true
description: "thesada-fw firmware architecture - self-registering modules, EventBus, Shell, Lua scripting, MQTT over TLS, multi-board support."
---

# Firmware Architecture

`thesada-fw` is built on C++17 with the Arduino framework, compiled via PlatformIO for multiple ESP32 board targets. It uses self-registering modules with priority-based boot ordering and a lightweight **Event Bus** for inter-module communication.

This section is split into sub-pages for easier navigation.
