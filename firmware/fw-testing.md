---
title: Testing
parent: Firmware
nav_order: 2
has_children: true
description: "Manual and automated test checklist for thesada-fw firmware - API, OTA, MQTT, sensors, and WebSocket verification."
---

# Firmware Testing

`thesada-fw` runs on embedded hardware. Tests are performed against a live device over serial and the web dashboard. An automated + manual test script is provided in `tests/test_firmware.py`.

This section is split into sub-pages for easier navigation.

## Hardware-in-the-loop (HIL)

The bench rack flashes a board over USB and runs the automated battery against it - no network or broker in the test path, so a board fault never hides behind connectivity. The harness drives the serial console in command mode (`console.mode command`), so it reads clean, framed command output instead of racing log lines:

```bash
python tests/test_firmware.py --port <port> --command-mode --board <id> \
  --skip sensors,ads1115,mqtt,ota,websocket,sd,cellular,config_mqtt,fallback_ap
```

`--board <id>` adds per-board profile checks (device identity, flash size, PSRAM, reset reason, board-specific module active). The run exits non-zero on any failed check, and fails closed: a missing frame, zero checks, or a board that rebooted mid-run all count as failure.

The bench host flashes and runs all boards via a wrapper that resolves each board by its USB fingerprint. Run the smoke on the rack before pushing `main`; a `pre-push` git hook reminds you. For a soak, loop the battery without reflashing and watch the per-run heap floor:

```bash
while sleep 600; do hil-flash-and-smoke --no-flash all || break; done
```
