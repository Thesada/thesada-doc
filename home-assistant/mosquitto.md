---
title: MQTT Integration in HA
parent: Home Assistant
nav_order: 3
description: "Configure the Mosquitto MQTT broker as a Home Assistant add-on with TLS encryption."
---

# Mosquitto MQTT Broker

Mosquitto is the MQTT broker used by all nodes. It runs as a Home Assistant app and handles all sensor data published by ESPHome nodes - both on the local network and remotely over cellular.

This guide covers:
- Installing and configuring Mosquitto in Home Assistant
- Creating an MQTT user
- Configuring Mosquitto for secure external access on port 8883

---

## Prerequisites

- Home Assistant running and accessible (see [Proxmox - HAOS Install](proxmox-haos.md))
- DNS, DDNS, and Let's Encrypt certificate configured (see [Home Assistant DNS & SSL](ha-dns-ssl.md))
- A router capable of custom port forwarding rules

---

## 1. Install Mosquitto

Mosquitto is a Home Assistant add-on (app), not an integration. Install it from the App Store.

1. **Settings → Apps → App Store**
2. Search **Mosquitto broker**
3. Click **Mosquitto broker** and click **Install**
4. Enable **Start on boot** and **Watchdog**
5. Click **Start**

### Add the MQTT Integration

Once the broker is running, Home Assistant should auto-discover it and prompt you to add the MQTT integration. If it doesn't:

1. **Settings → Devices & Services → Add Integration**
2. Search **MQTT** and select it
3. Click **Submit** - HA will connect to the local Mosquitto broker automatically

---

## 2. Create an MQTT User

All nodes authenticate with a dedicated MQTT user.

1. **Settings → Apps → Mosquitto broker**
2. Select the **Configuration** Tab
3. Click **Add** in **Options → Logins**
4. Set a username (e.g. `mqtt-user`) and a strong password (24+ characters recommended)
5. This user exists only for broker authentication

---

## 3. Test Local MQTT

From a machine on the same network, confirm the broker is reachable. Install the Mosquitto client tools if needed.

Open two terminals.

**Terminal 1 - subscribe:**
```bash
mosquitto_sub -h YOUR_HA_IP -p 1883 \
  -u mqtt-user -P YOUR_PASSWORD \
  -t 'test/#' -v
```

**Terminal 2 - publish:**
```bash
mosquitto_pub -h YOUR_HA_IP -p 1883 \
  -u mqtt-user -P YOUR_PASSWORD \
  -t 'test/hello' -m 'world'
```

Terminal 1 should print `test/hello world`. If you see `Connection Refused: not authorised`, check your username and password.

---

## 4. Port Forwarding

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

## 5. TLS Certificate

Mosquitto must use TLS for any external connections. The certificate is obtained via Let's Encrypt - see [Home Assistant DNS & SSL](ha-dns-ssl.md) for the full setup. Complete that guide before continuing here.

---

## 6. Configure Mosquitto for TLS

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

## 7. Test External MQTT

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

You should see `test/hello world` in the subscribe terminal. If the connection is refused, verify your port forwarding rule and confirm the certificate was issued successfully in the Let's Encrypt app logs.

---

## Summary

| Component | Status check |
|---|---|
| Mosquitto running | HA → Settings → Apps → Mosquitto → green |
| MQTT integration | HA → Settings → Integrations → MQTT → connected |
| DDNS updating | See [Home Assistant DNS & SSL](ha-dns-ssl.md) |
| Port 8883 open | External `mosquitto_sub` connects |
| TLS active | Connection uses port 8883 without certificate errors |