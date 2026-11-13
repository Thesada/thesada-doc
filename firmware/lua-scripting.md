---
title: Lua Scripting
parent: Firmware
nav_order: 6
description: "Lua 5.3 runtime for thesada-fw - alert rules, MQTT bridges, display logic, hot-reload workflow. Available globals, EventBus API, common patterns."
---

# Lua Scripting

`thesada-fw` ships a Lua 5.3 runtime that loads scripts from LittleFS at boot and re-runs them on demand without rebooting. Use it for alert thresholds, rules, periodic tasks, MQTT bridges, and display rendering, all without recompiling firmware.

## What you get

- **Lua 5.3** with the standard `math`, `table` and `string` libraries explicitly loaded. `io`, `os`, `debug` and `package` are nil, see [Stdlib sandbox](#stdlib-sandbox).
- **Hot reload**: `lua.reload` re-runs every script on the fly, dropping all subscriptions and timers from the previous generation cleanly.
- **Up to 8 concurrent timers** via `Node.setTimeout`.
- **Full MQTT publish + subscribe** with per-callback isolation.
- **EventBus subscriptions** for sensor reads, alerts, and module status events emitted by the C++ side.
- **Config read access** via dot-notation paths into the live `config.json`.

## Where scripts live

LittleFS path: `/scripts/`. Two files are loaded by name in order:

1. `/scripts/main.lua` - runs once at boot. Use for top-level setup that does not need modules.
2. `/scripts/rules.lua` - runs after main.lua. Conventional home for alert thresholds and MQTT bridges.

Other `.lua` files in `/scripts/` can be `lua.load`-ed on demand. The bootloader does not auto-discover them.

## Load order and the boot sequence

The ScriptEngine module sits low in the boot priority, so by the time scripts start running:

- WiFi / Ethernet has attempted association (live or fallback).
- MQTT may or may not be connected yet - assume not, and use `MQTT.subscribe` which queues the subscription until the broker session is up.
- Other modules (Telegram, Cellular) have called `begin()`. Their Lua bindings are available immediately.

Subscribe-style code is safe to run at top level. Anything that needs MQTT to be connected (e.g. `MQTT.publish` and expecting it to land immediately) should be wrapped in a `Node.setTimeout` or driven from an `EventBus.subscribe("mqtt_connected", ...)` style hook.

## Globals exposed to Lua

### `Log`

Three levels, all take a single string. Output goes to the same log ring the WS terminal replays + the serial console.

```lua
Log.info("rules.lua loaded")
Log.warn("Battery below 20%")
Log.error("Failed to parse payload")
```

### `MQTT`

```lua
MQTT.publish(topic, payload)
MQTT.subscribe(topic, function(topic, payload)
  -- topic is the full received topic
  -- payload is a string (parse with JSON.decode if it is JSON)
end)
```

Subscriptions persist across reconnects. The firmware re-applies every active subscription when it reconnects to the broker. Wildcards (`+`, `#`) are supported and follow MQTT 3.1.1 rules.

### `Node`

Per-device runtime info plus a small timer queue.

```lua
Node.restart()                   -- reboot the device
Node.version()                   -- firmware version string
Node.uptime()                    -- ms since boot, 32-bit float, no wrap
Node.ip()                        -- WiFi IP as "192.168.1.42" or empty
Node.setTimeout(5000, function() -- one-shot timer, ms
  Log.info("5 seconds passed")
end)
```

Timer queue is 8 slots. A `setTimeout` when full logs a warning and returns `false`; the callback is dropped. Build periodic loops by re-arming inside the callback.

`Node.uptime()` and `setTimeout` deadlines count 64-bit uptime, so neither breaks at the 49.7-day `millis()` wrap. Lua numbers are 32-bit floats here, so uptime stays monotonic but its step grows with it (512 ms past 49.7 days, 2 s past 199 days) - fine for second-scale cooldowns.

| `setTimeout` delay | Result |
|---|---|
| NaN | refused, returns `false` |
| negative | fires on the next pass |
| past 30 days (including `math.huge`) | capped at 30 days |

### `Config`

Read-only access to the live `config.json`. Dot-notation, drills into nested objects and arrays.

```lua
Config.get("device.name")               -- "owb"
Config.get("mqtt.topic_prefix")         -- "thesada/owb"
Config.get("temperature.unit")          -- "C"
Config.get("temperature.sensors.0.name") -- first sensor by array index
Config.get("nonexistent.key")           -- nil
```

For complex objects (whole subtrees), `Config.get` returns the JSON string serialization. Parse with `JSON.decode` if you want a Lua table.

### `EventBus`

Subscribe to events emitted by C++ modules. The callback receives a Lua table built from the event's JSON payload.

```lua
EventBus.subscribe("temperature", function(data)
  for i, sensor in ipairs(data.sensors or {}) do
    if sensor.temp_c and sensor.temp_c > 70 then
      Log.warn(string.format("%s above 70 C: %.1f", sensor.name, sensor.temp_c))
    end
  end
end)

EventBus.subscribe("alert", function(data)
  -- data.severity and data.message are always set. data.code comes from
  -- Telegram.broadcast, data.metric, data.value and data.ts only from scripts that add them
end)
```

Event names are exact strings - there is no `sensor.*` namespace or wildcard
matching. Write thresholds against `temp_c` (always Celsius). `temp` is the
same reading in the configured display unit.

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/event_bus_table.h match="constexpr size_t EVENT_SUBS_MAX = 128;" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/event_bus_table.h match="constexpr size_t EVENT_PUBLISH_MARGIN = 64;" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="script\.event_subscribe_refused event=%s reason=full max=%u" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="lua_pushboolean\(L, 0\);\n    return 1;\n  \}\n\n  Log::kvf\(TAG, \"script\.event_subscribed event=%s\", event\);\n  lua_pushboolean\(L, 1\);" -->
`EventBus.subscribe` returns `true` once the callback is registered. One event holds at most 128 live callbacks, and past that the call returns `false`, registers nothing and logs `script.event_subscribe_refused`. One publish runs the callbacks it started with plus at most 64 added during it, so a callback that subscribes from inside itself cannot hold the loop. Subscribe once at top level, not from inside a callback:

```lua
if not EventBus.subscribe("battery", on_battery) then
  Log.warn("battery subscription refused")
end
```

Common events (varies by build):

| Event | Source | Payload shape |
|---|---|---|
| `temperature` | TemperatureModule, SHT31Module | `{ sensors = [{ name, address, temp_c, temp }] }` (SHT31 row adds `humidity`, name `SHT31`); a probe without a reading is `{ name, address, stale = true }` with no `temp_c` or `temp` |
| `current` | ADS1115Module | `{ channels = [{ name, address, raw, voltage_v, current_a, power_w, line_v }] }` |
| `battery` | BatteryModule | `{ present, voltage_v, percent, charging }` |
| `alert` | any module / Lua publish | `{ severity, code, message, metric, value, ts }` |

The C++ side publishes to the EventBus as soon as a sensor read completes; subscribing in Lua is the lowest-latency way to react.

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-temperature/src/TemperatureModule.cpp match="case TempVerdict::PowerOn:" -->
Every DS18B20 probe is listed each cycle. One whose read failed, whose reading the `max_delta_c` guard held back, or that read the 85.0 C power-on value away from its last reading carries `stale = true` and no `temp_c` or `temp`. It is never filled with its last value. Guard every temperature field (`if s.temp_c then`) or skip `s.stale`: comparing or concatenating a missing field throws, and the throw ends the callback's loop over the remaining probes.

### `JSON`

```lua
local data = JSON.decode(payload)
if data and data.value then
  -- data is a table built from the JSON payload
end
```

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="if \(doc\.is<JsonObject>\(\) \|\| doc\.is<JsonArray>\(\)\) \{\n    pushJsonVariant\(L, doc\.as<JsonVariant>\(\)\);\n  \} else \{\n    lua_pushnil\(L\);" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="if \(v\.isNull\(\)\) \{\n    lua_pushnil\(L\);\n  \} else if \(v\.is<bool>\(\)\) \{\n    lua_pushboolean\(L, v\.as<bool>\(\)\);\n  \} else if \(v\.is<long>\(\)\) \{\n    lua_pushinteger" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="Shared by JSON\.decode and the EventBus payloads\." -->
`JSON.decode(str)` returns a table for a JSON object or array, and `nil` for invalid JSON or a bare top-level value (`"42"`, `"true"`). Objects and arrays nest at any depth, arrays as 1-based tables. `true` and `false` arrive as Lua booleans, a whole number as a Lua integer, a fractional number as a float, and `null` as `nil`, so a key holding `null` is absent from the table and a `null` array element leaves a hole. EventBus payloads are converted the same way.

Decode-only for now. Build outbound JSON by string concatenation or `string.format`.

### Stdlib sandbox

The Lua state is sandboxed. `io`, `os`, `debug`, `package`, `require`, `dofile`, `loadfile`, `load`, and `loadstring` are all `nil` - calling any of them raises a "attempt to call a nil value" error.

Reason: MQTT broker credentials are device root via `cli/lua.exec`. A leaked broker login should not equal `io.open("/config.json"):read("*a")` over the network. The safe subset that stays exposed is `_G`, `math`, `string`, `table`, `utf8` plus the firmware bindings below.

For LittleFS cleanup that the shell parser cannot reach (filenames with embedded whitespace etc), use the `fs.rm` shell command rather than the older `os.remove` helper that used to live here. `os.remove` is no longer registered.

### Module-provided bindings

Modules optionally register their own Lua libraries when their compile flag is set. The most common today:

- `Telegram.send(chatID, msg)` / `Telegram.broadcast(msg[, code])` - direct Telegram Bot API output (compile flag `ENABLE_TELEGRAM`). `broadcast` also publishes the app alert JSON with `code` (default `telegram`).

If a binding is missing on the running build, referencing it raises a Lua error. Guard with `if Telegram then ... end` for scripts that may run on a build where the module is disabled.

## Generation safety on reload

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="_generation\+\+;\n.*\n  MQTTClient::unsubscribeOwner\(MQTT_SUB_OWNER_LUA\);\n  EventBus::unsubscribeOwner\(EVENT_OWNER_LUA\);" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/mqtt_sub_table.h match="fn\(topic\) runs once per freed topic no\n  // other active slot still holds" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/MQTTClient.h match="MQTT_MAX_SUBS  = 16;" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/MQTTClient.cpp match="if \(_client\.connected\(\)\) _client\.unsubscribe\(topic\);" -->
Every MQTT and EventBus subscription a script makes is tagged as Lua-owned. A successful `lua.reload` frees all of them before the new state runs: the MQTT slots go back to the shared 16-slot table, a topic no other slot still holds is unsubscribed at the broker, and the Lua EventBus callbacks are dropped. Subscriptions the firmware itself holds stay. The new scripts subscribe again from their top level, so repeated reloads never fill the table or pile up callbacks.

The reload also bumps a generation counter that every Lua callback checks, so a callback from the previous load that is already in flight no-ops instead of running under the new state. `Node.setTimeout` slots are cleared at the start of `createState`, so a pending timer from the previous load never fires.

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/Shell.cpp match="Network config changed - reinitializing MQTT subscriptions" -->
<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-core/src/MQTTClient.cpp match="void MQTTClient::reinitSubscriptions\(\) \{(.|\n)*?_subs\.removeOwner\(MQTT_SUB_OWNER_CORE\);" -->
A `config.reload` that changes an MQTT network setting (`mqtt.topic_prefix`, broker, port, user, password or `ota.cmd_topic`) rebuilds only the firmware's own subscriptions and keeps the Lua ones, which hold the whole topics the script chose.

## Alert envelope

Scripts raise alerts by publishing a JSON object to `<prefix>/alert`. The platform parses the payload as JSON and requires a valid `severity`; everything else is optional metadata.

```json
{"severity": "warn", "code": "battery_low", "metric": "battery.voltage", "value": 3.21, "message": "Battery low for 60 s"}
```

| Field | Required | Notes |
|---|---|---|
| `severity` | yes | One of `info`, `warn`, `crit`. Any other value is dropped at ingest. |
| `message` | recommended | Human-readable text. |
| `code` | no | Short stable identifier for the alert kind. |
| `metric` | no | Dotted metric path the alert relates to (e.g. `temperature.boiler`). |
| `value` | no | The reading that triggered it. |

Publish delivery metadata (retry or ack status from a downstream notifier) to `<prefix>/status/alert_delivery`, never to `<prefix>/alert/status` - the latter collides with the alert ingest path.

## Common patterns

### Threshold alert with hysteresis

```lua
local triggered = false

EventBus.subscribe("temperature", function(data)
  for _, s in ipairs(data.sensors or {}) do
    if s.name == "boiler" then
      if s.temp_c and s.temp_c > 75 and not triggered then
        triggered = true
        local prefix = Config.get("mqtt.topic_prefix")
        local payload = string.format(
          '{"severity":"crit","metric":"temperature.boiler","value":%.1f,"message":"Boiler over 75 C"}',
          s.temp_c)
        MQTT.publish(prefix .. "/alert", payload)
      elseif s.temp_c and s.temp_c < 70 and triggered then
        triggered = false
      end
    end
  end
end)
```

`triggered` is a per-load script-local; it survives across event ticks but resets on reload. That is usually what you want.

### Sustain + cooldown

```lua
local sustain_start = nil
local last_alert    = 0
local SUSTAIN_MS    = 60000   -- must stay over threshold for 60 s
local COOLDOWN_MS   = 600000  -- 10 min between alerts

EventBus.subscribe("battery", function(data)
  if data.voltage_v and data.voltage_v < 3.3 then
    if sustain_start == nil then
      sustain_start = Node.uptime()
    elseif Node.uptime() - sustain_start > SUSTAIN_MS
       and Node.uptime() - last_alert  > COOLDOWN_MS then
      last_alert = Node.uptime()
      local prefix = Config.get("mqtt.topic_prefix")
      MQTT.publish(prefix .. "/alert",
        string.format('{"severity":"warn","metric":"battery.voltage","value":%.2f,"message":"Battery low for 60 s"}',
                      data.voltage_v))
    end
  else
    sustain_start = nil  -- reset on recovery
  end
end)
```

### Periodic publish via setTimeout

```lua
local function tick()
  local prefix = Config.get("mqtt.topic_prefix")
  MQTT.publish(prefix .. "/sensor/uptime_lua", tostring(Node.uptime() / 1000))
  Node.setTimeout(60000, tick)  -- re-arm every minute
end
tick()
```

### MQTT-driven action

```lua
local prefix = Config.get("mqtt.topic_prefix")

MQTT.subscribe(prefix .. "/cmd/lua/echo", function(topic, payload)
  Log.info("Echo: " .. payload)
  MQTT.publish(prefix .. "/cmd/lua/echo/response", payload)
end)
```

The `<prefix>/cmd/lua/reload` topic is reserved by the firmware (it triggers script reload), but other topics under `<prefix>/cmd/` are free for script use.

### Bridging an external MQTT topic

```lua
-- Mirror a remote node's temperature into our own topic tree.
local sourcePrefix = Config.get("display.remote_prefix") or "thesada/owb"
local ownPrefix    = Config.get("mqtt.topic_prefix")

MQTT.subscribe(sourcePrefix .. "/sensor/temperature", function(topic, payload)
  local data = JSON.decode(payload)
  if data and data.sensors then
    MQTT.publish(ownPrefix .. "/sensor/remote_temp", tostring(data.sensors[1].temp))
  end
end)
```

## Hot-reload workflow

Edit the script on the device:

```bash
# Push a new rules.lua via the chunked-write contract
mosquitto_pub -t '<prefix>/cli/fs.write' -f /tmp/payload.bin

# Reload
mosquitto_pub -t '<prefix>/cli/lua.reload' -m ''
```

Or via the WS terminal:

```text
fs.write /scripts/rules.lua  <... content ...>
lua.reload
```

The reload destroys the current Lua state, re-creates a fresh one, registers all bindings, and re-runs `main.lua` then `rules.lua`. Any timers, subscriptions, or globals from the previous run are gone.

If a script has a syntax error or runtime error during top-level execution, the error is logged at level `error` and the script's globals partially populate (whatever ran before the error). Subsequent reloads start over cleanly.

## Limits and gotchas

- **Heap pressure**. The Lua state itself costs ~30 KB plus per-script overhead. On a board without PSRAM, heavy table allocations during alert handlers can spike free-heap below the TLS reconnect floor and trigger a preventive reboot. Use `collectgarbage("collect")` from a periodic `Node.setTimeout` if you see linear heap decline.
- **8 timer slots**. Concurrent `setTimeout` count is hard-capped. Long polling loops should re-arm one timer at a time, not stack many.
- **No file I/O from Lua at all**. `io` is nil-out for sandbox reasons (see Stdlib sandbox above). Config is read-only from Lua (`Config.get`); a config change goes through the `config.set` shell command, and state leaves the device over MQTT. For LittleFS cleanup use the `fs.rm` shell command.
- **Lua 5.3 integer / float semantics**. `JSON.decode` gives a whole number as an integer and a fractional one as a float (see [`JSON`](#json)). A reading such as `21.0` that the sender wrote with a decimal point arrives as a float, so cast with `math.floor` or `n // 1` (integer division) before string formatting if you want an integer print.
- **String concatenation in tight loops** allocates. Prefer `table.concat` for building large strings.
- **Generation guard does not cover top-level side effects**. If `main.lua` allocates a global, hot-reload re-runs it from scratch in a new state - the previous state's global is gone, but any external resource the previous run held (a WiFi socket, a file handle) is also gone. Modules clean up their own resources on script-state teardown; Lua-side helpers should not hold resources that need explicit close.

## See also

- [CLI Reference - Lua](cli-reference.html#lua) for `lua.exec`, `lua.load`, `lua.reload` syntax.
- [MQTT Topics](mqtt-topics.html) for the topic shapes Lua scripts subscribe to.
- [Architecture - Shell and Scripting](architecture/shell-scripting.html) for the C++-side integration model.
