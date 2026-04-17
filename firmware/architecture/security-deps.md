---
title: Security & Dependencies
parent: Architecture
grand_parent: Firmware
nav_order: 7
description: "HTTP auth, rate limiting, WebSocket auth flow, adding new modules, and library dependency list."
---

# Security & Dependencies

## Adding a New Module

1. Create `lib/thesada-mod-newmodule/src/NewModule.h` and `NewModule.cpp`
2. Inherit from `Module`, implement `begin()`, `loop()`, `name()`
3. Use `EventBus::publish()` to emit data, `EventBus::subscribe()` to react
4. Add `#define ENABLE_NEWMODULE` to `thesada_config.h`
5. Add config block to `data/config.json` if needed
6. Add `MODULE_REGISTER(NewModule, ModulePriority::SENSOR)` at the bottom of the `.cpp` file
7. Create a `library.json` in the module directory (see existing modules for template)

No other files touched. `ModuleRegistry.cpp` has zero module-specific code - self-registration happens via the `MODULE_REGISTER` macro in the module file.

---

## Security

| Control | Implementation |
|---|---|
| Dashboard + `/api/state` + `/api/info` | Public (read-only sensor data) |
| All admin endpoints | Bearer token or HTTP Basic Auth (backwards compatible) |
| Token auth | `POST /api/login` with Basic Auth returns a 1-hour Bearer token (max 4 concurrent tokens) |
| Rate limiting | `/api/login` and `/api/auth/check`: 5 failed attempts per source IP triggers a 30 s lockout (returns 429). Table holds 16 IPs. |
| WebSocket terminal | Requires prior `GET /api/ws/token` (auth-gated); server records caller IP as authorized for 30 s (one-time use) |
| Path traversal | `/api/file` rejects any path containing `..` |
| TLS | MQTT and OTA use CA cert from `/ca.crt` on LittleFS when present. See TLS exceptions below. |

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

### TLS exceptions

Not all outbound connections use `/ca.crt`. These paths use `setInsecure()` (TLS without certificate validation):

| Path | Reason | Risk |
|---|---|---|
| MQTT before NTP sync | Cert validation requires a valid system clock. Pre-NTP, the device connects insecure and upgrades to cert-validated once NTP syncs. | First-boot MITM on untrusted networks. Low risk on LAN. |
| MQTT on low-heap boards | Boards with < 40 KB max contiguous heap (CYD/WROOM) can't allocate for TLS cert context. They stay insecure permanently. | No cert validation on constrained boards. |
| Telegram Bot API | `setInsecure()` to avoid heap fragmentation that kills Telegram after 3 alerts. Bot tokens are bearer creds visible to a MITM. | Low risk on trusted upstream. |
| OTA without `/ca.crt` | If `/ca.crt` is missing, OTA manifest + binary download proceed without cert validation. SHA256 covers binary integrity but the manifest itself is unverified. | Manifest substitution possible. Always deploy with `/ca.crt`. |

### MQTT CLI trust model

`cli/lua.exec` runs arbitrary Lua with the full standard library (including `io` and `os`). Anyone with MQTT broker credentials can read `/config.json` (contains WiFi, MQTT, Telegram credentials in plaintext), overwrite `/ca.crt`, or access the filesystem. MQTT broker credentials therefore gate everything on the device - treat them with the same trust level as local root access.

### LiteServer (CYD) auth notes

- In AP mode (fallback setup): auth is skipped entirely so the user can configure WiFi. Anyone in radio range of the AP can read/write config.
- Empty web credentials: if `web.user` and `web.password` are both empty in config.json, LiteServer admin endpoints are unprotected. A warning is logged.

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

- **Every push to `dev` or `main`**: builds all 5 board targets (owb, cyd, wroom, eth, s3bare) + minimal firmware, uploads as artifacts
- **Push to `main` with new version**: auto-creates GitHub release with binaries + changelog
- **Existing version**: skips release (no duplicates)
- Rescue envs (`esp32-owb-rescue`, `esp32-s3-debug-rescue`) are not built by CI - manual builds only for recovery scenarios

**Git workflow:**
1. Develop on `dev` - CI catches compile errors on every push
2. When ready to release: bump `FIRMWARE_VERSION` in `thesada_config.h`, merge dev to main
3. CI builds and creates the GitHub release automatically
4. Production nodes pick up the new version via OTA

---

## Dependencies

| Library | Version | Purpose |
|---|---|---|
| Arduino framework (ESP32) | espressif32 @ 6.13.0 | Base framework |
| ArduinoJson | 7.4.3 | JSON config + event payloads |
| LittleFS | built-in | Filesystem (config, CA cert, Lua scripts) |
| PubSubClient | 2.8 | WiFi MQTT client |
| ESPAsyncWebServer | git (ESP32Async) | Web server + WebSocket (pulls AsyncTCP transitively) |
| ESP-Arduino-Lua | git | Lua 5.3 runtime (GPL-3.0) |
| TinyGSM | 0.12.0 | AT command modem driver |
| XPowersLib | git | AXP2101 PMU control |
| DallasTemperature + OneWire | 4.0.6 / 2.3.8 | DS18B20 sensors |
| Adafruit ADS1X15 | 2.6.2 | ADS1115 ADC |
| HTTPClient + WiFiClientSecure | built-in | OTA manifest fetch + TLS |
| mbedtls | built-in | SHA256 verification for OTA + config drift detection |

> **`espressif32` 6.13.0 requires `intelhex`** in the PlatformIO Python environment (used to build the bootloader). Install once:
> ```bash
> ~/.local/pipx/venvs/platformio/bin/python -m pip install intelhex
> ```
