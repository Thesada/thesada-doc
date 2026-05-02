---
title: Chunked File I/O
parent: Firmware
nav_order: 5
description: "Protocol for reading and writing device files larger than the MQTT buffer, via chunked fs.cat / fs.write / fs.append over the CLI bridge."
---

# Chunked File I/O

Device files (config, Lua scripts) routinely exceed the MQTT buffer size (typically 4096 bytes). The CLI bridge defines a chunked-transfer contract for reading and writing files in slices that fit a single MQTT publish.

## Buffer limits

| Parameter | Value | Set by |
|---|---|---|
| `mqtt.buffer_in` | 4096 (configurable, max 8192) | `config.json` |
| `mqtt.buffer_out` | 4096 (configurable, max 8192) | `config.json` |
| Shell parse buffer | 256 bytes | hardcoded in firmware |
| Max chunk size (read) | 2048 bytes | hardcoded in firmware |

`fs.write` and `fs.append` bypass the Shell parse buffer via a special-case path in the firmware's MQTT CLI handler. The effective max write payload is `buffer_in` minus path length minus one (newline separator) minus a small JSON envelope overhead.

## Chunked read

### Request

```text
Topic:   <prefix>/cli/fs.cat
Payload: <path> <byte_offset> <byte_length>
```

Example - read the first 2 KiB of a Lua script:

```text
Payload: /scripts/rules.lua 0 2048
```

### Response

```json
{
  "cmd": "fs.cat",
  "ok": true,
  "total": 3858,
  "offset": 0,
  "length": 2048,
  "done": false,
  "data": "-- owb alerts - hot-reload..."
}
```

| Field | Type | Meaning |
|---|---|---|
| `total` | int | Total file size in bytes |
| `offset` | int | Byte offset of this chunk |
| `length` | int | Actual bytes returned in this chunk |
| `done` | bool | `true` if this is the last chunk |
| `data` | string | File content for this chunk (JSON-escaped) |

### Read loop

```text
offset = 0
content = ""
loop:
  publish <prefix>/cli/fs.cat with payload "<path> <offset> 2048"
  wait for response on <prefix>/cli/response
  content += response.data
  if response.done: break
  offset += response.length
```

### Backward compatibility

`fs.cat <path>` without offset / length still works on the line-mode path: it returns the file line-by-line in the `output` JSON array of the response envelope. That mode silently truncates for files that exceed the response buffer, so the chunked path is the right choice for anything beyond a few KB.

## Chunked write

### First chunk (truncate)

```text
Topic:   <prefix>/cli/fs.write
Payload: <path>\n<content bytes>
```

Opens the file in write mode (`"w"`), truncating any existing content. The first `\n` byte in the payload separates the path from the body; everything after is written verbatim, including additional newlines.

### Subsequent chunks (append)

```text
Topic:   <prefix>/cli/fs.append
Payload: <path>\n<content bytes>
```

Opens the file in append mode (`"a"`), adding content to the end.

### Response (both commands)

```json
{
  "cmd": "fs.write",
  "ok": true,
  "output": ["Wrote 3868 bytes to /scripts/rules.lua"]
}
```

```json
{
  "cmd": "fs.append",
  "ok": true,
  "output": ["Appended 1200 bytes to /scripts/rules.lua"]
}
```

### Write loop

```text
chunk_size = 3900  # leaves room for path + newline + JSON envelope
chunks = split(content, chunk_size)

for i, chunk in chunks:
  cmd     = "fs.write" if i == 0 else "fs.append"
  payload = path + "\n" + chunk
  publish <prefix>/cli/<cmd> with payload
  wait for response
  if not response.ok: abort

# Reload step depending on what was written:
publish <prefix>/cli/lua.reload         # Lua scripts
publish <prefix>/cli/config.reload      # config.json
```

### Legacy alias

`cli/file.write` is kept as a backward-compatible alias for `cli/fs.write`. Both hit the same bypass path; new clients should use `fs.write`.

## Payload framing

The write payload is binary: the first `\n` byte separates the path from the content. Everything after is written byte-for-byte, including embedded newlines. This is why a payload built from a real file works without any escaping:

```bash
# Build the binary payload
printf '/scripts/rules.lua\n' > /tmp/payload.bin
cat alerts.lua                >> /tmp/payload.bin

# Publish
mosquitto_pub -h <broker> -p 8883 \
  -u <username> -P '<password>' \
  -t '<prefix>/cli/fs.write' \
  -f /tmp/payload.bin
```

For chunked writes from a script, slice the file into ~3900-byte chunks (so `path + '\n' + chunk` stays under `buffer_in`), publish each as a separate MQTT message with `fs.append` after the first, and wait for the per-chunk `ok=true` before publishing the next.

## End-to-end example

Round-trip a Lua script via the chunked path:

```bash
PREFIX=thesada/owb
BROKER=<broker-host>
USER=<mqtt-username>
PASS=<mqtt-password>

# 1. Read the current /scripts/rules.lua
offset=0
> /tmp/rules.out
while :; do
  resp=$(mosquitto_pub -h $BROKER -u $USER -P "$PASS" \
    -t $PREFIX/cli/fs.cat \
    -m "/scripts/rules.lua $offset 2048" --quiet)
  # subscribe in another terminal for the response, accumulate data, stop on done=true
done

# 2. Write a new version (assuming rules-new.lua is < buffer_in - path - 1)
printf '/scripts/rules.lua\n' > /tmp/payload.bin
cat rules-new.lua            >> /tmp/payload.bin
mosquitto_pub -h $BROKER -u $USER -P "$PASS" \
  -t $PREFIX/cli/fs.write -f /tmp/payload.bin

# 3. Hot-reload
mosquitto_pub -h $BROKER -u $USER -P "$PASS" \
  -t $PREFIX/cli/lua.reload -m ''
```

## Failure modes

- **Buffer overflow on write**: if `path + '\n' + chunk` exceeds `buffer_in`, the firmware drops the message at the broker subscription path and the response never arrives. Always size chunks against the device's actual `mqtt.buffer_in` (read it via `config.get mqtt.buffer_in`).
- **Out-of-range read**: if `offset >= total`, the response returns `length=0`, `done=true`, `data=""`. Loop should treat that as a clean end-of-file.
- **Concurrent writes**: the firmware does not lock files. A second writer mid-stream interleaves bytes. Single-writer discipline is the operator's job.
- **Broker disconnect mid-stream**: the file is left in whatever state the partial writes produced. Re-run the whole loop from `fs.write` (truncate) to recover.

See also: [CLI Reference - Filesystem](cli-reference.html#filesystem) for the line-mode commands and full argument shape.
