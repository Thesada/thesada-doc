---
title: Mosquitto MQTT Broker
parent: Getting Started
nav_order: 2
---

# Mosquitto MQTT Broker

Mosquitto is the MQTT broker used by all nodes. It runs as a Home Assistant add-on and handles all sensor data published by ESPHome nodes — both on the local network and remotely over cellular.

This guide covers:
- Installing and configuring Mosquitto in Home Assistant
- Creating an MQTT user
- Setting up Cloudflare DDNS for a dynamic IP
- Obtaining a TLS certificate via Let's Encrypt and Cloudflare DNS challenge
- Configuring Mosquitto for secure external access on port 8883

---

## Prerequisites

- Home Assistant running and accessible (see [Proxmox — HAOS Install](proxmox-haos.md))
- A Cloudflare account managing your domain
- A Cloudflare API token with `Zone:DNS:Read` and `Zone:DNS:Edit` permissions
- A router capable of custom port forwarding rules

---

## 1. Install Mosquitto

1. In Home Assistant go to **Settings → Devices and services → Add integration**
2. Search for **MQTT**
3. Select **MQTT**
4. Click **Install**
5. Once installed, select the **Mosquitto Mqtt Broker** service in the integration and enable **Start on boot** and **Watchdog**
6. Click **Start**

---

## 2. Create an MQTT User

All nodes authenticate with a dedicated MQTT user.

1. **Settings → Apps → Mosquitto broker**
2. Select the **Configuration** Tab
3. Click **Add** in **Options → Logins**
3. Set a username (e.g. `mqtt-user`) and a strong password (24+ characters recommended)
4. This user exists only for broker authentication

---

## 3. Test Local MQTT

From a machine on the same network, confirm the broker is reachable. Install the Mosquitto client tools if needed.

Open two terminals.

**Terminal 1 — subscribe:**
```bash
mosquitto_sub -h YOUR_HA_IP -p 1883 \
  -u mqtt-user -P YOUR_PASSWORD \
  -t 'test/#' -v
```

**Terminal 2 — publish:**
```bash
mosquitto_pub -h YOUR_HA_IP -p 1883 \
  -u mqtt-user -P YOUR_PASSWORD \
  -t 'test/hello' -m 'world'
```

Terminal 1 should print `test/hello world`. If you see `Connection Refused: not authorised`, check your username and password.

---

## 4. Cloudflare DDNS

Remote nodes connect to the MQTT broker over the internet. Since your home IP is dynamic, you need a DNS record that updates automatically.

### Create the DNS record

1. Log in to Cloudflare
2. Select your domain
3. **DNS → Records → Add record**
   - Type: `A`
   - Name: `mqtt` (resolves to `mqtt.yourdomain.com`)
   - IPv4: your current public IP (find it at for example [ifconfig.me](https://ifconfig.me))
   - Proxy: **OFF** (grey cloud — DNS only) — MQTT is TCP, Cloudflare proxy does not support it

### Create a Cloudflare API token

1. Cloudflare dashboard → **My Profile → API Tokens**
2. Click **Create Token**
3. Use the **Edit zone DNS** template
4. Scope it to your specific zone (domain)
5. Copy the token — you will need it in the next step

### Install Cloudflare DDNS add-on

1. In Home Assistant go to **Settings → Devices & services → Add integration**
2. Search **Cloudflare**
3. Select **Cloudflare** (**Not Cloudflare R2**)
4. Enter your API token and click **Submit**
5. Select the Zone, then the Domain to update and click **Submit**

The add-on checks your public IP periodically and updates the Cloudflare A record automatically when it changes.

---

## 5. Port Forwarding

On your router, create a port forwarding rule:

| Field | Value |
|---|---|
| External port | 8883 |
| Internal IP | YOUR_HA_IP |
| Internal port | 8883 |
| Protocol | TCP |

Port 8883 is the standard MQTT over TLS port. Never expose port 1883 (plain text) externally.

Consult your router's documentation for port forwarding instructions.

---

## 6. Let's Encrypt TLS Certificate

Mosquitto must use TLS for any external connections. The certificate is obtained via Let's Encrypt using the Cloudflare DNS challenge — no port 80 required.

### Configure the Let's Encrypt add-on

1. In Home Assistant go to **Settings → Apps**
2. Open the **Let's Encrypt** add-on (install if not present)
3. Go to the **Configuration** tab and set:

```yaml
domains:
  - mqtt.yourdomain.com
certfile: fullchain.pem
keyfile: privkey.pem
challenge: dns
email: you@yourdomain.com
dns:
  provider: dns-cloudflare
  cloudflare_api_token: YOUR_CLOUDFLARE_API_TOKEN
```

4. Click **Save**

The add-on will obtain a certificate and store it at:
- `/data/letsencrypt/live/mqtt.yourdomain.com/fullchain.pem`
- `/data/letsencrypt/live/mqtt.yourdomain.com/privkey.pem`

### Auto-renewal

Let's Encrypt certificates expire every 90 days. The add-on does **not** auto-renew — you must set up an automation to restart it every 60 days.

In Home Assistant go to **Settings → Automations → Create Automation → Edit in YAML** and paste:

```yaml
alias: Let's Encrypt Auto-Renew
description: Restart Let's Encrypt add-on every 60 days to renew certificate
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: template
    value_template: >
      {{ (now() - states.automation.lets_encrypt_auto_renew.attributes.last_triggered).days >= 60 }}
action:
  - service: hassio.addon_restart
    data:
      addon: core_letsencrypt
mode: single
```

---

## 7. Configure Mosquitto for TLS

Now that the certificate exists, enable TLS in Mosquitto.

1. Go to **Settings → Apps → Mosquitto broker**
2. Update to:

```yaml
...
certfile: fullchain.pem
keyfile: privkey.pem
...
```

3. Click **Save** and **Restart**

---

## 8. Test External MQTT

From any machine outside your network (or using your domain instead of local IP):

**Subscribe:**
```bash
mosquitto_sub -h mqtt.yourdomain.com -p 8883 \
  -u mqtt-user -P YOUR_PASSWORD \
  -t 'test/#' -v
```

**Publish:**
```bash
mosquitto_pub -h mqtt.yourdomain.com -p 8883 \
  -u mqtt-user -P YOUR_PASSWORD \
  -t 'test/hello' -m 'world'
```

You should see `test/hello world` in the subscribe terminal. If the connection is refused, verify your port forwarding rule and confirm the certificate was issued successfully in the Let's Encrypt add-on logs.

---

## Summary

| Component | Status check |
|---|---|
| Mosquitto running | HA → Add-ons → Mosquitto → green |
| MQTT integration | HA → Settings → Integrations → MQTT → connected |
| DDNS updating | Cloudflare A record matches your public IP |
| Port 8883 open | External `mosquitto_sub` connects |
| TLS active | Connection uses port 8883 without certificate errors |