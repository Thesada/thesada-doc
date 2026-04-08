---
title: Shell & Scripting
parent: Architecture
grand_parent: Firmware
nav_order: 2
description: "Unified CLI with 30+ commands across serial, WebSocket, and HTTP. Lua 5.3 scripting with hot-reloadable event rules."
---

# Shell & Scripting

## Shell (CLI)

`Shell` is a unified command-line interface. The same command handlers run for both the serial terminal and the WebSocket web terminal - there is no duplicate logic.

**Transport wiring:**
- Serial: `main.cpp` reads characters, calls `Shell::execute(line, serialOut)` on newline
- WebSocket: `HttpServer.cpp` receives WS data, calls `Shell::execute(cmd, [client](line){ client->text(line); })`
- HTTP: `POST /api/cmd` with `{"cmd":"..."}` collects output lines into a JSON array and returns `{"ok":true,"output":[...]}`

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
| `fs.cat <path>` | Print file contents |
| `fs.rm <path>` | Remove file (echoes path) |
| `write <path> <content>` | Write content to file (echoes bytes written) |
| `fs.mv <src> <dst>` | Rename/move (echoes src -> dst) |
| `fs.df` | LittleFS + SD usage in bytes/MB |
| `config.get <key>` | Read config value by dot notation |
| `config.set <key> <value>` | Set + save + reload (echoes key = value) |
| `config.save` | Save to flash (echoes bytes written) |
| `config.reload` | Reload from flash (echoes device name) |
| `config.dump` | Print full config JSON |
| `net.ip` | SSID, IP, gateway, DNS, RSSI, MAC |
| `net.ping <host>` | DNS resolve test (echoes resolved IP) |
| `net.ntp` | Sync status, UTC time, epoch, server, offset. `net.ntp set <epoch>` or `net.ntp set <ISO8601>` to set manually. |
| `mqtt` | Connected/disconnected, broker, port, prefix |
| `module.list` | Compiled modules with [x]/[ ] toggles |
| `module.status` | Runtime state per module (sensor counts, intervals, pins, SD mount, Telegram direct) |
| `lua.exec <code>` | Execute inline Lua, show return value |
| `lua.load <path>` | Execute Lua file from LittleFS |
| `lua.reload` | Hot-reload scripts (echoes which scripts are present) |

Paths prefixed with `/sd/` are routed to the SD card; all others go to LittleFS. SD card handling (including `fs.df` SD output) is fully in `SDModule` - Shell.cpp has no SD_MMC or SD includes.

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
