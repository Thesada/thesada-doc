---
title: MQTT Topics
parent: Firmware
nav_order: 4
description: "Every MQTT topic the firmware publishes or subscribes to, payload shapes, retained vs live, QoS, and Home Assistant discovery layout."
---

# MQTT Topics

Reference for every topic a thesada-fw device touches. Use this when wiring up dashboards, building integrations, or auditing what the device sends.

## Topic prefix

Each device has a configured **topic prefix** that anchors every topic it owns. The prefix lives at `mqtt.topic_prefix` in `config.json`; default is `thesada/node`.

Two shapes are common in deployments:

| Shape | Example prefix | When to use |
|---|---|---|
| 3-tier legacy | `thesada/owb` | Single-tenant deployments. Older firmware defaults. |
| 4-tier | `thesada/<tenant>/<device>` | Multi-tenant deployments. Tenant slug is the second segment, device name third. |

The firmware does not care which shape you pick - the prefix is opaque to it. The wider Thesada platform parses 4-tier prefixes to route by tenant; standalone deployments work fine with 3-tier.

In every section below, `<prefix>` stands for whatever this device's prefix is.

## At a glance

| Topic | Direction | Retained | QoS | When |
|---|---|---|---|---|
| `<prefix>/status` | publish | yes | 0 | LWT `offline`; `online` on connect |
| `<prefix>/info` | publish | yes | 0 | Once per connect |
| `<prefix>/info/retained_topics` | publish | yes | 0 | Once per connect, debounced re-emit on late additions |
| `<prefix>/sensor/<kind>/<name>` | publish | no | 0 | Per sensor read interval |
| `<prefix>/alert` | publish | no | 0 | Per fired alert |
| `<prefix>/status/ota` | publish | no | 0 | OTA progress / outcome |
| `<prefix>/cellular/active` | publish | no | 0 | Cellular fallback toggled on |
| `<prefix>/cellular/rssi` | publish | no | 0 | Periodic during cellular session |
| `<prefix>/cli/<command>` | subscribe | no | 0 | Operator CLI invocation |
| `<prefix>/cli/response` | publish | no | 0 | Reply to a CLI invocation |
| `<prefix>/cmd/lua/reload` | subscribe | no | 0 | Hot-reload Lua scripts |
| `homeassistant/<component>/<dev>/<uid>/config` | publish | yes | 0 | HA autodiscovery, once per connect |

QoS 0 throughout: the Thesada device fleet trades guaranteed delivery for connection liveness. The firmware uses retained for state-of-the-world topics so a fresh subscriber catches up, and uses LWT for offline detection.

## Lifecycle topics

### `<prefix>/status`

Online / offline marker. The firmware sets the broker's Last Will and Testament to publish `offline` (retained) on disconnect, then publishes `online` (retained) on every successful connect. Subscribers see one of two payloads at any moment:

```text
online
offline
```

### `<prefix>/info`

Retained JSON blob describing the device. Published once per successful connect, and re-emitted after any operation that mutates the configuration (`config.reload`, `cert.apply`, etc) so subscribers see the new state in the same round trip.

```json
{
  "firmware_version": "x.y.z",
  "hardware_type": "esp32-s3",
  "board": "s3-bare",
  "chip_model": "esp32-s3",
  "chip_revision": 0,
  "chip_cores": 2,
  "mac": "48:27:e2:e8:b4:34",
  "psram": true,
  "build_time": "<build timestamp>",
  "config_hash": "a3b1...e2",
  "scripts_main_hash": "c4d2...8f",
  "scripts_rules_hash": "0000...00"
}
```

The three hash fields are SHA-256 of the on-disk file bytes - `config_hash` over `/config.json`, `scripts_main_hash` over `/scripts/main.lua`, `scripts_rules_hash` over `/scripts/rules.lua`. Use them for drift detection: if the hash you see on the broker disagrees with what your management database expects, the device is running a different config or script set than you think.

Hashing the on-disk file (not the re-serialised in-memory object) keeps the value byte-for-byte comparable with what a `fs.cat` of the same path would return. A management process can pull the file, sha256 it locally, and compare without worrying about whitespace, key ordering, or numeric formatting drift.

### `<prefix>/info/retained_topics`

Retained JSON array listing every topic this device currently retains on the broker. Built fresh on each connect; debounce-republished if a module retains a new topic after the initial connect.

```json
[
  "thesada/sht31/status",
  "thesada/sht31/info",
  "thesada/sht31/info/retained_topics",
  "homeassistant/sensor/sht31/sht31_sht31_temp/config",
  "homeassistant/sensor/sht31/sht31_sht31_humidity/config"
]
```

The point: when a device is decommissioned, the retained payloads it owns persist on the broker forever (that is what retained means). A management process can read this manifest, then publish empty retained payloads on each listed topic to clean up.

## Sensor topics

`<prefix>/sensor/<kind>/<name>` for per-sensor live readings. Payload is the bare value as a string; subscribers parse it as a number when they expect one.

| Topic shape | Example | Payload |
|---|---|---|
| `<prefix>/sensor/temperature/<name>` | `<prefix>/sensor/temperature/boiler` | `21.4` |
| `<prefix>/sensor/humidity/<name>` | `<prefix>/sensor/humidity/sht31` | `54.2` |
| `<prefix>/sensor/current/<name>` | `<prefix>/sensor/current/house_pump` | `2.31` |
| `<prefix>/sensor/power/<name>` | `<prefix>/sensor/power/house_pump` | `277.2` |
| `<prefix>/sensor/battery/percent` | (singleton) | `87` |
| `<prefix>/sensor/battery/voltage` | (singleton) | `4.012` |
| `<prefix>/sensor/battery/charging` | (singleton) | `Charging` / `Discharging` |
| `<prefix>/sensor/wifi/rssi` | (singleton) | `-54` |
| `<prefix>/sensor/wifi/ssid` | (singleton) | `MyWiFi` |
| `<prefix>/sensor/wifi/ip` | (singleton) | `192.168.1.50` |
| `<prefix>/sensor/heap/free` | (singleton) | `123456` |
| `<prefix>/sensor/heap/min_free` | (singleton) | `89012` |
| `<prefix>/sensor/heap/max_alloc_block` | (singleton) | `38400` |
| `<prefix>/sensor/heap/psram_free` | (singleton, PSRAM boards) | `4194304` |
| `<prefix>/sensor/uptime` | (singleton) | `12345` |
| `<prefix>/sensor/pwm` | (singleton, PWM boards) | `45` |
| `<prefix>/cellular/rssi` | (singleton, cellular boards) | `-83` |

Sensors are not retained: the value at any moment is the most recent publish, and a subscriber that joined late reads the next interval. Heap stats publish every 5 minutes; sensor reads follow each module's configured interval (`sensors[].interval_s`, `sht31.interval_s`, etc).

The `current/<name>` and `power/<name>` topics from the ADS1115 module also publish a roll-up payload on `<prefix>/sensor/current` and `<prefix>/sensor/power` for boards that aggregate.

Names come from the device's `config.json`. A sensor named "House Pump" in config slugifies to `house_pump` for the topic. Renaming a sensor changes the topic, which is intentional - the topic IS the name.

## Alerts

### `<prefix>/alert`

JSON payload, fired when a Lua alert rule matches.

```json
{
  "device": "owb",
  "alert_id": "boiler_overtemp",
  "severity": "crit",
  "message": "Boiler 78.4 C above 75 C threshold",
  "metric": "temperature.boiler",
  "value": 78.4,
  "ts": 1735000000,
  "free_heap": 184320
}
```

Severity is one of `info`, `warn`, `crit`. The `free_heap` field is the firmware's last sampled free heap at alert-publish time; useful when triaging whether an alert misfired during a low-heap period.

Cellular boards mirror alerts on the same topic via the cellular module's queue when WiFi is down, so subscribers do not need a separate cellular alert path.

### `<prefix>/status/ota`

JSON state events. Published on every OTA code path so operators can drive dashboards without watching serial. Not retained; the broker only holds rolling status while an OTA is in flight.

```json
{"state":"updating","version":"x.y.z"}
{"state":"up-to-date","version":"x.y.z"}
{"state":"refused","reason":"no-ca","version":"x.y.z"}
{"state":"failed","reason":"sha256-mismatch","version":"x.y.z"}
```

| `state` | Meaning | `reason` field |
|---|---|---|
| `updating` | Manifest fetched and a flash is in progress. | not present |
| `up-to-date` | Manifest matches the running version; nothing to do. | not present |
| `refused` | OTA aborted before the download started. | one of `no-transport`, `no-manifest-url`, `no-ca`, `heap-low`, `manifest-fetch-failed` |
| `failed` | Download or flash phase failed. | free-form short string |

`reason` values are kebab-case stable identifiers. Add new reasons by extending `publishOtaRefusal()` in `OTAUpdate.cpp`.

## CLI bridge

The firmware subscribes to `<prefix>/cli/#` so any topic under it is treated as a command. Topic suffix is the command name; payload is the argument string.

### Inbound: `<prefix>/cli/<command>`

Plain payload form (works on every firmware version):

```bash
mosquitto_pub -t 'thesada/owb/cli/chip.info' -m ''
mosquitto_pub -t 'thesada/owb/cli/ota.check' -m '--force'
mosquitto_pub -t 'thesada/owb/cli/config.set' -m 'sleep.deep_sleep_minutes 15'
```

Envelope form, useful when multiple CLI commands are in flight against the same device:

```bash
mosquitto_pub -t 'thesada/owb/cli/chip.info' -m '{"req_id":"abc-123"}'
mosquitto_pub -t 'thesada/owb/cli/ota.check' -m '{"req_id":"x42","args":"--force"}'
```

The firmware extracts `req_id` and echoes it back on every response message, and unwraps `args` so downstream handlers see the raw payload as if it had been published directly. A payload without `req_id` / `args` falls through and is treated as the literal command argument, so plain-payload clients keep working unchanged.

Some commands take multi-line payloads (`fs.write`, `fs.append`, `cert.set`) and are not envelope-compatible because the binary protocol reads the raw payload directly. See the [CLI Reference](cli-reference.html) for the per-command wire contracts.

### Outbound: `<prefix>/cli/response`

JSON envelope with the original command, success flag, and one entry per output line.

```json
{
  "cmd": "chip.info",
  "req_id": "abc-123",
  "ok": true,
  "output": [
    "ESP32-S3 rev 0  cores=2  flash=8 MB",
    "PSRAM: 8 MB octal SPI"
  ]
}
```

`req_id` appears in the response only when the inbound payload carried one. Subscribe before publishing to avoid missing the response (it is QoS 0 and not retained).

### `<prefix>/cmd/lua/reload`

The Lua module also subscribes to a fixed reload trigger separate from the CLI bridge. Publishing any payload (empty works) re-runs every script under `/scripts/` in load order. Equivalent to issuing `lua.reload` via the CLI.

## Home Assistant discovery

When `mqtt.ha_discovery: true` in `config.json` (default), the firmware publishes Home Assistant MQTT autodiscovery configs (retained) on connect. Topic shape:

```text
homeassistant/<component>/<device_id>/<unique_id>/config
```

`<component>` is the HA entity component (`sensor`, `binary_sensor`, etc - currently only `sensor` is used). `<device_id>` is the device's name from `config.json`. `<unique_id>` is per-entity, derived from the device id and a per-sensor suffix.

Each config payload references the sensor's state topic from the table above and an availability topic of `<prefix>/status`, so HA marks the entity unavailable when the device drops offline. Worked-out example for an SHT31 humidity sensor on a device named `sht31`:

```json
{
  "name": "SHT31 Humidity",
  "stat_t": "thesada/sht31/sensor/humidity/sht31",
  "uniq_id": "sht31_sht31_humidity",
  "avty_t": "thesada/sht31/status",
  "unit_of_meas": "%",
  "dev_cla": "humidity",
  "stat_cla": "measurement",
  "dev": {
    "ids": "sht31",
    "name": "SHT31 Test Node",
    "mf": "Thesada",
    "sw": "x.y.z"
  }
}
```

The firmware emits one of these per active sensor on connect: temperature, humidity, current, power, battery (percent / voltage / charging), wifi (rssi / ssid / ip), heap (free / min / max_alloc / psram), uptime, cellular (rssi). Disabling a module via build flags removes its discovery configs from the published set.

## Authentication and ACLs

The firmware connects with one of:

- **Username + password** from `config.json` `mqtt.user` / `mqtt.password`. The fallback path used by unpaired devices.
- **mTLS client certificate** stored in NVS. When present, `cert.apply` triggers a reconnect using the cert as identity (no username, no password). The broker maps the certificate CN onto the MQTT username via `use_identity_as_username`, so the connection arrives as if the device had logged in with username = CN.

ACLs live on the broker side via the Mosquitto dynamic-security plugin. Per-device pairing creates a role scoped to `<prefix>/#` plus the device's `homeassistant/...` discovery namespace. Operators wire those out of band; the firmware does not configure ACLs.

## Putting it together

A typical subscribe pattern for a single device:

```bash
mosquitto_sub -v -t 'thesada/owb/#'
```

For Home Assistant discovery on a single device:

```bash
mosquitto_sub -v -t 'homeassistant/sensor/owb/#'
```

For a tenanted multi-device deployment, the wider `thesada/#` works at the broker layer; combine with broker-side ACLs to scope by tenant.

To inspect what one device retains right now:

```bash
mosquitto_sub -t 'thesada/owb/info/retained_topics' -W 5 -C 1 | jq .
```
