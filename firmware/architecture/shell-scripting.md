---
title: Shell & Scripting
parent: Architecture
grand_parent: Firmware
nav_order: 2
description: "Unified CLI with 30+ commands across serial, WebSocket, HTTP, and MQTT. Lua 5.3 scripting with hot-reloadable event rules."
---

# Shell & Scripting

## Shell (CLI)

`Shell` is a unified command-line interface. The same command handlers run across every transport - there is no duplicate logic.

**Transport wiring:**
- Serial: `main.cpp` reads characters, calls `Shell::execute(line, serialOut)` on newline
- WebSocket: `HttpServer.cpp` receives WS data, calls `Shell::execute(cmd, [client](line){ client->text(line); })`
- HTTP: `POST /api/cmd` with `{"cmd":"..."}` collects output lines into a JSON array and returns `{"ok":true,"output":[...]}`
- MQTT: publish the command to `thesada/<device>/cli/<cmd>` (payload is the argument string, empty payload for argless commands). `MQTTClient.cpp` subscribes to `thesada/<device>/cli/#`, parses the suffix as the command name, and calls `Shell::execute("<cmd> <payload>", out)` where `out` collects lines into a JSON array published back on `thesada/<device>/cli/response` as `{"cmd":"...","ok":true,"output":["..."]}`. This is the primary remote-debug path for devices with no serial access.

Example MQTT usage:

```bash
# trigger an OTA check with force flag
mosquitto_pub -t thesada/owb/cli/ota.check -m '--force'

# dump chip info
mosquitto_pub -t thesada/owb/cli/chip.info -m ''

# subscribe to the response topic before sending for round-trip visibility
mosquitto_sub -t 'thesada/owb/cli/response' -v
```

**Self-registering commands:**
Modules register their own shell commands in `begin()` via `Shell::registerCommand()`. Shell.cpp has zero module includes - commands are discovered at runtime.

```cpp
// In any module's begin():
Shell::registerCommand("name", "one-line help text", [](int argc, char** argv, ShellOutput out) {
  out("response line");
});
```

The `module.status` and `selftest` commands call `Module::status()` and `Module::selftest()` virtuals on each registered module.

**Built-in commands:**

| Command | Output |
|---|---|
| `help` | List all commands |
| `version` | Firmware version, build date |
| `restart` | Reboot device |
| `heap` | Free, min free, max alloc bytes |
| `uptime` | Days + HH:MM:SS |
| `sensors` | All configured sensors with addresses/pins/mux/gain + battery reading |
| `battery` | Voltage, percent, charging state |
| `sleep` | Sleep enabled/disabled, boot count, wake/sleep times, last OTA check |
| `selftest` | 10-point check with pass/fail/warn per item |
| `fs.ls [path]` | Directory listing with file sizes |
| `fs.cat <path>` | Print file contents (line-by-line) |
| `fs.cat <path> <offset> <len>` | Chunked read with metadata (total, offset, length, done, data) |
| `fs.rm <path>` | Remove file (echoes path) |
| `fs.write <path> <content>` | Write content to file - truncates (echoes bytes written) |
| `fs.append <path> <content>` | Append content to file (echoes bytes appended) |
| `fs.mv <src> <dst>` | Rename/move (echoes src -> dst) |
| `fs.df` | LittleFS + SD usage in bytes/MB |
| `config.get <key>` | Read config value by dot notation |
| `config.set <key> <value>` | Set + save to flash + reload in-memory (echoes key = value) |
| `config.save` | Save to flash (echoes bytes written) |
| `config.reload` | Reload from flash, reconnect MQTT if network keys changed |
| `config.dump` | Print full config JSON |
| `net.ip` | SSID, IP, gateway, DNS, RSSI, MAC |
| `net.ping <host>` | DNS resolve test (echoes resolved IP) |
| `net.ntp` | Sync status, UTC time, epoch, server, offset. `net.ntp set <epoch>` or `net.ntp set <ISO8601>` to set manually. |
| `net.mqtt` | MQTT connection status, subscription table, recent RX ring |
| `ota.check` | Trigger OTA update check |
| `ota.check --force [url]` | Force OTA bypassing version check, optional custom URL |
| `ota.status` | Partition table + rollback state |
| `boot.info` | Last reset reason + uptime |
| `partitions` | Full partition table dump |
| `chip.info` | Chip revision, flash size, PSRAM, CPU frequency |
| `sdkconfig` | Selected CONFIG_* values relevant to OTA/boot |
| `module.list` | Compiled modules with [x]/[ ] toggles |
| `module.status` | Runtime state per module (sensor counts, intervals, pins, SD mount, Telegram direct) |
| `lua.exec <code>` | Execute inline Lua, show return value |
| `lua.load <path>` | Execute Lua file from LittleFS |
| `lua.reload` | Hot-reload scripts (echoes which scripts are present) |

Paths prefixed with `/sd/` are routed to the SD card; all others go to LittleFS. SD card handling (including `fs.df` SD output) is fully in `SDModule` - Shell.cpp has no SD_MMC or SD includes.

### Chunked file I/O

For files larger than the MQTT response buffer (4096 bytes default), use the chunked read protocol:

```bash
# Read first 2048 bytes
mosquitto_pub -t '<prefix>/cli/fs.cat' -m '/scripts/rules.lua 0 2048'
# Response: {"cmd":"fs.cat","ok":true,"total":3858,"offset":0,"length":2048,"done":false,"data":"..."}

# Continue from offset 2048
mosquitto_pub -t '<prefix>/cli/fs.cat' -m '/scripts/rules.lua 2048 2048'
# Response: {"cmd":"fs.cat","ok":true,"total":3858,"offset":2048,"length":1810,"done":true,"data":"..."}
```

For writes, `fs.write` and `fs.append` use a binary payload format via MQTT (path + newline + content). These bypass the Shell's 256-byte parse buffer:

```bash
# Build payload file: first line is path, rest is content
printf '/scripts/rules.lua\n' > /tmp/payload.bin
cat rules.lua >> /tmp/payload.bin
mosquitto_pub -t '<prefix>/cli/fs.write' -f /tmp/payload.bin
```

For multi-chunk writes: first `fs.write` (truncates), then `fs.append` for remaining chunks.

---

## Lua Scripting (ScriptEngine)

Lua 5.3 runtime via the [ESP-Arduino-Lua](https://github.com/sfranzyshen/ESP-Arduino-Lua) library (GPL-3.0).

**Self-registering Lua bindings:** Modules register their own Lua bindings in `begin()` via `ScriptEngine::addBindings(fn)`. ScriptEngine has zero module includes - Display, TFT, and Telegram Lua bindings live in their respective modules. The registrar list is persistent and survives `lua.reload`. The Lua API table below is unchanged - the same functions are available to scripts.

**Scripts on LittleFS:**
- `/scripts/main.lua` - runs once at boot (setup tasks, one-time subscriptions)
- `/scripts/rules.lua` - event-driven rules, hot-reloadable without restart

**Lua API:**

| Function | Description |
|---|---|
| `Log.info(msg)` | Log at INFO level (tag: Lua) |
| `Log.warn(msg)` | Log at WARN level |
| `Log.error(msg)` | Log at ERROR level |
| `EventBus.subscribe(event, func)` | Subscribe to named event; func receives a table |
| `MQTT.publish(topic, payload)` | Publish a message to MQTT |
| `MQTT.subscribe(topic, fn)` | Subscribe to MQTT topic; fn(topic, payload) called on message |
| `Telegram.broadcast(msg)` | Send message to all configured Telegram chat IDs. Returns true/false. |
| `Telegram.send(chatID, msg)` | Send message to a specific chat ID. Returns true/false. |
| `JSON.decode(str)` | Parse JSON string into a Lua table |
| `Config.get(key)` | Read config value by dot-notation key (e.g. `"mqtt.broker"`) |
| `Node.restart()` | Reboot the device |
| `Node.version()` | Returns firmware version string |
| `Node.uptime()` | Returns `millis()` as number |
| `Node.ip()` | Returns WiFi IP as string |
| `Node.setTimeout(ms, fn)` | Call `fn` after `ms` milliseconds (max 8 pending timers) |
| `Display.clear()` | Clear OLED framebuffer [ENABLE_DISPLAY] |
| `Display.text(x, y, str)` | Draw text at position |
| `Display.line(x1, y1, x2, y2)` | Draw a line |
| `Display.rect(x, y, w, h)` | Rectangle outline |
| `Display.fill(x, y, w, h)` | Filled rectangle |
| `Display.show()` | Send framebuffer to screen |
| `Display.font(size)` | Set font: "small", "medium", "large" |
| `Display.ready()` | Returns true if display initialized |
| `Display.color(r, g, b)` | Set foreground color (TFT only, 0-255 per channel) |
| `Display.bgcolor(r, g, b)` | Set background color (TFT only) |
| `Display.width()` | Screen width in pixels (TFT only) |
| `Display.height()` | Screen height in pixels (TFT only) |
| `Display.touched()` | Returns x, y if touched, nil otherwise (TFT only) |
| `Display.onTouch(fn)` | Register touch callback fn(x, y), IRQ-driven (TFT only) |
| `Display.center(y, str)` | Draw text centered horizontally (TFT only) |
| `Display.textWidth(str)` | Return pixel width of string in current font (TFT only) |
| `Display.backlight(bool)` | Turn TFT backlight on/off (TFT only) |
| `Display.led(r, g, b)` | Set RGB LED color (CYD only, 0-255) |

On the OLED module, TFT-specific functions are not available. On the TFT module, `Display.show()` is a no-op (TFT draws immediately). Touch uses the XPT2046 IRQ pin for zero-polling-overhead event detection.

**Config.get array support:**
`Config.get` supports both object keys and array indices via dot notation:
```lua
Config.get("telegram.chat_ids.0")       -- first element of array
Config.get("telegram.chat_ids.daniel")  -- named key in object
Config.get("mqtt.broker")               -- regular nested key
```

**Telegram chat_ids format:**
Both array and object formats are supported:
```json
"chat_ids": ["123456789", "-10987654321"]
"chat_ids": {"user1": "123456789", "user2": "-10987654321"}
```
Object format allows `Telegram.send(Config.get("telegram.chat_ids.user1"), msg)` for per-recipient alerts.

**Script loading:**
ScriptEngine loads two files at boot (and on `lua.reload`):
1. `/scripts/main.lua` - runs once (boot tasks, timers, one-time setup)
2. `/scripts/rules.lua` - event-driven rules (EventBus subscriptions, alert logic)

Alert logic should go in `rules.lua`, not a separate file. Only `main.lua` and `rules.lua` are loaded automatically.

**Hot reload:**
`ScriptEngine::reload()` bumps a generation counter, destroys the Lua state, creates a fresh one, and re-executes both scripts. Stale EventBus callbacks check the generation counter and silently skip. Reload is triggered by:
- Shell command: `lua.reload`
- MQTT CLI: `cli/lua.reload`

**Example rules.lua:**
```lua
EventBus.subscribe("temperature", function(data)
  local sensors = data.sensors
  for i = 1, #sensors do
    local s = sensors[i]
    if s.temp_c > 40 then
      Log.warn("High temp: " .. s.name .. " " .. s.temp_c .. "C")
      MQTT.publish("thesada/node/alert", s.name .. " overheating")
    end
  end
end)
```
