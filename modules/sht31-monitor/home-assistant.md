---
title: Home Assistant
parent: SHT31 Monitor
nav_order: 3
---

# SHT31 Monitor — Home Assistant

Once the SHT31 node is flashed and online, Home Assistant auto-discovers it via the ESPHome integration. This page covers verifying the entities and setting up hourly Telegram alerts.

---

## Prerequisites

- Telegram bot created and token obtained from @BotFather
- Chat ID obtained from @getidsbot
- Telegram bot integration set up in Home Assistant (see below)

---

## 1. Verify ESPHome Entities

1. **Settings → Integrations → ESPHome**
2. Find `thesada-sht31` — it should appear automatically once the device is online
3. Click the device — you should see two entities:
   - `sensor.thesada_sht31_temperature`
   - `sensor.thesada_sht31_humidity`

If the device does not appear, check that HA and the ESP32 are on the same network and the API encryption key in the ESPHome config matches the one in `secrets.yaml`.

---

## 2. Set Up Telegram Bot Integration

### Create the bot and get your chat ID

1. In Telegram open a chat with **@BotFather** and send `/newbot`
2. Follow the instructions — save the API token
3. Send any message to **@getidsbot** and send `/start` — note your chat ID
4. Open a chat with your new bot and send `/start` — **this step is required**, the bot cannot find your chat without an initial message from you

### Add the integration

1. **Settings → Integrations → Add Integration**
2. Search **Telegram bot**
3. Select **Polling**
4. Enter your API token and click **Submit**
5. Assign to a room if desired, click **Finish**

### Allowlist your chat ID

1. **Settings → Integrations**
2. Find **Telegram bot**
3. Select **Add allowed chat ID**
4. Enter your chat ID and click **Submit**

A notify entity will be created automatically once the chat ID is added.

---

## 3. Hourly Telegram Alert Automation

This automation sends temperature and humidity readings to Telegram every hour.

1. **Settings → Automations → Create Automation**
2. Click **Create new automation**
3. Click **Edit in YAML**
4. Paste the following — replace `notify.YOUR_NOTIFY_ENTITY` with your actual notify entity ID:

```yaml
alias: SHT31 Hourly Telegram Report
description: Send temperature and humidity from SHT31 to Telegram every hour
trigger:
  - platform: time_pattern
    hours: "/1"
action:
  - action: notify.send_message
    data:
      entity_id: notify.YOUR_NOTIFY_ENTITY
      message: |-
        Thesada SHT31 Report:
        Temperature: {{ states('sensor.thesada_sht31_temperature') | round(2) }}°C
        Humidity: {{ states('sensor.thesada_sht31_humidity') | round(2) }}%
mode: single
```

5. Click **Save**

### Find your notify entity ID

**Settings → Integrations → Telegram bot** — the notify entity is listed under the integration. It will be something like `notify.telegram_bot_YOUR_NAME`.

### Test the automation

**Settings → Automations** → find the automation → click the **three dots** → **Run**. You should receive a Telegram message immediately.

---

## Message Format

The automation uses `|-` YAML block style to preserve newlines in the Telegram message. This produces a clean multi-line message:

```
Thesada SHT31 Report:
Temperature: 23.84°C
Humidity: 42.10%
```

Always use `|-` for multiline Telegram messages in HA automations if you want to preserve new lines.