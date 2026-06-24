---
title: Getting Started
nav_order: 2
description: "Flash a bare ESP32-S3, set WiFi over the captive portal, and watch the device publish to MQTT - first device running in about 30 minutes."
---

# Getting Started

Take one bare ESP32-S3 dev board from unboxed to publishing sensor data over MQTT.
No soldering, no custom hardware - a dev board and a USB cable. Plan for about 30
minutes the first time, most of it tool install and the first build.

This walkthrough uses the `esp32-s3-debug` build: USB serial, SHT31 temperature and
humidity sensor enabled, cellular and battery hardware switched off. It is the
firmware's bench target and the right place to start before moving to a field board.

## What you need

| Item | Notes |
|---|---|
| ESP32-S3 dev board | Any bare ESP32-S3 devkit with USB. PSRAM build is assumed (most S3 devkits have it) |
| USB cable | Data cable, not charge-only |
| A computer | macOS, Linux, or Windows with Python 3 and git |
| A WiFi network | 2.4 GHz SSID and password the board can reach |
| `mosquitto` clients | `mosquitto_sub` / `mosquitto_pub`, to watch the device publish |

The SHT31 sensor is optional. Without it the board still boots, connects, and
publishes device telemetry (heap, MQTT status); the temperature rows just stay empty.

## 1. Clone and install the toolchain

The firmware builds with [PlatformIO](https://platformio.org/). Install the CLI
(`pip install platformio`), then clone the repo:

```bash
git clone https://github.com/Thesada/thesada-fw.git
cd thesada-fw
python3 scripts/check_deps.py
```

`check_deps.py` verifies PlatformIO and the pinned library versions before you build.

## 2. Stage the filesystem image

The firmware reads its config and TLS root from a LittleFS partition. Seed both
before flashing:

```bash
cp examples/config.json.example data/config.json
curl -o data/ca.crt https://test.mosquitto.org/ssl/mosquitto.org.crt
```

- `data/config.json` is the editable runtime config. Leave the placeholder WiFi in
  place for now - you will set the real SSID over the web UI in step 5.
- `data/ca.crt` is the CA the device trusts for MQTT over TLS. The firmware always
  uses TLS, so the broker's CA must be present. This walkthrough uses the public
  `test.mosquitto.org` broker, so its CA goes here. For your own broker, use that
  broker's CA instead.

## 3. Build and flash

Plug in the board, then flash the firmware and the filesystem image:

```bash
pio run -e esp32-s3-debug --target upload      # firmware
pio run -e esp32-s3-debug --target uploadfs    # LittleFS (config.json + ca.crt)
```

The first build downloads the toolchain and compiles every module, so it takes a
few minutes; later builds are incremental. A successful `upload` ends like this:

```text
Auto-detected: /dev/ttyACM0
Chip is ESP32-S3 (QFN56) (revision v0.2)
Features: WiFi, BLE, Embedded PSRAM 8MB
Writing at 0x0015ef79... (100 %)
Wrote 1372896 bytes (860762 compressed) at 0x00010000 in 9.0 seconds
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
========================= [SUCCESS] Took 50.28 seconds =========================
```

`uploadfs` then writes the LittleFS image and lists what it packed:

```text
Building FS image from 'data' directory to .pio/build/esp32-s3-debug/littlefs.bin
/ca.crt
/config.json
Wrote ... Hash of data verified.
```

The `/ca.crt` is what lets the TLS broker connection verify in step 6.

## 4. Open the serial console

Watch the boot log at 115200 baud:

```bash
pio device monitor -e esp32-s3-debug
```

The bare S3 uses the chip's native USB-Serial/JTAG, which re-enumerates on reset,
so a monitor opened beforehand stays blank. Press the **RST** button, then launch
the monitor within a couple of seconds: the firmware waits up to 3 s for a USB
host, so it catches the boot from the top. If more than one board is plugged in,
pin the port with `-p /dev/ttyACM0` so you watch the right one.

You should see the modules register, LittleFS mount, and - because the placeholder
WiFi cannot connect - the device fall back to a setup access point:

```text
ESP-ROM:esp32s3-20210327
entry 0x403c98d0
[INF][Boot] thesada-fw <version>
[INF][WiFi] Scanning...
[INF][WiFi] Scan complete: 18 AP(s) visible
[INF][WiFi] Trying primary-ssid (RSSI -67 dBm, attempt 1/2, timeout 10s)...
[WRN][WiFi] All networks failed - starting fallback AP
[WRN][WiFi] Fallback AP: thesada-node-setup (captive portal at 192.168.4.1, timeout 300s)
```

The AP name is `<device name>-setup`, so the default is `thesada-node-setup`. It
times out after 5 minutes and retries the WiFi scan, so if it disappears just wait
for it to come back. (Log lines carry no timestamp until NTP syncs - on the
fallback AP there is no internet yet, so they stay bare.)

## 5. Set WiFi and broker over the captive portal

1. On a laptop or phone, join the `thesada-node-setup` WiFi network. A captive
   portal opens the dashboard automatically; if it does not, browse to
   `http://192.168.4.1/`.
2. Open the **Config** tab and log in. The default credentials from the example
   config are `admin` / `changeme` - change the password before any real
   deployment.
3. The Config tab is a JSON editor holding the full `config.json`. Set your network
   and broker:

   ```json
   "wifi": {
     "networks": [
       { "ssid": "your-ssid", "password": "your-password" }
     ]
   },
   "mqtt": {
     "broker": "test.mosquitto.org",
     "port": 8883,
     "topic_prefix": "thesada/demo/s3-01"
   }
   ```

   `test.mosquitto.org` is open and unauthenticated, so `mqtt.user` and
   `mqtt.password` can stay empty for this first run. Pick a `topic_prefix` unlikely
   to clash with anyone else on the public broker.
4. Click **Save & Restart**. The device writes `config.json`, reboots, and applies
   the new settings.

## 6. Watch it connect and publish

Re-open the serial console (RST, then launch). After the reboot the device joins
your WiFi, syncs NTP, loads the CA, and connects over TLS:

```text
[INF][WiFi] Connected to your-ssid - IP: 192.168.1.42
[INF][MQTT] CA cert loaded from /ca.crt
[INF][MQTT] Connecting as thesada-...
[INF][MQTT] Connected
```

From your computer, subscribe to the device's prefix and watch it publish. Point
`mosquitto_sub` at the same CA you uploaded:

```bash
curl -o mosquitto.org.crt https://test.mosquitto.org/ssl/mosquitto.org.crt
mosquitto_sub --cafile mosquitto.org.crt -h test.mosquitto.org -p 8883 \
  -t 'thesada/demo/s3-01/#' -v
```

```text
thesada/demo/s3-01/status   online
thesada/demo/s3-01/info     {"name":"thesada-node","fw":"...","ip":"192.168.1.42"}
```

A retained `online` on `.../status` plus an `.../info` payload confirm the device is
connected and publishing. Telemetry (heap, MQTT state, and SHT31 readings if the
sensor is attached) follows on its own topics.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| No serial output | Charge-only cable or wrong port | Use a data cable; check the port in `pio device list` |
| Monitor stays blank on an S3 | Native USB re-enumerates on reset | Press RST, then launch the monitor within ~3 s; pin `-p /dev/ttyACMx` if several boards are attached |
| Watching the wrong device | More than one board plugged in | `pio device list`, match by MAC, then `-p` the right port |
| `Could not find port` / permission denied (Linux) | Missing udev rules | Install `99-platformio-udev.rules` (see the PlatformIO udev-rules docs) |
| AP never appears | WiFi actually connected, or AP timed out | Check the log for a connect line; wait for the 5 min retry |
| MQTT never connects | Missing or wrong `ca.crt` | Re-run the `uploadfs` step with the broker's CA in `data/ca.crt` |
| `mosquitto_sub` sees nothing | Prefix mismatch | Match the `-t` filter to the `topic_prefix` you set |

## Next steps

You now have a device that boots, connects, and publishes. From here:

- [Write your own alert rules]({{ site.baseurl }}/firmware/lua-scripting/) - the Lua
  runtime lets you add rules without recompiling.
- [Provisioning]({{ site.baseurl }}/firmware/provisioning/) - the serial-console and
  over-MQTT paths for configuring a device.
- [Config Management]({{ site.baseurl }}/firmware/config/) - the full `config.json`
  schema.
- [Modules]({{ site.baseurl }}/modules/) - what each hardware module does and how to
  enable it.
