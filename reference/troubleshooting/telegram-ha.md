---
title: Telegram Alerts in Home Assistant
parent: Troubleshooting
nav_order: 3
description: "Set up Telegram bot alerts in Home Assistant -- webhook mode, automation syntax, bot commands."
---

# Telegram Bot Alerts from Home Assistant

## Overview

Home Assistant can send alerts via Telegram using webhook mode. This is
the preferred approach over polling mode - webhook is faster and uses
fewer resources.

This covers the working setup: HA automations trigger Telegram messages
using `notify.send_message` with the correct syntax.

## Setup

### 1. Create a Telegram bot

Message @BotFather on Telegram:

```
/newbot
```

Follow the prompts. Save the API token.

### 2. Get your chat ID

Message @id_bot (or @userinfobot) on Telegram. It replies with your
numeric chat ID. Save this.

### 3. Configure in HA

Go to **Settings > Devices & Services > Add Integration > Telegram Bot**.

Select **webhooks** as the platform. Enter your bot API token and
allowed chat IDs when prompted.

The integration creates a `notify.telegram` service automatically.

For the full setup guide, see [Telegram Integration](../../getting-started/telegram).

## Automation Syntax

The correct syntax for sending a Telegram message from an automation
uses `notify.send_message` with `entity_id` inside `data`.

Uses the current plural `triggers`/`actions` syntax:

```yaml
automation:
  - alias: "OWB Supply Temp Low"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.house_loop_supply_temp
        below: 40
        for:
          minutes: 5
    actions:
      - action: notify.send_message
        data:
          entity_id: notify.telegram_notify
          message: "OWB supply temp below 40C - check fire"
```

## Common Mistakes

**Wrong service call:** Using `telegram_bot.send_message` instead of
`notify.send_message`. The `telegram_bot.send_message` service exists
but `notify.send_message` with `entity_id` is the current recommended
approach.

**Singular vs plural syntax:** Older HA automation examples use
`trigger:` and `action:` (singular). Current HA versions use
`triggers:` and `actions:` (plural). Both work but plural is the
current standard.

**Webhook mode requires HTTPS:** If HA is not exposed via HTTPS,
webhook mode will not receive incoming messages (bot commands).
Outbound notifications still work without HTTPS. For bot commands
(like `/temp` or `/getpic`), HA must be reachable via HTTPS with a
valid certificate.

## Bot Commands

To receive commands from Telegram (e.g. `/temp` to query current
temperature), add a `telegram_bot` event trigger:

```yaml
automation:
  - alias: "Telegram /temp command"
    triggers:
      - trigger: event
        event_type: telegram_command
        event_data:
          command: "/temp"
    actions:
      - action: notify.send_message
        data:
          entity_id: notify.telegram_notify
          message: >
            House supply: {{ states('sensor.house_loop_supply_temp') }}C
            House return: {{ states('sensor.house_loop_return_temp') }}C
```

