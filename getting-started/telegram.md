---
title: Telegram
parent: Getting Started
nav_order: 5
---

# Telegram

Telegram is used by all nodes for critical alerts — pump failures, temperature thresholds, boiler faults. This guide covers creating a Telegram bot, finding your chat ID, and adding it to Home Assistant.

---

## Prerequisites

- Home Assistant running and accessible
- A Telegram account and the Telegram app installed on your phone

---

## 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Start a conversation and send `/newbot`
3. Follow the prompts — choose a name and a username (username must end in `bot`)
4. BotFather will return a **bot token** — copy it and keep it somewhere safe

---

## 2. Get Your Chat ID

1. Search for **@getidsbot** in Telegram
2. Send `/start`
3. The bot will return your **chat ID** — copy it

---

## 3. Send Your Bot a Message First

Before adding the chat ID to Home Assistant, open your bot in Telegram and send it `/start`. If you skip this step, Home Assistant will return a "chat not found" error when it tries to send a message.

---

## 4. Add the Telegram Integration to Home Assistant

1. **Settings → Devices & Services → Add Integration**
2. Search for **Telegram bot**
3. Select **Telegram bot**
4. Choose **Polling** as the platform — this requires no port forwarding or public access
5. Enter your bot token and click **Submit**

---

## 5. Add Your Chat ID

1. Go to **Settings → Devices & Services → Telegram bot**
2. Click the three dots → **Add allowed chat ID**
3. Enter your chat ID and click **Submit**

Home Assistant will create a `notify` entity automatically — you will see it listed under **Settings → Devices & Services → Telegram bot**.

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
        {{ trigger.to_state.attributes.friendly_name }} — {{ trigger.to_state.state }}
```

Use `|-` for multiline messages to preserve line breaks.

Full alert automation examples are covered in each module's documentation.