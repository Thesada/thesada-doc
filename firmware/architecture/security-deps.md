---
title: Security & Dependencies
parent: Architecture
grand_parent: Firmware
nav_order: 7
description: "HTTP auth, rate limiting, WebSocket auth flow, adding new modules, and library dependency list."
---

# Security & Dependencies

## Adding a New Module

1. Create `src/modules/newmodule/NewModule.h` and `NewModule.cpp`
2. Inherit from `Module`, implement `begin()`, `loop()`, `name()`
3. Use `EventBus::publish()` to emit data, `EventBus::subscribe()` to react
4. Add `#define ENABLE_NEWMODULE` to `thesada_config.h`
5. Add config block to `data/config.json` if needed
6. Add one `#ifdef ENABLE_NEWMODULE` block to `ModuleRegistry.cpp`

No other files touched.

---

## Security

| Control | Implementation |
|---|---|
| Dashboard + `/api/state` + `/api/info` | Public (read-only sensor data) |
| All admin endpoints | Bearer token or HTTP Basic Auth (backwards compatible) |
| Token auth | `POST /api/login` with Basic Auth returns a 1-hour Bearer token (max 4 concurrent tokens) |
| Rate limiting | `/api/login` and `/api/auth/check`: 5 failed attempts per source IP triggers a 30 s lockout (returns 429) |
| WebSocket terminal | Requires prior `GET /api/ws/token` (auth-gated); server records caller IP as authorized for 30 s (one-time use) |
| TLS | All MQTT and OTA HTTPS uses the CA cert from `/ca.crt` on LittleFS; `setInsecure()` fallback logs a warning |

**Token auth flow (v1.2.4+):**

```
1. POST /api/login  (Authorization: Basic base64(user:pass))
   -> {"ok":true, "token":"<32-char-hex>", "expires_in":3600}
2. All admin requests: Authorization: Bearer <token>
3. Token stored in sessionStorage (persists across page refresh, cleared on tab close)
4. On device reboot, stale tokens are detected and login is re-prompted
5. Basic Auth still accepted on all admin endpoints (for curl, scripts, backwards compat)
```

**WebSocket auth flow:**

```
1. JS calls GET /api/ws/token  (Authorization: Bearer <token>)
2. Server records remoteIP -> authorized for 30 s
3. JS opens ws://device/ws/serial  (no credentials in URL)
4. WS_EVT_CONNECT: server checks remoteIP against grant table -> allow or close
```

Unauthenticated WebSocket connections (e.g. direct curl or wscat) are accepted at TCP level (101 Switching Protocols) then immediately closed with a WS close frame. The rejection is logged as `[WRN][WebServer] WS: rejected - not pre-authorized`.

**Note:** The web interface uses HTTP, not HTTPS. Admin credentials transit in cleartext on the LAN. For internet-exposed deployments, put the device behind a reverse proxy with TLS termination.

---

## Hardware Watchdog

The firmware enables the ESP32 Task Watchdog Timer (30s timeout) at boot. If `loop()` fails to feed the watchdog within 30 seconds (hang, infinite loop, memory corruption), the device automatically reboots.

```cpp
esp_task_wdt_init(30, true);   // 30s timeout, panic on expire
esp_task_wdt_add(NULL);        // monitor the loopTask
esp_task_wdt_reset();          // fed every loop() cycle
```

---

## CI/CD

GitHub Actions pipeline (`.github/workflows/ci.yml`):

- **Every push to `dev` or `main`**: builds full + minimal firmware, uploads as artifacts
- **Push to `main` with new version**: auto-creates GitHub release with binaries + changelog
- **Existing version**: skips release (no duplicates)

**Git workflow:**
1. Develop on `dev` - CI catches compile errors on every push
2. When ready to release: bump `FIRMWARE_VERSION` in `thesada_config.h`, merge dev to main
3. CI builds and creates the GitHub release automatically
4. Production nodes pick up the new version via OTA

`release.sh` still works for manual releases (CI skips if release already exists).

---

## Dependencies

| Library | Version | Purpose |
|---|---|---|
| Arduino framework (ESP32) | espressif32 @ 6.13.0 | Base framework |
| ArduinoJson | 7.4.3 | JSON config + event payloads |
| LittleFS | built-in | Filesystem (config, CA cert, Lua scripts) |
| PubSubClient | 2.8 | WiFi MQTT client |
| ESPAsyncWebServer + AsyncTCP | git / vendored | Web server + WebSocket |
| ESP-Arduino-Lua | git | Lua 5.3 runtime (GPL-3.0) |
| TinyGSM | 0.12.0 | AT command modem driver |
| XPowersLib | git | AXP2101 PMU control |
| DallasTemperature + OneWire | 4.0.6 / 2.3.8 | DS18B20 sensors |
| Adafruit ADS1X15 | 2.6.2 | ADS1115 ADC |
| HTTPClient + WiFiClientSecure | built-in | OTA manifest fetch + TLS |
| mbedtls | built-in | SHA256 verification for OTA |

> **`espressif32` 6.13.0 requires `intelhex`** in the PlatformIO Python environment (used to build the bootloader). Install once:
> ```bash
> ~/.local/pipx/venvs/platformio/bin/python -m pip install intelhex
> ```
