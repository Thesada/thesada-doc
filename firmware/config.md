---
title: Config Management
parent: Firmware
nav_order: 7
description: "config.json shape, save/reload workflow, drift detection via the SHA-256 hash trio in <prefix>/info, recovery and rollback."
---

# Config Management

Every Thesada device is configured by a single JSON file at `/config.json` on LittleFS. The Config module loads it at boot, exposes a JSON API to in-firmware readers (and to Lua via `Config.get`), and provides shell commands to read, write, save, and reload values without restarting the device.

## File location and lifecycle

- Path on LittleFS: `/config.json`.
- Loaded once at boot by `Config::begin()`.
- Held in memory as the live tree; queries hit RAM, not flash.
- Mutations stage in RAM and flush to flash on save.
- A reload re-reads from flash and replaces the in-memory tree atomically (the old tree stays valid until the new one fully parses, then a swap happens).

If `/config.json` is missing on first boot, the firmware writes a minimal default and continues. If the file exists but fails to parse, the firmware logs an error and falls back to the in-memory default. Recovery requires either pushing a fresh config (chunked write) or reformatting LittleFS (`fs.format --yes`) and starting clean.

## Shape

```json
{
  "device": {
    "name": "owb",
    "friendly_name": "Off-Grid Well Booster",
    "heartbeat_s": 15
  },
  "wifi": {
    "networks": [
      { "ssid": "<ssid>", "password": "<password>" }
    ],
    "timeout_per_ssid_s": 10,
    "wifi_check_interval_s": 900
  },
  "ntp": {
    "server": "pool.ntp.org",
    "tz_offset_s": 0
  },
  "mqtt": {
    "broker": "<broker-host>",
    "port": 8883,
    "user": "<username>",
    "password": "<password>",
    "topic_prefix": "thesada/owb",
    "ha_discovery": true,
    "buffer_in": 4096,
    "buffer_out": 4096
  },
  "ota": {
    "enabled": true,
    "manifest_url": "https://example.com/firmware/<board>.json",
    "check_interval_s": 21600
  },
  "web": {
    "enabled": true,
    "user": "admin",
    "password": "<password>"
  },
  "telegram": {
    "enabled": true,
    "bot_token": "<token>",
    "chat_ids": ["<id>"],
    "cooldown_s": 300
  },
  "temperature": {
    "enabled": true,
    "unit": "C",
    "buses": [ { "pin": 9 }, { "pin": 10 } ],
    "read_retries": 2,
    "max_delta_c": 40,
    "sensors": [
      { "name": "boiler", "address": "28-3c01a818..." }
    ]
  },
  "ads1115": {
    "enabled": true,
    "channels": [
      { "name": "house_pump", "mux": "A0_A1", "gain": 0.256, "clamp_a_per_v": 30 }
    ]
  },
  "battery": { "enabled": true },
  "sht31":   { "enabled": true, "sda": 11, "scl": 12, "address": 68, "interval_s": 30 },
  "sd": { "enabled": true, "pin_clk": 38, "pin_cmd": 39, "pin_data": 40, "max_file_kb": 1024 },
  "pwm": { "enabled": true, "pin": 16, "frequency_hz": 25000, "channel": 0, "resolution": 8 },
  "sleep": { "deep_sleep_minutes": 0 }
}
```

Within a section, individual fields are optional and fall back to the firmware's compile-time default. But whether a module runs at all is governed by its `enabled` key - see below.

## Module activation

Compiling a module into the firmware does not run it. Each module reads its own `enabled` flag at boot and stays completely dark - no hardware probe, no handlers, no log lines - unless activated. Modules fall into two tiers that differ only in what an **absent** `enabled` key means:

- **Core** - `wifi`, `mqtt`, `ota`, `heartbeat`, `cellular`, `power`. Default **on**. An absent key means the module runs; set `"enabled": false` to turn one off. This is how `"wifi": { "enabled": false }` forces a device onto the cellular transport without removing WiFi credentials.
- **Optional** - `temperature`, `ads1115`, `battery`, `sht31`, `sd`, `pwm`, `telegram`, `web`, `lua`, `gnss`. Default **off**. An absent or `false` key means the module never inits. You must set `"enabled": true` to activate it, in addition to any other fields that section needs.

So a minimal config is just `device`, `wifi`, and `mqtt` - and on such a device every optional module is off. To enable an optional sensor or service, add its section with `"enabled": true`.

The recovery shell (serial/MQTT CLI) is always available and has no `enabled` gate - a bad config can never lock you out of it.

> **Upgrading from a firmware build before module gating**: optional modules used to run whenever they were compiled in and their section was present. They now require `"enabled": true`. Before flashing, add the key to every optional section a device actively uses (commonly `web` for the dashboard, plus whatever sensors it carries), or that module will go silent after the update. Core sections need no change.

You can confirm what is actually running on a device with `module.status` over the shell - gated-off modules report `disabled`.

## Reading config

### Shell

```text
config.get device.name
config.get mqtt.broker
config.get temperature.unit
config.get temperature.sensors.0.name   # array index by number
config.dump                              # print the whole tree
```

`config.get` walks dot-notation; integers in the path are treated as array indices. Returns `null` for missing keys without raising an error.

### From Lua

```lua
local prefix = Config.get("mqtt.topic_prefix")
local unit   = Config.get("temperature.unit") or "C"
```

See [Lua Scripting - Config](lua-scripting.html#config) for the full binding semantics. Lua reads return strings for complex subtrees; parse with `JSON.decode` if you need a table.

## Writing config

Two modes: scalar update via `config.set`, or whole-file push via `fs.write`.

### Scalar update

```text
config.set mqtt.broker "<broker-host>"
config.set sleep.deep_sleep_minutes 15
config.set telegram.cooldown_s 600
```

`config.set` parses the value as JSON: bare strings need quotes, booleans and numbers do not. The save + reload sequence is atomic - a value that fails to parse leaves the live config untouched.

This is the right path for small operational changes (tweak a threshold, swap a broker hostname).

### Whole-file push

For larger reconfigurations (rewriting `temperature.sensors`, adding a new module section, or initial provisioning), push the whole file via the chunked-write contract and reload:

```bash
# Build payload: path + newline + content bytes
printf '/config.json\n' > /tmp/payload.bin
cat new-config.json     >> /tmp/payload.bin

mosquitto_pub -t '<prefix>/cli/fs.write' -f /tmp/payload.bin
mosquitto_pub -t '<prefix>/cli/config.reload' -m ''
```

See [Chunked File I/O](chunked-io.html) for the full write contract and the chunk-size math.

### Save and reload

`config.set` saves and reloads automatically. The save and reload commands exist as separate primitives for cases where you want explicit control:

```text
config.save     # flush in-memory tree to /config.json
config.reload   # re-parse /config.json from flash, replace live tree
```

After a `fs.write` that overwrote `/config.json` directly, you must `config.reload` to pick up the new content - the firmware does not watch the file.

## Drift detection

The firmware publishes a JSON blob to `<prefix>/info` (retained) on every successful MQTT connect AND re-emits it after any operation that mutates the live state - `config.reload`, `cert.apply`, or anything else that drives `MQTTClient::publishDeviceInfo`. Three SHA-256 hashes accompany the device metadata:

```json
{
  "firmware_version":   "x.y.z",
  "config_hash":        "a3b1d9...",
  "scripts_main_hash":  "c4d2e8...",
  "scripts_rules_hash": "0000...00"
}
```

Each hash covers the on-disk file bytes:

- `config_hash` over the bytes of `/config.json` as the file lives on LittleFS.
- `scripts_main_hash` over `/scripts/main.lua`.
- `scripts_rules_hash` over `/scripts/rules.lua`.

Hashing the file bytes (rather than re-serialising the in-memory tree) means the value is byte-for-byte comparable with what `fs.cat /config.json` returns. A management process can pull the file, sha256 it locally, and compare without worrying about JSON whitespace, key ordering, or numeric formatting drift.

Files that do not exist hash to a placeholder (zero-length string SHA, then by convention `0000...00`).

This is the simplest possible drift signal: a management process keeps a known-good hash for each device and watches `<prefix>/info`. The retained publish means a fresh subscriber catches up to the latest state on connect without waiting for the next emit. If the hash drifts, either:

- Someone pushed a config or script directly without going through the management process. Investigate.
- The file was corrupted or partially written. Recover by re-pushing the known-good content.
- The known-good hash was updated upstream but the device has not pulled yet.

The hashes are not authentication - a device can publish whatever it computes. Treat the signal as observability, not enforcement.

### Forced republish after a config push

When a management process pushes a new `/config.json` via the chunked-write path and follows up with `config.reload`, the firmware re-emits `<prefix>/info` immediately after the reload completes. Subscribers see the new hash in the same round trip; no need to wait for the next regular publish or to disconnect/reconnect.

A `config.reload` issued without preceding writes also re-emits `/info`. This is the cheapest way to ask a device "what is your current hash" when the retained payload may have gone stale because of a broker restart that lost retained state.

## Recovery patterns

### Reset config to defaults without losing the cert

```text
fs.rm /config.json
restart
```

The mTLS client cert + key live in NVS, separate from `/config.json`, so this preserves pairing. The firmware writes a fresh default config on next boot. A LittleFS reformat (`fs.format --yes`) wipes scripts too, so prefer the targeted `fs.rm` for config-only resets.

### Roll back to a previous config

The firmware does not keep on-device snapshots of `/config.json`. If you need rollback, a management process needs to keep its own history and re-push the old version via the chunked-write path.

### Push from a remote management process

Out-of-band push pattern, suitable for bootstrap and full-config deploys:

```bash
# 1. Compute new SHA-256 (so you know what to expect post-deploy)
sha256sum new-config.json

# 2. Push via chunked write
printf '/config.json\n' > /tmp/payload.bin
cat new-config.json     >> /tmp/payload.bin
mosquitto_pub -t '<prefix>/cli/fs.write' -f /tmp/payload.bin

# 3. Trigger reload (republishes /info on completion)
mosquitto_pub -t '<prefix>/cli/config.reload' -m ''

# 4. Verify the freshly republished info has the expected hash
mosquitto_sub -t '<prefix>/info' -W 5 -C 1 | jq '.config_hash'
```

`config.reload` triggers an immediate `/info` republish, so the verify step returns within a second of the reload landing.

If the new hash does not match, the device either did not pick up the file (writer failure) or the file failed to parse (logged error, live config untouched). Re-push and retry.

Binary write handlers (`fs.write`, `fs.append`) read the payload raw, so the JSON envelope form is not available there. Wrap the `config.reload` request instead so a follow-up `/info` confirmation can be matched to this push:

```json
Topic:   <prefix>/cli/config.reload
Payload: {"req_id":"<uuid>"}
```

See [CLI Reference - Request correlation](cli-reference.html#request-correlation).

## Common pitfalls

- **Forgetting `config.reload` after `fs.write`**: the file on flash is new but the in-memory tree is old, so the device keeps running with the previous values. The retained `<prefix>/info` on the broker also still shows the previous `config_hash` because `/info` only republishes on connect or after a `config.reload`. Always follow `fs.write /config.json` with `config.reload` so both the live config and the public hash advance together.
- **Quoting in `config.set`**: values are parsed as JSON. `config.set device.name foo` writes the string `foo` as JSON-parsed (works because bare-word JSON is permissive in some parsers, but rely on quoting for safety). Always quote string values.
- **Whole-tree replacement via `config.set`**: not supported. `config.set` is scalar-only. Use `fs.write` + `config.reload` for sub-trees.
- **Secrets in `config.json`**: WiFi passwords, MQTT credentials, Telegram bot tokens, and the web admin password all live in plain JSON on LittleFS. Treat the file as a secret. NVS-only storage is reserved for the per-device mTLS client cert + key.
- **Heartbeat field**: `device.heartbeat_s` controls some periodic publishes; reading it as a tunable for sensor intervals is wrong. Per-module sensor intervals are in their own sections (`sht31.interval_s`, `temperature.interval_s`, etc).

## See also

- [CLI Reference - Config](cli-reference.html#config) for full command syntax.
- [Chunked File I/O](chunked-io.html) for whole-file pushes.
- [MQTT Topics - `<prefix>/info`](mqtt-topics.html#prefixinfo) for the drift-hash payload shape.
- [Lua Scripting - Config](lua-scripting.html#config) for read access from scripts.
