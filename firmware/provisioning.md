---
title: Provisioning
parent: Firmware
nav_order: 9
description: "Configure a new device from the serial console or over MQTT: WiFi, broker connection, topic prefix, and verifying the first connection."
---

# Provisioning

Device-side setup for a new node: WiFi, broker connection, and topic prefix, then verifying the first connection. Creating the tenant and broker credentials is a platform-operator step and is out of scope here - this page assumes you already have a broker host, a username and password (or client certificate), and a topic prefix to use.

## Configure over USB serial

Connect to the serial console and set the connection keys. Each `config.set` writes `/config.json` to flash immediately and refreshes the in-memory copy:

```text
config.set wifi.ssid <ssid>
config.set wifi.password <password>
config.set mqtt.broker <broker-host>
config.set mqtt.port 8883
config.set mqtt.user <username>
config.set mqtt.password <password>
config.set mqtt.topic_prefix <root>/<tenant>/<device-id>
config.reload
```

`config.set` persists each key on its own - there is no separate save step in normal use. `config.save` exists only to flush programmatic changes that bypass `config.set`. Network keys (broker, port, credentials, prefix) do not take effect until `config.reload` reconnects the MQTT client; a `restart` also applies them.

## Reconfigure over MQTT

A device that is already connected can be reconfigured over its command topics without serial access. Send the new value to `config.set`, then an empty message to `config.reload` to apply it:

```text
<old-prefix>/cli/config.set      payload: mqtt.topic_prefix <root>/<tenant>/<device-id>
<old-prefix>/cli/config.reload   payload: (empty)
```

The device reconnects on the new prefix.

## Topic prefix

The topic prefix is the root of every topic the device publishes and subscribes to:

```text
<root>/<tenant>/<device-id>
```

Everything the firmware emits (`/status`, `/info`, sensor topics, `/alert`) and every command it accepts (`/cli/...`) hangs off this prefix. See [MQTT Topics]({{ site.baseurl }}/firmware/mqtt-topics/) for the full topic map.

## Verify the first connection

After the device boots with the new config, watch its topics from any broker client:

```sh
# Presence (retained "online")
mosquitto_sub -t '<root>/<tenant>/<device-id>/status' -C 1 -W 30

# Device info (retained)
mosquitto_sub -t '<root>/<tenant>/<device-id>/info' -C 1 -W 10

# Round-trip a CLI command
mosquitto_pub -t '<root>/<tenant>/<device-id>/cli/version' -m ''
```

A retained `online` on `/status` plus an `/info` payload confirm the device is connected and publishing. Add your broker's host, port, TLS, and auth flags to each command.

## Change a device's topic prefix

To move a node to a new prefix:

```text
config.set mqtt.topic_prefix <root>/<new-tenant>/<device-id>
config.reload
```

Confirm it publishes on the new prefix, then clear any retained messages left on the old prefix so stale `/status` and `/info` do not linger.

## Provisioning keys

The keys you touch during provisioning. See [Config Management]({{ site.baseurl }}/firmware/config/) for the full `config.json` schema.

| Key | Example | Purpose |
|---|---|---|
| `wifi.ssid` | `MyNetwork` | WiFi SSID |
| `wifi.password` | `secret` | WiFi password |
| `mqtt.broker` | `<broker-host>` | Broker hostname |
| `mqtt.port` | `8883` | Broker port (TLS) |
| `mqtt.user` | `<username>` | MQTT username |
| `mqtt.password` | `<password>` | MQTT password |
| `mqtt.topic_prefix` | `<root>/<tenant>/<device-id>` | Root of all device topics |
