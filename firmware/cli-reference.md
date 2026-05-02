---
title: CLI Reference
parent: Firmware
nav_order: 3
description: "Complete reference for every thesada-fw shell command, available across serial, WebSocket, and MQTT transports."
---

# CLI Reference

Every shell command registered by the firmware. The same handler runs on every transport, so the syntax below works on serial, the `/ws/serial` WebSocket terminal, and the MQTT CLI bridge alike.

## How to invoke a command

**Serial** (115200 baud, USB or UART):

```text
> sensors all
[temp.boiler] 21.4 C
[battery.percent] 86 %
[wifi.rssi] -54 dBm
```

**WebSocket** at `ws://<device-ip>/ws/serial`. Same line-based protocol.

**MQTT** via the device's `cli/` bridge. Publish the command to `<topic_prefix>/cli/<command>`; payload is the argument string (empty for argless commands). The response lands on `<topic_prefix>/cli/response` as a JSON object.

```bash
# argless command
mosquitto_pub -t 'thesada/owb/cli/chip.info' -m ''

# command with arguments
mosquitto_pub -t 'thesada/owb/cli/ota.check' -m '--force'

# subscribe to the response before publishing
mosquitto_sub -t 'thesada/owb/cli/response' -v
```

Response shape:

```json
{
  "cmd": "chip.info",
  "ok": true,
  "output": [
    "ESP32-S3 rev 0  cores=2  flash=8 MB",
    "PSRAM: 8 MB octal SPI"
  ]
}
```

A command line longer than the MQTT 256-char buffer should be sent over the WebSocket terminal instead. The chunked file I/O commands (`fs.cat` with offset, `fs.write`) have their own MQTT contract so the wire payload stays small; see [Chunked I/O](#chunked-file-io) below.

## Command groups

- [Core](#core) - help, version, restart, heap, uptime, sensors, selftest, sleep
- [Filesystem](#filesystem) - fs.ls, fs.cat, fs.rm, fs.write, fs.append, fs.mv, fs.df, fs.format
- [Config](#config) - config.get, config.set, config.save, config.reload, config.dump
- [Network](#network) - net.ip, net.ping, net.ntp, net.mqtt, net.eth
- [OTA](#ota) - ota.check, ota.status
- [Certificates](#certificates) - cert.info, cert.apply, cert.clear
- [Boot and system](#boot-and-system) - boot.info, partitions, chip.info, sdkconfig
- [Modules](#modules) - module.list, module.status
- [Lua](#lua) - lua.exec, lua.load, lua.reload

## Core

### help

Show all registered commands with one-line help text. The output is the same data this reference is generated from.

### version

Print the firmware version, build timestamp, and the SHA of the bundled CA cert. Useful for confirming an OTA actually rolled forward.

### restart

Reboot the device. No confirmation - issued from MQTT, the response publishes before the actual restart so the operator sees a clean acknowledgement.

### heap

Print free heap, minimum free since boot, largest free contiguous block, and free PSRAM (where present). Reads the same numbers the periodic 5-minute heap telemetry publishes.

### uptime

Seconds since boot, plus a human-readable form (`6d 3h 12m`).

### sensors

Lists every sensor registered through `SensorRegistry`. Each entry has a name, a one-line description, and an enabled flag.

```text
sensors            # list
sensors <name>     # read one sensor
sensors all        # read every enabled sensor
```

Each module that exposes a sensor calls `SensorRegistry::add()` in its `begin()`, so the list reflects the modules compiled into the running firmware.

### selftest

Runs each module's `selftest` hook in registration order. Modules report their internal state (probe success, last sensor read, communication health). Used by post-flash bring-up.

### sleep

Inspect the SleepManager state: configured deep-sleep schedule, boot count since last hard reset, wake reason of the most recent boot. Read-only; sleep behavior is configured via `config.set sleep.*`.

## Filesystem

All paths are LittleFS-rooted unless prefixed with `/sd/`, in which case they go to the SD card via the SD module.

### fs.ls

List a directory.

```text
fs.ls                # list /
fs.ls /scripts       # list a subdirectory
```

### fs.cat

Print a text file. Two modes:

- **Line-by-line** (serial / WebSocket): `fs.cat <path>` prints the whole file, one line per output frame.
- **Chunked** (MQTT only): `fs.cat <path> <offset> <length>` returns a JSON envelope with `offset`, `length`, `total`, `done`, and `data` fields. Use this from any client that needs to read a file larger than the MQTT response buffer; loop until `done=true`.

### fs.rm

Remove a file. No globs, no recursion. `fs.rm <path>`.

### fs.write

Truncate-and-write a file with content from the command payload.

- **Serial / WebSocket**: `fs.write <path> <content>` (content is the rest of the line, single-line only).
- **MQTT**: payload format is `<path>\n<content>`. The first newline separates path from body. Multi-line content is preserved.

### fs.append

Same shape as `fs.write` but appends instead of truncating.

### fs.mv

Rename or move a file. `fs.mv <src> <dst>`.

### fs.df

Print LittleFS used / total / free in bytes, plus per-mountpoint stats for SD when the SD module is enabled.

### fs.format

Reformats the LittleFS partition. Confirmation gate: requires `--yes` argument. `fs.format` alone prints a warning and exits without doing anything. `fs.format --yes` actually wipes.

## Config

`config.json` lives on LittleFS. The Config module loads it at boot, exposes a JSON API to readers, and reloads from flash on `config.reload`.

### config.get

Read one key with dot-notation path. `config.get mqtt.broker` prints the value as JSON.

### config.set

Write one key, save to flash, reload in-place.

```text
config.set mqtt.broker "mqtt.example.com"
config.set sleep.deep_sleep_minutes 15
config.set telegram.enabled false
```

The value is parsed as JSON: bare strings need to be quoted, booleans and numbers do not. The save + reload happens atomically; a write that fails to parse leaves the live config untouched.

### config.save

Save the in-memory config to flash without changing it. Used after a sequence of `config.set` calls if you batched edits or after a programmatic mutation from Lua.

### config.reload

Re-read `config.json` from flash and replace the in-memory copy. Use after editing the file directly via `fs.write` if you skipped the `config.set` path.

### config.dump

Print the entire config as pretty-formatted JSON. Useful for a one-shot snapshot from MQTT.

## Network

### net.ip

Print every active interface (WiFi, Ethernet if present, cellular if connected). Each entry shows interface name, IP, gateway, DNS, and MAC.

### net.ping

Resolve a hostname and report its IP. Pure DNS check; does not actually ICMP-ping (LittleFS firmware does not ship a raw socket layer).

```text
net.ping mqtt.example.com
```

### net.ntp

Without arguments, prints NTP server pool, last sync time, and clock skew at last sync.

```text
net.ntp                                 # status
net.ntp set 1730000000                  # set clock from epoch (test override)
net.ntp set 2026-04-30T20:00:00Z        # set clock from ISO 8601
```

Manual sets are intended for bench setup before the network is up; the regular NTP pull will overwrite once the device gets connectivity.

### net.mqtt

Print the live MQTT state: broker, port, connection state, last publish timestamp, queue depth, and every active subscription (topic + ring-buffer latest received).

### net.eth

Available only when the firmware was built for an Ethernet board (`-DENABLE_ETH`). Prints PHY init state, link speed, IP, gateway, and last ETH-specific log line.

## OTA

### ota.check

Triggers an OTA check against the configured manifest URL.

```text
ota.check                       # standard check, only updates if version differs
ota.check --force               # force re-flash even if version matches
ota.check https://...firmware.json   # one-shot check against a different URL
ota.check --force https://...firmware.json
```

The actual download + flash + reboot sequence runs from the OTA module's loop on the main task, so this command returns immediately ("download started"). Watch `boot.info` after the device comes back to confirm.

### ota.status

Prints partition layout (running slot vs target slot), rollback state, last OTA result, and the SHA of the running image.

## Certificates

Per-device mTLS client certificate stored in NVS, separate from `config.json` so a factory reset of config does not wipe the cert. PEM-encoded; ECDSA P-256 keys + certs fit comfortably in the 4000-byte NVS blob limit.

### cert.info

Show stored cert metadata: CN, serial number (hex), notBefore, notAfter, issuer CN, and live status (inactive / active / about to expire).

### cert.apply

If both halves of the cert+key are present in NVS, schedules a deferred reboot ~3 seconds out so the response can publish before the restart. Post-reboot, the firmware connects with mTLS and uses the cert CN as the MQTT username.

### cert.clear

Erase the stored cert + key from NVS. Connection falls back to password auth on the next reconnect.

## Boot and system

### boot.info

Last reset reason (raw + decoded), boot count, time since last hard reset, wake reason if the previous reset came out of sleep.

### partitions

Full partition table dump - same data the bootloader sees. Useful for confirming the OTA layout matches what the firmware expects.

### chip.info

Chip family + revision, core count, flash size, PSRAM presence and size, security e-fuses set.

### sdkconfig

A curated subset of the IDF `CONFIG_*` keys that affect boot behavior, OTA, mbedtls record size, and partition layout. Not the full sdkconfig - just what is operationally relevant.

## Modules

### module.list

List every module compiled into the firmware, with an enabled flag (`[x]` enabled, `[ ]` compiled but disabled at runtime). Disabled modules cost no flash beyond the symbol table; the `#ifdef ENABLE_*` guards in each module compile to empty translation units when their flag is off.

### module.status

Each module reports a one-line health string. Format is module-specific; common entries cover last successful operation, error counter, and any retry / cooldown state.

## Lua

### lua.exec

Execute a string of Lua against the live runtime. Multi-line bodies arrive as a single argument; quote them or use the MQTT path which preserves newlines.

```text
lua.exec print(2 + 2)
lua.exec for i=1,5 do print(i) end
```

### lua.load

Run a Lua file from LittleFS. `lua.load /scripts/test.lua`.

### lua.reload

Re-load every script under `/scripts/` in load order (`alerts.lua`, `rules.lua`, `display.lua` where present). Used after `fs.write` or a config update; no reboot needed.

## Chunked file I/O

Two commands accept large payloads via a chunked MQTT contract so the wire stays under the broker's per-message limit:

- **`fs.cat <path> <offset> <length>`** for reads.
- **`fs.write <path>\n<content>`** and **`fs.append <path>\n<content>`** for writes.

Read example, pulling an 80 KB file in 4 KB chunks:

```bash
offset=0
while :; do
  resp=$(mosquitto_pub -t 'thesada/owb/cli/fs.cat' -m "/scripts/main.lua $offset 4096")
  # ... parse JSON, append data, advance offset by length, stop when done==true
done
```

The response envelope:

```json
{
  "cmd": "fs.cat",
  "ok": true,
  "total": 81920,
  "offset": 4096,
  "length": 4096,
  "done": false,
  "data": "..."
}
```

Writes are pushed in a single payload (no chunking on the write path); the MQTT broker's max message size sets the upper bound. For larger writes use the WebSocket terminal which has no per-line cap beyond the underlying frame size.

## Adding new commands

Modules register their own commands in `begin()`:

```cpp
Shell::registerCommand("name", "one-line help text",
  [](int argc, char** argv, ShellOutput out) {
    out("response line");
    out("another line");
  });
```

There is no central registry to edit - the module owns its command surface. Register before any caller tries to invoke (boot priority is set in the module's `MODULE_REGISTER(..., PRIORITY_*)` macro).
