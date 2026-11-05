---
title: Build and Field Notes
parent: Firmware
nav_order: 8
description: "Build targets, the release and versioning workflow, and hardware-integration notes, including SIM7080G cellular TLS."
---

# Build and Field Notes

Build-time and hardware-integration knowledge for `thesada-fw` that does not belong to a single runtime subsystem. Runtime behaviour lives in the other firmware pages; this one holds build targets, the release workflow, and modem-integration notes.

## Build targets

`main` builds ESP32-S3 targets only. The PlatformIO environments and the boards they map to are listed in the [hardware table]({{ site.baseurl }}/firmware/#hardware). Each environment selects its module set at compile time.

Classic ESP32 variants (WROOM, CYD, Ethernet) are maintained on a separate track and are not produced from `main`. Do not expect `main` to build a non-S3 image.

## Release and versioning

Bump `FIRMWARE_VERSION` in `src/thesada_config.h` **before** the merge commit that ships the release, then tag that commit.

The source of truth for the running version is `thesada_config.h` plus the git tags - never a version line written into prose docs. Bumping before the merge avoids having to force-move a tag that was placed ahead of the version constant.

## Cellular TLS (SIM7080G)

TLS over cellular runs on the ESP32 (mbedTLS, `TlsClient`) over a plain modem TCP socket, the same stack and client cert as WiFi. Nothing is uploaded to the modem filesystem and no modem TLS setup exists.

Field notes:

- TinyGSM registers a socket client in a table when it is constructed and never removes it, so the firmware keeps its two modem sockets for the whole program instead of allocating them per request.
- Reference AT samples: LilyGo's published T-SIM7080G sketches at `github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G`.
