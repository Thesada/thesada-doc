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

### Request correlation

Multiple in-flight CLI commands share the single `cli/response` topic. To match a response to the request that issued it, wrap the published payload in a JSON envelope with a caller-supplied `req_id`:

```json
{"req_id": "abc-123", "args": "/sd/log042.csv 0 256"}
```

The firmware unwraps `args` and dispatches the command with that as the raw payload, then echoes `req_id` back on every response message:

```json
{
  "cmd": "fs.cat",
  "req_id": "abc-123",
  "ok": true,
  "total": 22,
  "offset": 0,
  "length": 22,
  "done": true,
  "data": "timestamp,sensor,data\n"
}
```

Envelope rules:

- `req_id` may be a string or a number.
- `args` may be omitted, an empty string, or a string. With no `args` (or `args=""`), the command runs as if invoked argless.
- Any other top-level field is ignored.
- A payload that is not JSON, or JSON without `req_id`/`args`, is treated as the literal command argument. Plain-payload clients keep working unchanged.

Binary protocols (`fs.write`, `fs.append`, `cert.set`) read the raw payload directly and do not accept the JSON envelope. Use them without wrapping; correlation in those cases relies on per-device serialization at the client.

## Command groups

- [Core](#core) - help, version, restart, heap, uptime, sensors, selftest, sleep
- [Filesystem](#filesystem) - fs.ls, fs.cat, fs.rm, fs.write, fs.append, fs.mv, fs.df, fs.format
- [Config](#config) - config.get, config.set, config.save, config.reload, config.dump
- [Network](#network) - net.ip, net.ping, net.ntp, net.mqtt, net.http
- [OTA](#ota) - ota.check, ota.status
- [Certificates](#certificates) - cert.info, cert.apply, cert.clear
- [Cellular](#cellular) - cell.at, cell.reset, cell.cert.test, cell.cert.dump, cell.smconn.test
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

Filesystem commands resolve the backing filesystem from a path prefix. The default backing is LittleFS; the SD module registers `/sd` at boot so paths starting with `/sd/` (or the bare prefix `/sd`) route to the SD card.

```text
fs.ls /             # LittleFS root
fs.ls /sd           # SD card root
fs.cat /config.json
fs.cat /sd/log042.csv
```

Path validation runs before resolution. Any path containing `..` or `//` is rejected on every transport, so `/sd/../config.json` is refused before the prefix is even considered. The same policy is enforced for the MQTT binary handlers (`fs.write`, `fs.cat` chunked).

### fs.ls

List a directory.

```text
fs.ls                # list /
fs.ls /scripts       # list a subdirectory
fs.ls /sd            # SD card root
```

### fs.cat

Print a text file. Two modes:

- **Line-by-line** (serial / WebSocket): `fs.cat <path>` prints the whole file, one line per output frame.
- **Chunked** (MQTT only): `fs.cat <path> <offset> <length>` returns a JSON envelope with `offset`, `length`, `total`, `done`, and `data` fields. Use this from any client that needs to read a file larger than the MQTT response buffer; loop until `done=true`. Works against both `/` (LittleFS) and `/sd/` (SD card) paths.

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

Print LittleFS used / total / free in bytes. SD card capacity is reported separately by the SD module via `module.status`.

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

The `net.*` commands route by active transport. With WiFi up they use the WiFi stack; with WiFi down and cellular up they fall back to the modem so they keep working on the cellular leg.

### net.ip

Print every active transport. The WiFi block shows SSID, IP, gateway, DNS, RSSI, and MAC. When cellular is connected a separate block shows operator, modem IP, signal quality, and IMEI. Both blocks appear when both transports are up - no claim is made about which one the OS routes through.

### net.ping

Resolve a hostname and report its IP. Pure DNS check; does not actually ICMP-ping (LittleFS firmware does not ship a raw socket layer). With WiFi up the resolve goes through the WiFi DNS stack; with WiFi down it uses the cellular modem DNS instead. The output notes which transport carried the resolve.

```text
net.ping mqtt.example.com
```

### net.ntp

Without arguments, prints NTP server pool, last sync time, and clock skew at last sync.

```text
net.ntp                                 # status
net.ntp set 1730000000                  # set clock from epoch (test override)
net.ntp set 2026-04-30T20:00:00Z        # set clock from ISO 8601
net.ntp sync                            # force a sync now
```

Manual sets are intended for bench setup before the network is up; the regular NTP pull will overwrite once the device gets connectivity. `net.ntp sync` forces a sync immediately - over WiFi the background SNTP client already handles this, but on a cellular-only boot (WiFi never associated) nothing syncs the clock until the modem is asked, so `net.ntp sync` is the recovery path. The cellular sync timeout is configurable via `ntp.cell_timeout_s` (default 60).

### net.mqtt

Print the live MQTT state: broker, port, connection state, the transport currently carrying the session (WiFi or cellular), last publish timestamp, queue depth, and every active subscription (topic + ring-buffer latest received).

### net.http

HTTPS GET against a URL, routed by active transport: WiFi up uses `HTTPClient` over `WiFiClientSecure` with the CA loaded from `/ca.crt`; WiFi down with cellular up uses the modem SSL socket. Prints the status code, body length, and the first 1 KB of the body as a preview.

```text
net.http https://ota.example.com/latest/firmware.json
net.http --insecure http://192.0.2.10/healthz   # plain HTTP / skip cert check
```

HTTPS only by default - plain HTTP is refused unless `--insecure` is passed. The cellular path is HTTPS only. This replaces the need to walk an OTA manifest fetch by hand to test an HTTPS endpoint, and is the single HTTPS-GET command - there is no separate cellular variant, `net.http` auto-routes. The WiFi fetch runs on a dedicated task - the TLS handshake needs more stack than the shell's main-loop call path has.

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

## Cellular

Available only when the firmware was built with the cellular module enabled (`-DENABLE_CELLULAR`). The cell module talks AT to a SIM7080G modem over UART; commands here are operator-facing diagnostics, not the runtime publish path.

### cell.at

Send a raw AT command to the modem and capture the response lines.

```text
cell.at AT+CSQ          # signal quality
cell.at AT+COPS?        # current operator
cell.at AT+CGNSPWR=1    # enable GNSS power
```

Each invocation acquires the modem AT bus mutex for the duration, so a long-running AT command blocks runtime telemetry briefly. Use sparingly when the device is actively publishing.

### cell.reset

Power-cycle the modem via its DC3 enable pin (200 ms gap to drain the bulk caps; without the delay the modem latches state across the toggle). Equivalent to pulling the modem from the board and reseating it. Use after a failed PDP activation or when the modem stops responding to AT.

### cell.cert.test

Verify that the device's mTLS client certificate + private key are present in NVS and that the PEM round-trips through the modem's file-system upload path. Reads NVS, writes the PEM to the modem at `/customer/client.crt` + `/customer/client.key`, reads back, compares.

Cellular-debug command - only registered in builds with the `THESADA_CELL_DEBUG` flag (the `esp32-owb-debug` bench env). Not present in production builds.

### cell.cert.dump

Print the PEM stored in NVS for `client_cert` and `client_key`. Returns full PEM payload over MQTT cli response.

Cellular-debug command - only registered in builds with the `THESADA_CELL_DEBUG` flag (the `esp32-owb-debug` bench env). Not present in production builds.

### cell.smconn.test

Force a modem-native MQTT (SMCONN) connect attempt against the broker configured in `mqtt.broker` / `mqtt.port`, using the mTLS cert pair already written to the modem. Reports connect result + the modem's `+SMSTATE` register value. Use to isolate "cellular up, modem AT happy, but MQTT not connecting" from broader transport-layer faults.

Cellular-debug command - only registered in builds with the `THESADA_CELL_DEBUG` flag (the `esp32-owb-debug` bench env). Not present in production builds.

There is no `cell.http` command - HTTPS GET over the modem is reached through [net.http](#nethttp), which auto-routes WiFi vs cellular. The modem-side implementation (`Cellular::httpsGet`, CAOPEN / CASEND / CARECV) still backs the OTA cellular fallback and the `net.http` cellular branch.

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
