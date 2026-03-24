---
title: Alerts & Webhook
parent: Architecture
grand_parent: Firmware
nav_order: 5
description: "Three-channel alerting (MQTT, Telegram Bot API, webhook), per-sensor cooldown, low-battery alerts, and HA automation examples."
---

# Alerts & Webhook

## Alerts (TelegramModule)

The `TelegramModule` subscribes to `temperature` and `battery` events and fires alerts when readings cross configured thresholds. Alerts are delivered via three independent channels:

1. **MQTT** - `MQTTClient` subscribes to the `alert` EventBus event and publishes to `<topic_prefix>/alert` as `{ "value": "..." }`
2. **Telegram Bot API** - optional direct HTTPS call if `telegram.bot_token` and `telegram.chat_ids` are set. Sends to all chat IDs in the array.
3. **HTTP webhook** - optional POST to `webhook.url` with configurable message template

All three channels fire independently. If `bot_token` or `chat_ids` are empty, the Telegram API call is skipped. If `webhook.url` is empty, the webhook is skipped. MQTT alerts always fire.

**Alert config in `config.json`:**

```json
"telegram": {
  "bot_token": "",
  "chat_ids": [],
  "cooldown_s": 300,
  "alerts": [
    { "enabled": true,  "name": "overheat", "temp_high_c": 40.0 },
    { "enabled": true,  "name": "freeze",   "temp_low_c":  2.0  },
    { "enabled": false, "name": "custom",   "temp_high_c": 60.0, "temp_low_c": -5.0 }
  ]
}
```

| Field | Description |
|---|---|
| `bot_token` | Telegram Bot API token (from @BotFather). Empty = skip direct Telegram. |
| `chat_ids` | Array of Telegram chat ID strings. Supports users and groups (negative IDs). |
| `cooldown_s` | Minimum seconds between repeated alerts for the same sensor+rule (default 300). Recovery alerts always send immediately. |
| `alerts` | Array of threshold rules (see below) |

- Each rule has an independent enable toggle
- `temp_high_c` fires when **any** sensor exceeds the threshold
- `temp_low_c` fires when **any** sensor drops below the threshold
- **Hysteresis**: alert fires only on state transition - no repeated messages
- **Cooldown**: if a sensor oscillates around a threshold, the same alert will not re-fire until `cooldown_s` has elapsed. Recovery ("back to normal") always sends immediately and resets the cooldown.
- **Low battery**: fires when battery percent drops below `battery.low_pct` (default 20%) while not charging

Alert state per `ruleName:sensorName`: `0` = normal, `1` = high, `-1` = low.

Message format: `[overheat] barn_supply: 42.10C - OVERHEAT (>= 40.0C)`

**MQTT alerting via Lua (alternative):** alerts can also be published from Lua scripts without the TelegramModule:
```lua
MQTT.publish("thesada/node/alert", "custom alert message")
```

---

## Webhook

Optional HTTP POST fired on every alert:

```json
"webhook": {
  "url":              "http://homeassistant.local:8123/api/webhook/thesada-alert",
  "message_template": "{% raw %}{{value}}{% endraw %}"
}
```

`{% raw %}{{value}}{% endraw %}` is replaced with the full alert message. Supports `http://` and `https://` (`setInsecure()`). Leave `url` empty to disable.

**Home Assistant automation for MQTT alerts:**

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
          message: "{% raw %}{{ trigger.payload_json.value }}{% endraw %}"
```
