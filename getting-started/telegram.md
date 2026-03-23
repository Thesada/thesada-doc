---
title: Telegram
parent: Getting Started
nav_order: 5
---

# Telegram

Telegram is used by all Thesada nodes for critical alerts - pump failures, temperature thresholds, boiler faults. This guide covers creating a Telegram bot, finding your chat ID, and adding it to Home Assistant.

---

## Prerequisites

- Home Assistant running and accessible
- A Telegram account and the Telegram app installed on your phone

---

## 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Start a conversation and send `/newbot`
3. Follow the prompts - choose a name and a username (username must end in `bot`)
4. BotFather will return a **bot token** - copy it and keep it somewhere safe

---

## 2. Get Your Chat ID

1. Search for **@id_bot** in Telegram
2. Send `/start`
3. The bot will return your **chat ID** - copy it

---

## 3. Send Your Bot a Message First

Before adding the chat ID to Home Assistant, open your bot in Telegram and send it `/start`. If you skip this step, Home Assistant will return a "chat not found" error when it tries to send a message.

---

## 4. Add the Telegram Integration to Home Assistant

1. **Settings → Devices & Services → Add Integration**
2. Search for **Telegram bot**
3. Select **Telegram bot**
4. Choose **Webhooks** as the platform - this requires HTTPS (already configured in the DNS & SSL guide) but delivers incoming commands instantly
5. Enter your bot token and click **Submit**

---

## 5. Add Your Chat ID

1. Go to **Settings → Devices & Services → Telegram bot**
2. Click the three dots → **Add allowed chat ID**
3. Enter your chat ID and click **Submit**

Home Assistant will create a `notify` entity automatically - you will see it listed under **Settings → Devices & Services → Telegram bot**.

---

## 6. Test

In **Developer Tools → Actions**, call the notify service:

```yaml
action: notify.YOUR_NOTIFY_ENTITY
data:
  message: "Thesada Telegram test"
```

You should receive the message on your phone within a few seconds.

---

## Usage in Automations

Thesada alert automations use the notify entity created above. Example:

```yaml
action:
  - action: notify.YOUR_NOTIFY_ENTITY
    data:
      message: |-
        Thesada Alert:
        {{ trigger.to_state.attributes.friendly_name }} - {{ trigger.to_state.state }}
```

Use `|-` for multiline messages to preserve line breaks.

Full alert automation examples are covered in each module's documentation.

---

## Bot Commands

The Telegram webhook integration fires a `telegram_command` event when the bot receives a command. You can handle multiple commands in a single automation using `choose`. Webhook mode requires HTTPS (already configured in the [DNS & SSL guide](ha-dns-ssl)).

### Setup

All bot command automations follow the same structure. Create via **Settings → Automations → Create Automation → Edit in YAML**.

### Example - /temp and /getpic

The automation below handles two commands: `/temp` returns sensor readings, `/getpic` sends a camera snapshot.

```yaml
alias: Telegram Bot Commands
description: Handle bot commands
triggers:
  - trigger: event
    event_type: telegram_command
    event_data:
      command: /temp
  - trigger: event
    event_type: telegram_command
    event_data:
      command: /getpic
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.command == '/temp' }}"
        sequence:
          - action: notify.send_message
            data:
              entity_id: notify.YOUR_NOTIFY_ENTITY
              message: |-
                Thesada - Current Readings:
                {{ states('sensor.YOUR_TEMP_ENTITY') | round(1) }}°C
                {{ states('sensor.YOUR_HUMIDITY_ENTITY') | round(1) }}%
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.command == '/getpic' }}"
        sequence:
          - action: camera.snapshot
            data:
              entity_id: camera.YOUR_CAMERA_ENTITY
              filename: /config/tmp/snapshot.jpg
          - action: telegram_bot.send_photo
            data:
              verify_ssl: true
              entity_id:
                - notify.YOUR_NOTIFY_ENTITY
              file: /config/tmp/snapshot.jpg
mode: single
```

### /getpic - Required Setup

The `camera.snapshot` action writes to `/config/tmp/`. Two things required before this works:

**1. Create the folder** via the HA terminal:

```bash
mkdir /config/tmp
```

**2. Add the path to `allowlist_external_dirs` in `configuration.yaml`:**

```yaml
homeassistant:
  allowlist_external_dirs:
    - /config/tmp
```

Restart Home Assistant after editing `configuration.yaml`.

### Adding More Commands

Each new command is an additional trigger and a new `conditions` / `sequence` block inside `choose`. Keep all commands in a single automation to avoid event conflicts.