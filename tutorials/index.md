---
title: Tutorials
nav_order: 3
has_children: true
description: "Step-by-step walkthroughs: build a Thesada module on real hardware, plus standalone ESP32 how-tos for OTA updates from a release URL and MQTT over TLS."
---

# Tutorials

## On a Thesada board

These start from a flashed board and end with something new running on it. They assume you have done [Getting started]({{ site.baseurl }}/getting-started.html) once, so the toolchain, the captive portal and `mosquitto_sub` are already familiar.

| Tutorial | You end up with |
|---|---|
| [Build your first module]({{ site.baseurl }}/tutorials/first-module.html) | a sensor module of your own, publishing to MQTT, with a Lua rule reacting to it |

## ESP32 how-tos

These stand on their own. Each one explains the plain ESP32 mechanism with a sketch that compiles, then shows how Thesada does it. No Thesada board needed.

| How-to | The question it answers |
|---|---|
| [ESP32 OTA update from a GitHub release]({{ site.baseurl }}/tutorials/esp32-ota-update-github.html) | how to pull a firmware from a release URL, check its SHA256 and roll back a bad image |
| [ESP32 MQTT over TLS with a private CA]({{ site.baseurl }}/tutorials/esp32-mqtt-tls.html) | how to connect to Mosquitto over TLS with your own CA, with a password or a client certificate |
