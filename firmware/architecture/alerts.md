---
title: Alerts & Webhook
parent: Architecture
grand_parent: Firmware
nav_order: 5
description: "Lua-driven alerting with sustain, cooldown, and three output channels (MQTT, Telegram, webhook)."
---

# Alerts & Webhook

```mermaid
flowchart TD
    A[Sensor Read] --> B[EventBus publish]
    B --> C[rules.lua callback]
    C --> D{Threshold crossed?}
    D -->|No| E[Clear sustain counter]
    D -->|Yes| F[Increment sustain]
    F --> G{N readings OR T minutes?}
    G -->|Not yet| H[Wait for next read]
    G -->|Yes| I{Cooldown expired?}
    I -->|No| H
    I -->|Yes| J[notify]
    J --> K[Log.warn]
    J --> L[Telegram.broadcast]
    J --> M[MQTT publish alert]
```

## Lua Alert Engine

Alert logic lives in `/scripts/rules.lua` on LittleFS - hot-reloadable without recompiling. The firmware provides the bindings; the script defines the rules.

**Available Lua bindings for alerts:**

| Function | Description |
|---|---|
| `EventBus.subscribe(event, fn)` | Subscribe to sensor events (`temperature`, `current`, `battery`) |
| `Telegram.send(chat_id, msg)` | Send to a specific Telegram chat |
| `Telegram.broadcast(msg)` | Send to all configured `chat_ids` |
| `MQTT.publish(topic, payload)` | Publish alert to MQTT |
| `Config.get(key)` | Read config values (supports dot notation and array indices) |
| `Node.uptime()` | Current uptime in ms (for cooldown/sustain timing) |
| `Node.setTimeout(ms, fn)` | Delayed execution (e.g. boot alerts after WiFi ready) |
| `Log.warn(msg)` | Log alert to serial/WebSocket terminal |

**Telegram config (`config.json`):**

```json
"telegram": {
  "bot_token": "your-bot-token",
  "chat_ids": ["123456789", "-100987654321"]
}
```

Both array and object format supported for `chat_ids`:
```json
"chat_ids": {"daniel": "123456789", "family": "-100987654321"}
```

Object format enables per-recipient routing in Lua:
```lua
local daniel = Config.get("telegram.chat_ids.daniel")
Telegram.send(daniel, "critical alert")
```

## Example rules.lua

```lua
local prefix = Config.get("mqtt.topic_prefix")
local unit   = Config.get("temperature.unit") or "C"

local sustain = {}
local cooldown = {}
local COOLDOWN_MS = 900000   -- 15 minutes
local TEMP_SUSTAIN = 5       -- 5 readings or 5 minutes

local function can_alert(key)
  local now = Node.uptime()
  if cooldown[key] and (now - cooldown[key]) < COOLDOWN_MS then
    return false
  end
  cooldown[key] = now
  return true
end

local function notify(msg)
  Log.warn(msg)
  Telegram.broadcast(msg)
  MQTT.publish(prefix .. "/alert", msg)
end

-- Temperature: sustained low temp alert
EventBus.subscribe("temperature", function(data)
  for _, s in ipairs(data.sensors) do
    local key = "low_temp:" .. s.name
    if s.name == "House Supply" and s.temp_c <= 55 then
      sustain[key] = (sustain[key] or 0) + 1
      if sustain[key] >= TEMP_SUSTAIN and can_alert(key) then
        notify(s.name .. ": " .. s.temp .. unit .. " - Low temp")
        sustain[key] = 0
      end
    else
      sustain[key] = 0
    end
  end
end)

-- Battery: immediate alert
EventBus.subscribe("battery", function(data)
  if data.present and data.percent <= 20 and not data.charging then
    if can_alert("battery_low") then
      notify("Battery low: " .. data.percent .. "%")
    end
  end
end)
```

**EventBus data format (temperature):**

```json
{
  "sensors": [
    { "name": "House Supply", "temp_c": 54.4, "temp": 129.9, "address": "28..." }
  ]
}
```

- `temp_c` - always Celsius (use for thresholds)
- `temp` - display unit (C or F depending on `temperature.unit` config)

**Sustain pattern:** alert only fires after N consecutive readings cross the threshold. Prevents false alerts from single sensor glitches or brief temperature dips when loading fuel.

**Cooldown pattern:** after an alert fires, the same key won't fire again for `COOLDOWN_MS` milliseconds. Prevents alert spam when a condition persists.

---

## Webhook

Optional HTTP POST fired from Lua or TelegramModule on every alert:

```json
"webhook": {
  "url": "http://homeassistant.local:8123/api/webhook/thesada-alert",
  "message_template": "{% raw %}{{value}}{% endraw %}"
}
```

`{% raw %}{{value}}{% endraw %}` is replaced with the full alert message. Supports `http://` and `https://`. Leave `url` empty to disable.

---

## Boot alert (main.lua)

Send a Telegram message when the node starts (delayed 10s for WiFi/firewall):

```lua
Node.setTimeout(10000, function()
  local name = Config.get("device.name") or "unknown"
  local ip = Node.ip() or "no IP"
  Telegram.broadcast(name .. " booted - " .. ip)
end)
```

---

## Home Assistant automation for MQTT alerts

```yaml
automation:
  - alias: "Thesada Node Alert - Telegram"
    triggers:
      - trigger: mqtt
        topic: thesada/node/alert
    actions:
      - action: notify.send_message
        data:
          entity_id: notify.telegram_notify
          message: "{% raw %}{{ trigger.payload }}{% endraw %}"
```
