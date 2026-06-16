---
title: Lua Scripting
parent: Firmware
nav_order: 6
description: "Lua 5.3 runtime for thesada-fw - alert rules, MQTT bridges, display logic, hot-reload workflow. Available globals, EventBus API, common patterns."
---

# Lua Scripting

`thesada-fw` ships a Lua 5.3 runtime that loads scripts from LittleFS at boot and re-runs them on demand without rebooting. Use it for alert thresholds, rules, periodic tasks, MQTT bridges, and display rendering, all without recompiling firmware.

## What you get

- **Lua 5.3** with the standard `math`, `table`, `string`, `io` libraries explicitly loaded.
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
Node.uptime()                    -- millis since boot, integer
Node.ip()                        -- WiFi IP as "192.168.1.42" or empty
Node.setTimeout(5000, function() -- one-shot timer, ms
  Log.info("5 seconds passed")
end)
```

Timer queue is 8 slots. A `setTimeout` when full logs a warning and returns `false`; the callback is dropped. Build periodic loops by re-arming inside the callback.

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
EventBus.subscribe("sensor.temperature", function(data)
  for i, sensor in ipairs(data.sensors or {}) do
    if sensor.temp and sensor.temp > 70 then
      Log.warn(string.format("%s above 70 C: %.1f", sensor.name, sensor.temp))
    end
  end
end)

EventBus.subscribe("alert", function(data)
  -- data has .severity, .message, .metric, .value, .ts
end)
```

Common events (varies by build):

| Event | Source | Payload shape |
|---|---|---|
| `sensor.temperature` | TemperatureModule | `{ sensors = [{ name, temp }] }` |
| `sensor.current` | ADS1115Module | `{ channels = [{ name, current_a, power_w }] }` |
| `sensor.battery` | BatteryModule | `{ percent, voltage, charging }` |
| `sensor.sht31` | SHT31Module | `{ temperature, humidity }` |
| `alert` | any module / Lua publish | `{ severity, code, message, metric, value, ts }` |

The C++ side publishes to the EventBus as soon as a sensor read completes; subscribing in Lua is the lowest-latency way to react.

### `JSON`

```lua
local data = JSON.decode(payload)
if data and data.value then
  -- data is a table built from the JSON payload
end
```

Decode-only for now; build outbound JSON by string concatenation or `string.format`.

### Stdlib sandbox

The Lua state is sandboxed. `io`, `os`, `debug`, `package`, `require`, `dofile`, `loadfile`, `load`, and `loadstring` are all `nil` - calling any of them raises a "attempt to call a nil value" error.

Reason: MQTT broker credentials are device root via `cli/lua.exec`. A leaked broker login should not equal `io.open("/config.json"):read("*a")` over the network. The safe subset that stays exposed is `_G`, `math`, `string`, `table`, `utf8` plus the firmware bindings below.

For LittleFS cleanup that the shell parser cannot reach (filenames with embedded whitespace etc), use the `fs.rm` shell command rather than the older `os.remove` helper that used to live here. `os.remove` is no longer registered.

### Module-provided bindings

Modules optionally register their own Lua libraries when their compile flag is set. The most common today:

- `Telegram.send(chatID, msg)` / `Telegram.broadcast(msg)` - direct Telegram Bot API output (compile flag `ENABLE_TELEGRAM`).

If a binding is missing on the running build, referencing it raises a Lua error. Guard with `if Telegram then ... end` for scripts that may run on a build where the module is disabled.

## Generation safety on reload

Every successful `lua.reload` bumps an internal generation counter. MQTT subscriptions and EventBus subscriptions registered by Lua capture the generation at registration time; when a callback fires, it checks against the current generation and silently no-ops if it is stale. The same goes for `Node.setTimeout` callbacks - timer slots are cleared at the start of `createState`, so a pending timer from the previous load will never fire.

The point: you can `lua.reload` mid-flight without leftover subscriptions executing under the new state. The C++ side keeps the broker subscription alive across reloads, so the new script's `MQTT.subscribe` re-attaches its own handler without re-talking to the broker.

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

EventBus.subscribe("sensor.temperature", function(data)
  for _, s in ipairs(data.sensors or {}) do
    if s.name == "boiler" then
      if s.temp > 75 and not triggered then
        triggered = true
        local prefix = Config.get("mqtt.topic_prefix")
        local payload = string.format(
          '{"severity":"crit","metric":"temperature.boiler","value":%.1f,"message":"Boiler over 75 C"}',
          s.temp)
        MQTT.publish(prefix .. "/alert", payload)
      elseif s.temp < 70 and triggered then
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

EventBus.subscribe("sensor.battery", function(data)
  if data.voltage and data.voltage < 3.3 then
    if sustain_start == nil then
      sustain_start = Node.uptime()
    elseif Node.uptime() - sustain_start > SUSTAIN_MS
       and Node.uptime() - last_alert  > COOLDOWN_MS then
      last_alert = Node.uptime()
      local prefix = Config.get("mqtt.topic_prefix")
      MQTT.publish(prefix .. "/alert",
        string.format('{"severity":"warn","metric":"battery.voltage","value":%.2f,"message":"Battery low for 60 s"}',
                      data.voltage))
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
- **No file I/O from Lua at all**. `io` is nil-out for sandbox reasons (see Stdlib sandbox above). Use the firmware bindings (`Config.set`, MQTT outbound, etc) for state writes; for LittleFS cleanup use the `fs.rm` shell command.
- **Lua 5.3 integer / float semantics**. Numbers from `JSON.decode` come as floats; cast with `math.floor` or `n // 1` (integer division) before string formatting if you want an integer print.
- **String concatenation in tight loops** allocates. Prefer `table.concat` for building large strings.
- **Generation guard does not cover top-level side effects**. If `main.lua` allocates a global, hot-reload re-runs it from scratch in a new state - the previous state's global is gone, but any external resource the previous run held (a WiFi socket, a file handle) is also gone. Modules clean up their own resources on script-state teardown; Lua-side helpers should not hold resources that need explicit close.

## See also

- [CLI Reference - Lua](cli-reference.html#lua) for `lua.exec`, `lua.load`, `lua.reload` syntax.
- [MQTT Topics](mqtt-topics.html) for the topic shapes Lua scripts subscribe to.
- [Architecture - Shell and Scripting](architecture/shell-scripting.html) for the C++-side integration model.
