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
    "user": "admin",
    "password": "<password>"
  },
  "telegram": {
    "bot_token": "<token>",
    "chat_ids": ["<id>"],
    "cooldown_s": 300
  },
  "temperature": {
    "unit": "C",
    "sensors": [
      { "name": "boiler", "address": "28-3c01a818..." }
    ]
  },
  "ads1115": {
    "channels": [
      { "name": "house_pump", "channel": 0, "ratio": 30.0 }
    ]
  },
  "battery": { "enabled": true },
  "sht31":   { "enabled": true, "sda": 11, "scl": 12, "address": 68, "interval_s": 30 },
  "sd": { "pin_clk": 38, "pin_cmd": 39, "pin_data": 40, "max_file_kb": 1024 },
  "pwm": { "pin": 16, "frequency_hz": 25000, "channel": 0, "resolution": 8 },
  "sleep": { "deep_sleep_minutes": 0 }
}
```

Sections are optional. A field absent from `/config.json` falls back to the firmware's compile-time default, so a minimal usable config is just `device`, `wifi`, and `mqtt`. Other sections only need to appear when their module is enabled and you want to override defaults.

Module-specific sections (`temperature`, `ads1115`, `battery`, `sht31`, `sd`, `pwm`, `telegram`, `sleep`) are read by their respective modules at `begin()`; missing sections leave the module on its compiled defaults.

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

Every connect, the firmware publishes a JSON blob to `<prefix>/info` (retained) that includes three SHA-256 hashes:

```json
{
  "firmware_version": "1.3.11",
  "config_hash":        "a3b1d9...",
  "scripts_main_hash":  "c4d2e8...",
  "scripts_rules_hash": "0000...00"
}
```

Each hash covers the full file content - `config_hash` over the JSON-serialized live tree, `scripts_main_hash` over `/scripts/main.lua`, `scripts_rules_hash` over `/scripts/rules.lua`. Files that do not exist hash to a placeholder (zero-length string SHA, then by convention `0000...00`).

This is the simplest possible drift signal: a management process keeps a known-good hash for each device and watches `<prefix>/info`. If the hash drifts, either:

- Someone pushed a config or script directly without going through the management process. Investigate.
- The file was corrupted or partially written. Recover by re-pushing the known-good content.
- The known-good hash was updated upstream but the device has not pulled yet.

The hashes are not authentication - a device can publish whatever it computes. Treat the signal as observability, not enforcement.

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

# 3. Trigger reload
mosquitto_pub -t '<prefix>/cli/config.reload' -m ''

# 4. Verify the next info publish has the expected hash
mosquitto_sub -t '<prefix>/info' -W 30 -C 1 | jq '.config_hash'
```

If the new hash does not match, the device either did not pick up the file (writer failure) or the file failed to parse (logged error, live config untouched). Re-push and retry.

## Common pitfalls

- **Forgetting `config.reload` after `fs.write`**: the file on flash is new but the in-memory tree is old. Drift hash will eventually show the change after the next reload triggers, not on the spot.
- **Quoting in `config.set`**: values are parsed as JSON. `config.set device.name foo` writes the string `foo` as JSON-parsed (works because bare-word JSON is permissive in some parsers, but rely on quoting for safety). Always quote string values.
- **Whole-tree replacement via `config.set`**: not supported. `config.set` is scalar-only. Use `fs.write` + `config.reload` for sub-trees.
- **Secrets in `config.json`**: WiFi passwords, MQTT credentials, Telegram bot tokens, and the web admin password all live in plain JSON on LittleFS. Treat the file as a secret. NVS-only storage is reserved for the per-device mTLS client cert + key.
- **Heartbeat field**: `device.heartbeat_s` controls some periodic publishes; reading it as a tunable for sensor intervals is wrong. Per-module sensor intervals are in their own sections (`sht31.interval_s`, `temperature.read_interval_s`, etc).

## See also

- [CLI Reference - Config](cli-reference.html#config) for full command syntax.
- [Chunked File I/O](chunked-io.html) for whole-file pushes.
- [MQTT Topics - `<prefix>/info`](mqtt-topics.html#prefixinfo) for the drift-hash payload shape.
- [Lua Scripting - Config](lua-scripting.html#config) for read access from scripts.
