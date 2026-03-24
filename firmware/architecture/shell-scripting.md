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
- WebSocket: `WebServer.cpp` receives WS data, calls `Shell::execute(cmd, [client](line){ client->text(line); })`
- HTTP: `POST /api/cmd` with `{"cmd":"..."}` collects output lines into a JSON array and returns `{"ok":true,"output":[...]}`

**Registering a command:**
```cpp
Shell::registerCommand("name", "one-line help text", [](int argc, char** argv, ShellOutput out) {
  out("response line");
});
```

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
| `ls [path]` | Directory listing with file sizes |
| `cat <path>` | Print file contents |
| `rm <path>` | Remove file (echoes path) |
| `write <path> <content>` | Write content to file (echoes bytes written) |
| `mv <src> <dst>` | Rename/move (echoes src -> dst) |
| `df` | LittleFS + SD usage in bytes/MB |
| `config.get <key>` | Read config value by dot notation |
| `config.set <key> <value>` | Set + save + reload (echoes key = value) |
| `config.save` | Save to flash (echoes bytes written) |
| `config.reload` | Reload from flash (echoes device name) |
| `config.dump` | Print full config JSON |
| `ifconfig` | SSID, IP, gateway, DNS, RSSI, MAC |
| `ping <host>` | DNS resolve test (echoes resolved IP) |
| `ntp` | Sync status, UTC time, epoch, server, offset. `ntp set <epoch>` or `ntp set <ISO8601>` to set manually. |
| `mqtt` | Connected/disconnected, broker, port, prefix |
| `module.list` | Compiled modules with [x]/[ ] toggles |
| `module.status` | Runtime state per module (sensor counts, intervals, pins, SD mount, Telegram direct) |
| `lua.exec <code>` | Execute inline Lua, show return value |
| `lua.load <path>` | Execute Lua file from LittleFS |
| `lua.reload` | Hot-reload scripts (echoes which scripts are present) |

Paths prefixed with `/sd/` are routed to SD_MMC; all others go to LittleFS.

---

## Lua Scripting (ScriptEngine)

Lua 5.3 runtime via the [ESP-Arduino-Lua](https://github.com/sfranzyshen/ESP-Arduino-Lua) library (GPL-3.0).

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
| `Config.get(key)` | Read config value by dot-notation key (e.g. `"mqtt.broker"`) |
| `Node.restart()` | Reboot the device |
| `Node.version()` | Returns firmware version string |
| `Node.uptime()` | Returns `millis()` as number |

**Hot reload:**
`ScriptEngine::reload()` bumps a generation counter, destroys the Lua state, creates a fresh one, and re-executes both scripts. Stale EventBus callbacks check the generation counter and silently skip. Reload is triggered by:
- Shell command: `lua.reload`
- MQTT message to `<topic_prefix>/cmd/lua/reload`

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
