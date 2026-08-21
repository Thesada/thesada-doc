---
title: Provisioning
parent: Firmware
nav_order: 9
description: "Configure a new device from the serial console or over MQTT: WiFi, broker connection, topic prefix, and verifying the first connection."
---

# Provisioning

Device-side setup for a new node: WiFi, broker connection, and topic prefix, then verifying the first connection. Creating the tenant and broker credentials is a platform-operator step and is out of scope here - this page assumes you already have a broker host, a username and password (or client certificate), and a topic prefix to use.

## Device identity

A device mints its own identity the first time it boots a build that can: a `device_id` derived from the full factory MAC, and an Ed25519 keypair. They live in the `thesada-ident` NVS namespace, which no `secret.*` command can address, and they survive a config reset and a LittleFS reformat.

```text
identity.info
device_id: thesada-0123456789ab
pubkey: 3d40f1...c7
node_name: thesada-0123456789ab
factory-provisioned: false
```

Nothing here is provisioned by an operator. The id is what the fallback AP SSID is built from, and the public key is what proves the device holds its private key when somebody claims it. `identity.reset --yes` is the only way to change either, and it makes the unit a stranger to anything that trusted the old key.

## Seed the fallback AP passphrase at flash time

The fallback AP refuses to start unless `wifi.ap_password` is set to something that is not the shipped `changeme` placeholder and is at least 8 characters. A unit that never had one seeded has no local recovery path when WiFi fails - only a serial cable. Seeding is therefore part of flashing, not a later step.

`scripts/flash-provision.sh` does both halves in one run:

```bash
scripts/flash-provision.sh --env esp32-owb --port /dev/cu.usbmodem1101
```

It uploads the firmware for `--env`, waits for the board to re-enumerate, reads the device id over the serial shell, generates a 24-character alphanumeric passphrase, pushes it with `secret.set wifi.ap_password`, and confirms with `secret.info` that the value actually landed in NVS rather than trusting the response line.

| Flag | Effect |
|---|---|
| `--env <name>` | PlatformIO environment to upload. Required unless `--skip-upload` |
| `--port <path>` | Serial port. Auto-discovered when omitted |
| `--skip-upload` | Seed an already-flashed board, no build or upload |
| `--out <dir>` | Artifact directory. Defaults to `build/provision`, or `PROVISION_DIR` |
| `--force` | Rotate the passphrase on a board that already holds one |

The passphrase is generated inside the script and never crosses argv or stdout. It is written to one 0600 file per device under `build/provision/<device_id>/`:

| File | Contents |
|---|---|
| `ap-credentials.txt` | device id, AP SSID, passphrase, timestamp |
| `join-wifi.txt` | the `WIFI:T:WPA;S:<ssid>;P:<pass>;;` payload a phone can scan |
| `join-wifi.png` | the same payload as a QR image, when the Python `qrcode` module is installed |

Without `qrcode` the PNG is skipped and the text payload still renders through any QR encoder (`qrencode -o join.png < join-wifi.txt`).

NVS is write-only, so those files are the only copy of the passphrase - back them up or the AP cannot be joined again. The script is idempotent: a device that already holds a passphrase and still has its artifact directory is left alone. A device that holds one whose artifact is missing is refused, because the value cannot be read back; `--force` rotates it instead.

Requirements: `python3` with `pyserial`, and `pio` unless you pass `--skip-upload`. A board that reports no device id has not yet booted an image that can mint one - boot a non-rescue build once, then retry.

## Configure over USB serial

Connect to the serial console and set the connection keys. Each `config.set` writes `/config.json` to flash immediately and refreshes the in-memory copy.

WiFi credentials live in the `wifi.networks` array (the firmware only reads that array - flat `wifi.ssid`/`wifi.password` keys are ignored). Initialise the array once, then set entry 0:

```text
config.set wifi.networks []
config.set wifi.networks.0 '{"ssid":"<ssid>","password":"<password>"}'
config.set mqtt.broker <broker-host>
config.set mqtt.port 8883
config.set mqtt.user <username>
config.set mqtt.password <password>
config.set mqtt.topic_prefix <root>/<tenant>/<device-id>
config.reload
```

Passwords can live in NVS instead of `config.json`: provision with
`secret.set wifi.password:<ssid> <password>` (one entry per SSID) and
`secret.set mqtt.password <password>`, then leave the config fields
blank. NVS wins over config at every read site; see
[CLI Reference]({{ site.baseurl }}/firmware/cli-reference/#secrets).

`config.set` persists each key on its own - there is no separate save step in normal use. `config.save` exists only to flush programmatic changes that bypass `config.set`. Network keys (broker, port, credentials, prefix) do not take effect until `config.reload` reconnects the MQTT client; a `restart` also applies them.

## Reconfigure over MQTT

A device that is already connected can be reconfigured over its command topics without serial access. Send the new value to `config.set`, then an empty message to `config.reload` to apply it:

```text
<old-prefix>/cli/config.set      payload: mqtt.topic_prefix <root>/<tenant>/<device-id>
<old-prefix>/cli/config.reload   payload: (empty)
```

The device reconnects on the new prefix.

This needs a certificate-authenticated broker session. On the shared password credential the MQTT CLI is held to what pairing and recovery need, and the only config key it may write is `mqtt.port` - see [CLI Reference]({{ site.baseurl }}/firmware/cli-reference.html#how-to-invoke-a-command). Reconfigure over serial instead, or pair the device first.

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
| `wifi.networks` | `[]` | Known networks array - initialise before setting entries |
| `wifi.networks.0` | `'{"ssid":"MyNetwork","password":"secret"}'` | First network entry (ssid + password) |
| `mqtt.broker` | `<broker-host>` | Broker hostname |
| `mqtt.port` | `8883` | Broker port (TLS) |
| `mqtt.user` | `<username>` | MQTT username |
| `mqtt.password` | `<password>` | MQTT password |
| `mqtt.topic_prefix` | `<root>/<tenant>/<device-id>` | Root of all device topics |
| `wifi.ap_password` | `<passphrase>` | Fallback-AP passphrase. Without a usable value the AP refuses to start; normally seeded by `flash-provision.sh` |
