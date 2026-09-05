---
title: Security & Dependencies
parent: Architecture
grand_parent: Firmware
nav_order: 8
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
| TLS | MQTT and OTA load the CA from `/ca.crt` on LittleFS. If that file is missing or empty, both subsystems fall back to a PROGMEM bundle baked into the firmware (common public TLS roots). The rotation path stays flash-based; the bundle is a safety net for wiped data partitions. See TLS exceptions below. |

**Token auth flow:**

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
| MQTT on low-heap boards | A board with less than ~40 KB max contiguous heap cannot allocate for the TLS cert context. The connection stays on `setInsecure()` permanently when the upgrade is unsafe. | No cert validation on constrained boards. |
| Webhook (operator endpoint) | Arbitrary URL configured by operator - no fixed CA to pin against by default. Uploading `/webhook-ca.crt` (endpoint root, self-signed included) switches the client to verified TLS; without it the client stays unverified. | Operator-chosen endpoint; treat as untrusted upstream unless a CA is uploaded. |

The Telegram Bot API client now validates against Go Daddy Root G2 (baked into `telegram_ca_progmem.h` with a `/telegram-ca.crt` LittleFS override, mirroring the OTA CA pattern). If no CA is available the request fails closed instead of falling back to `setInsecure()`, so bot tokens stop leaking over unverified TLS.

### MQTT client cert/key pair validation

`MQTTClient::validateClientCertKey` parses both PEMs and calls `mbedtls_pk_check_pair` before accepting them, so a mismatched cert + key (cert A + key B) is rejected at `cert.set` instead of failing later as an opaque TLS handshake error. Version-guarded for mbedtls 2.x and 3.x.

### MQTT CLI authorization

`MQTTClient::runCli` dispatches straight into the shell, so publish rights on a device's topic tree mean command execution. Every inbound CLI command is therefore authorized against how the broker session that carried it authenticated.

| Session auth | Command surface |
|---|---|
| Client certificate (mTLS) | every registered command |
| Password (shared onboarding credential) | `cert.set`, `cert.apply`, `cert.info`, `secret.set`, `restart`, `version`, `chip.info`, `heap` |
| Password, stored cert broken | the above plus `cert.clear` |
| Password, `config.set` | the key `mqtt.port` only |
| Password, `secret.set` | provisioning fields only: `mqtt.password`, `telegram.bot_token`, `web.password`, `wifi.ap_password`, `wifi.password:<ssid>` |
| Either mode, `config.set mqtt.port` | the value must parse as a decimal port in 1-65535 |

The password rows are exactly what the pairing and recovery flows need, and nothing that reads the filesystem, dumps config, or runs code - `lua.exec`, `fs.cat` and `config.dump` are out of reach on a password session. `cert.clear` opens only while the stored cert would not load or validate: a broken pair is worthless, so clearing it unstrands the device without widening anything else, and the permission closes again with the cert that granted it. `broker_url` is deliberately absent from the one writable config key: it is the repoint-to-another-broker path. Command names case-fold exactly as the shell dispatches them.

The value rule sits on both rows because it is not an authorization question. `config.set` stores what it is handed, so `mqtt.port 8884}` saved verbatim strands the device at its next reload whoever sent it. A bare `config.set mqtt.port` with no value is left alone - the command answers with its usage line and writes nothing.

The mode is a property of the session that spoke, frozen at dispatch rather than read when the deferred ring drains, and each transport carries its own answer: a device that failed over from a WiFi mTLS session to a cellular password session must not carry the mTLS verdict onto the password path. Password is the default in every ambiguous case. A denied command answers on `<prefix>/cli_response` with `ok: false` and `Denied: not permitted on this connection`, and logs `mqtt.cli_denied cmd=<cmd> auth=<mode>`.

Serial and the HTTP/WebSocket surfaces are not gated by this: serial implies physical access, and HTTP has its own admin auth. A build with `MQTT_TLS` undefined (the local plaintext-broker escape hatch) has no per-device identity to gate on, so the gate is a no-op there.

This is authorization, not device authentication. A leaked per-device certificate still gets the full surface; the CLI carries no signature and no replay protection.

### Lua sandbox

`cli/lua.exec` runs arbitrary Lua, and is reachable only on an mTLS session (see above). The Lua sandbox blocks `io`, `os`, `debug`, `package`, `require`, `dofile`, `loadfile`, `load`, and `loadstring` (nil after `luaL_openlibs`), so even there it is not `io.open("/config.json"):read("*a")`. The safe subset is `_G`, `math`, `string`, `table`, `utf8` plus the firmware bindings (`Config`, `MQTT`, `Node`, `EventBus`, `JSON`, `Log`, optional module-provided libs).

A leaked per-device certificate is still a sensitive surface - it gives a remote attacker arbitrary Lua and any firmware binding (write Config, send Telegram, and so on). Treat one with the same trust level as a privileged on-device shell, not full root.

### Device identity

First boot derives a `device_id` from the full six-byte factory MAC and mints an Ed25519 keypair. Both live in their own NVS namespace, `thesada-ident`, separate from the `secret.*` store.

| Property | Value |
|---|---|
| NVS namespace | `thesada-ident` |
| Device id shape | `thesada-` plus 12 lowercase hex digits of the factory MAC |
| CLI reach | `identity.info` / `chip.info` print the id and public key, `identity.reset --yes` erases the pair; no `secret.*` field maps to this namespace and nothing prints or accepts the private key |
| Private key exposure | loaded, used, and zeroized inside the signing call; never printed by any command |
| Rescue builds | read the stored id and key, never mint or sign |

The id uses all six MAC bytes rather than a suffix, because Espressif assigns sequentially and a short suffix collides across manufacturer prefixes. Writes go secret key, public key, then id, and the load path gates on the id, so a write interrupted midway reads back as absent and regenerates cleanly rather than yielding half an identity. An all-zero key read is treated the same way.

`identity.info` and `chip.info` report the id and the public key. Neither prints the private half. `identity.reset --yes` wipes the pair and reboots to mint a new one; anything that trusted the old public key has to be re-paired.

Reset does not touch the mTLS client certificate. That lives in its own namespace and only `cert.clear` removes it, so a paired unit keeps broker access across an identity reset and the app must revoke the certificate separately. Reset invalidates possession proofs, not an already-issued certificate.

The keypair is what proves possession when a device is claimed: the app issues a single-use challenge, the device signs it, and the holder of the public key verifies the signature. See [Web App Provisioning]({{ site.baseurl }}/app/provisioning.html).

### Captive-portal auth notes

- The fallback AP refuses to start unless `wifi.ap_password` is present, at least 8 characters, and not the shipped `changeme` placeholder. It never falls back to an open AP. See [Connectivity]({{ site.baseurl }}/firmware/architecture/connectivity.html).
- Admin auth is the same in AP mode as on a normal network: the portal serves the public dashboard routes, and the Config tab still needs `web.password`. Anyone who holds the AP passphrase reaches the device, which is why the passphrase is per device and seeded at flash time.
- Default or empty `web.password` refuses the whole authenticated surface rather than opening it. `changeme`, an absent key, and an explicit `""` all count as default, and the veto beats a Bearer token too, so a token minted before a password reset cannot outlive the reset. The refusal logs `web.admin_refused reason=default_password`, throttled to one line a minute.

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

- **Every push to `dev` or `main`**: builds the production OWB binary plus the debug variants (`esp32-owb`, `esp32-owb-debug`, `esp32-s3-debug`) and uploads them as artifacts.
- **Push to `main` with a new version**: auto-creates a GitHub release with the production binary, the rescue binary, and a manifest pointer.
- **Existing version**: release step is skipped (no duplicates).
- Rescue envs (`esp32-owb-rescue`, `esp32-s3-debug-rescue`) are built on demand only - manual recovery flow.

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
| libsodium | built-in | Ed25519 keypair for device identity (~97 KB of flash; compiled out of rescue builds) |

> **`espressif32` 6.13.0 requires `intelhex`** in the PlatformIO Python environment (used to build the bootloader). Install once:
> ```bash
> ~/.local/pipx/venvs/platformio/bin/python -m pip install intelhex
> ```
