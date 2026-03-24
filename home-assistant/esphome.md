---
title: ESPHome Setup in HA
parent: Home Assistant
nav_order: 4
description: "Set up ESPHome in Home Assistant for compiling and flashing firmware to ESP32 sensor nodes."
---

# ESPHome Setup

ESPHome is the firmware platform used by all nodes. It runs as a Home Assistant app and provides a dashboard for managing, compiling, and deploying firmware to ESP32-based devices.

This guide covers:
- Installing the ESPHome Device Builder app in Home Assistant
- Enabling SSL
- Creating your secrets file
- First flash via CLI (required on macOS)
- OTA updates for all subsequent deployments

---

## Prerequisites

- Home Assistant running and accessible
- Let's Encrypt certificate already obtained (see [Home Assistant DNS & SSL](ha-dns-ssl.md))
- ESPHome CLI installed on your PC/Mac:

```bash
pipx install esphome
pipx ensurepath
```

Verify:

```bash
esphome version
```

---

## 1. Install ESPHome Device Builder

1. **Settings → Apps → App Store**
2. Search **ESPHome**
3. Click **ESPHome Device Builder**
4. Click **Install**
5. Enable **Start on boot** and **Watchdog**

---

## 2. Enable SSL

Before starting the app, go to the **Configuration** tab and set:

```yaml
ssl: true
certfile: fullchain.pem
keyfile: privkey.pem
```

Click **Save**.

This uses the Let's Encrypt certificate from the Mosquitto setup. No additional certificate work needed.

---

## 3. Start and Open Dashboard

1. Click **Start**
2. Click **Open Web UI**

You will be asked for your Home Assistant credentials - ESPHome uses HA's authentication system.

---

## 4. Create secrets.yaml

All sensitive values - WiFi credentials, API keys, OTA passwords - are stored in a `secrets.yaml` file in the ESPHome dashboard, never in the device config directly.

In the ESPHome dashboard:
1. Click **Secrets** in the top right
2. Create the file with your values:

```yaml
wifi_ssid: "your-wifi-ssid"
wifi_password: "your-wifi-password"
api_encryption_key: "your-32-byte-base64-key"
ota_password: "your-ota-password"
```

**Generate the API encryption key:**
```bash
openssl rand -base64 32
```

**Generate the OTA password:**
```bash
openssl rand -base64 24
```

---

## 5. First Flash - CLI Method (macOS)

ESPHome's browser-based Web Serial flash does not work reliably on macOS with the Freenove ESP32-S3 WROOM. Use the CLI for the first flash. All subsequent updates are OTA.

### Download the config and binary

1. In the ESPHome dashboard, create your device and edit the config
2. Click **Install → Manual download → Modern format** - save the `.factory.bin` file
3. Click the **three dots** menu on the device → **Download configuration** - save the `.yaml` file
4. Copy your `secrets.yaml` from the ESPHome dashboard to the same folder as the downloaded `.yaml`

### Flash via CLI

```bash
esphome upload --file ~/Downloads/thesada-DEVICE.factory.bin \
  ~/Downloads/thesada-DEVICE.yaml
```

Replace `thesada-DEVICE` with your device name.

---

## 6. Verify Connection

After flashing, confirm the device is online:

```bash
esphome logs ~/Downloads/thesada-DEVICE.yaml
```

You should see WiFi connecting, then the API handshake completing. Home Assistant will auto-discover the device via the ESPHome integration.

---

## 7. OTA Updates

Once the device is online and connected to HA, all subsequent firmware updates are wireless:

1. Edit the config in the ESPHome dashboard
2. Click **Install → Wirelessly**

No USB cable needed.

---

## Storing Configs in GitHub

All ESPHome configs belong in the `thesada-cfg` repo under `esphome/`:

```
thesada-cfg/
└── esphome/
    ├── secrets.yaml.example
    ├── .gitignore
    └── thesada-sht31.yaml
```

The `.gitignore` prevents `secrets.yaml` from being committed. Only `secrets.yaml.example` is tracked.

**Never commit real credentials to the repo.**