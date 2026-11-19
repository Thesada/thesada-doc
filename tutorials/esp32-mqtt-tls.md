---
title: ESP32 MQTT over TLS with a private CA
parent: Tutorials
nav_order: 3
description: "ESP32 MQTT over TLS against Mosquitto with your own CA: create the certificates, configure the 8883 listener, load the CA in WiFiClientSecure and PubSubClient, add client certificates, and avoid the usual traps."
---

# ESP32 MQTT over TLS with a private CA

You run your own Mosquitto broker and want the ESP32 to talk to it encrypted, checking that it really is your broker, without buying a certificate. That takes a small CA of your own, a broker certificate signed by it, and the CA certificate on the ESP32. This page covers the general setup on Arduino-ESP32 first, with a sketch that compiles, then how Thesada does the same thing.

The short version:

| Piece | Where it lives | Secret |
|---|---|---|
| `ca.key` | offline, on the machine that signs | yes, it can mint any certificate your devices will trust |
| `ca.crt` | on the broker (for client certificates) and on every ESP32 | no |
| `server.key`, `server.crt` | on the broker | the key is |
| `client.key`, `client.crt` | on one ESP32, only with client certificates | the key is |

## 1. Two kinds of TLS

| | Server-only TLS | Mutual TLS (mTLS) |
|---|---|---|
| Broker proves its identity | yes, with `server.crt` | yes |
| Device proves its identity | with a username and password inside the encrypted session | with its own certificate, during the handshake |
| On the device | `ca.crt` | `ca.crt`, `client.crt`, `client.key` |
| Usual port | 8883 | any second TLS listener, 8884 in this page |

Start with server-only TLS. Add client certificates when one shared password for all devices stops being good enough.

## 2. Create the CA and the broker certificate

The CA, valid ten years. `openssl` asks for a passphrase for `ca.key`:

```bash
openssl req -new -x509 -days 3650 -extensions v3_ca -keyout ca.key -out ca.crt -subj "/CN=Home MQTT CA"
```

The broker key and a signing request. The name is the DNS name your devices will connect to:

```bash
openssl genrsa -out server.key 2048
openssl req -new -key server.key -out server.csr -subj "/CN=mqtt.example.com"
```

Sign it with the CA, and put the name into the certificate as a subject alternative name:

```bash
echo "subjectAltName=DNS:mqtt.example.com" > san.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -extfile san.ext
```

Three things to get right here:

- Give the CA and the broker certificate different subjects. Mosquitto's own guide warns that identical subjects lead to errors that are hard to diagnose.
- Use the name, not an IP address. The client compares the host it connects to with the names in the certificate.
- Set the subject alternative name. The ESP32 falls back to the CN when a certificate has no alternative names, but the `mosquitto_pub` and `mosquitto_sub` you test with may not.

## 3. Configure Mosquitto

```text
listener 8883
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key

allow_anonymous false
password_file /etc/mosquitto/passwd
```

`certfile` and `keyfile` together turn TLS on for that listener. The `openssl` commands left the files in your working directory, so copy them to where the config looks. Mosquitto 2 drops to the `mosquitto` user before it loads them, so that user has to own the key and nobody else may read it:

```bash
sudo install -d -m 0755 /etc/mosquitto/certs
sudo install -m 0644 server.crt ca.crt /etc/mosquitto/certs/
sudo install -m 0600 -o mosquitto -g mosquitto server.key /etc/mosquitto/certs/
```

Create the password file and give it the same owner and mode:

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd demo
sudo chown mosquitto:mosquitto /etc/mosquitto/passwd
sudo chmod 0600 /etc/mosquitto/passwd
```

`-c` creates the file and overwrites one that already exists, with every user in it. To add a user to an existing file, leave it out: `sudo mosquitto_passwd /etc/mosquitto/passwd another-user`.

Restart the broker so the listener picks up the certificate, and check that it came up:

```bash
sudo systemctl restart mosquitto
sudo systemctl status mosquitto
```

Test from another machine before touching the ESP32. If this fails, the sketch will too:

```bash
mosquitto_pub -h mqtt.example.com -p 8883 --cafile ca.crt -u demo -P demo-password -t demo/hello -m hi
```

## 4. The ESP32 side

This compiles against Arduino-ESP32 3.3 and PubSubClient 2.8 for an ESP32-S3. It has not been run against a device for this page.

```cpp
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

const char* WIFI_SSID = "your-ssid";
const char* WIFI_PASS = "your-password";

// Your ca.crt, pasted whole. The client keeps the pointer, so keep it global.
const char* CA_CERT = R"PEM(
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)PEM";

WiFiClientSecure tls;
PubSubClient mqtt(tls);
char clientId[24];  // unique per board, see below

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) delay(250);

  snprintf(clientId, sizeof(clientId), "esp32-%012llx", ESP.getEfuseMac());
  tls.setCACert(CA_CERT);
  mqtt.setServer("mqtt.example.com", 8883);  // the name in the server certificate
}

void loop() {
  if (!mqtt.connected()) {
    if (mqtt.connect(clientId, "demo", "demo-password")) {
      mqtt.publish("demo/hello", "connected over TLS");
    } else {
      Serial.printf("mqtt connect failed, state=%d\n", mqtt.state());
      delay(5000);
    }
  }
  mqtt.loop();
}
```

What the calls do:

| Call | Effect |
|---|---|
| `tls.setCACert(pem)` | the broker certificate must chain to this CA. The string is not copied, so it has to outlive the client |
| `mqtt.setServer(name, 8883)` | the name is sent as SNI and compared with the certificate |
| `tls.setInsecure()` | encrypts without checking who is on the other end. Fine for five minutes of debugging, not for a device you leave running |

The client ID comes from the chip's factory MAC, so every board gets its own. The broker keeps one session per client ID and drops the older connection when a second one logs in with the same ID. Two boards flashed with a fixed ID knock each other off, reconnect in `loop()`, and keep doing that.

Traps that cost an evening:

- `state=-2` from PubSubClient means the network connection failed before MQTT started. With TLS that includes a failed handshake, so check the CA and the name first.
- PubSubClient's packet buffer is 256 bytes by default, and the topic and the payload share it. A publish that does not fit returns `false` and nothing is sent. Raise it with `mqtt.setBufferSize()`.

## 5. Certificate dates and the clock

This one surprises people in both directions.

The prebuilt libraries that ship with Arduino-ESP32 are built without the ESP-IDF option `CONFIG_MBEDTLS_HAVE_TIME_DATE`. With that option off, the "valid from" and "valid to" fields of a certificate are ignored. So:

| Build | Dates checked | Needs a correct clock |
|---|---|---|
| Arduino-ESP32, prebuilt libraries | no | no |
| An ESP-IDF build with `CONFIG_MBEDTLS_HAVE_TIME_DATE=y` | yes | yes, before the first handshake |

On the stock Arduino build an expired broker certificate keeps working on the ESP32 while `mosquitto_sub` on your laptop already refuses it. Nothing on the device will tell you to rotate, so put the expiry date in a calendar.

With the option on, an ESP32 that has not set its clock yet rejects every certificate as not yet valid. Sync time first, for example with `configTime(0, 0, "pool.ntp.org")`, and wait for it before connecting.

## 6. Client certificates

Each device gets its own key and a certificate signed by the same CA. The CN becomes the device's identity:

```bash
openssl genrsa -out client.key 2048
openssl req -new -key client.key -out client.csr -subj "/CN=esp32-demo"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365
```

A second listener on the broker asks for it:

```text
listener 8884
cafile /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/server.crt
keyfile /etc/mosquitto/certs/server.key
require_certificate true
use_identity_as_username true
```

| Option | Effect |
|---|---|
| `cafile` | the CA that client certificates are checked against |
| `require_certificate true` | no valid client certificate, no connection |
| `use_identity_as_username true` | the certificate CN is used as the MQTT username, and the password file is not used on this listener |

Neither listener limits topics. Any device that gets in can publish and subscribe to everything, including another device's topics. Before you rely on one certificate per device for isolation, add an `acl_file`. A minimal one that keeps each certificate under its own CN and lets the `demo` password user keep `demo/`:

```text
user demo
topic readwrite demo/#

pattern readwrite devices/%u/#
```

Point the broker at it with `acl_file /etc/mosquitto/acl`, give it the same owner and mode as the password file, and restart. With an ACL file loaded, every topic it does not grant is denied. The format is in [mosquitto.conf(5)](https://mosquitto.org/man/mosquitto-conf-5.html) under `acl_file`.

On the ESP32, add the two PEM strings and connect without a password:

```cpp
tls.setCACert(CA_CERT);
tls.setCertificate(CLIENT_CERT);  // client.crt
tls.setPrivateKey(CLIENT_KEY);    // client.key
mqtt.setServer("mqtt.example.com", 8884);
// ...
mqtt.connect(clientId);  // the per-board ID from above
```

Both listeners can run side by side: 8883 with a password for devices that have no certificate yet, 8884 for those that do.

## 7. How Thesada does it

<!-- claim: repo=thesada-fw file=platformio.ini match="knolleary/PubSubClient" -->
[Thesada](https://github.com/Thesada/thesada-fw) is an open-source ESP32 firmware built on Arduino-ESP32 and PubSubClient. Everything in this section is read from the firmware source.

<!-- claim: repo=thesada-fw file=src/thesada_config.h match="#define MQTT_TLS  true" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="cfg\[\"mqtt\"\]\[\"port\"\]            \| 8883;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="if \(LittleFS.exists\(\"/ca.crt\"\)\) \{" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="_caCert    = OTA_CA_PROGMEM;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="mqtt.tls_refused reason=no_ca allow_insecure=unset" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="connect\(brokerIp, _brokerPort, _brokerHost" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="cfg\[\"mqtt\"\]\[\"buffer_in\"\]  \| 4096;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="_client.setBufferSize\(_bufferIn\);" -->

| Piece | Thesada |
|---|---|
| TLS | on at compile time, default port 8883 from `mqtt.port` |
| CA | `/ca.crt` on the LittleFS partition, a PEM file, so a private CA is one file and no rebuild |
| No `/ca.crt` | a bundle of public roots compiled into the firmware is used instead |
| No CA at all | the client refuses to connect. `setInsecure()` is only reachable with `mqtt.allow_insecure` set |
| Name check | the firmware resolves the broker name itself, dials the address, and still hands the name to the TLS client for SNI and the certificate check |
| Packet buffer | `mqtt.buffer_in`, default 4096 bytes |

<!-- claim: repo=thesada-fw file=docs/invariants.md match="### Certificate validity dates are not enforced, at any clock value" -->
<!-- claim: repo=thesada-fw file=platformio.ini match="framework = arduino" -->
Certificate dates are not enforced, for the reason in step 5: Thesada builds on the prebuilt Arduino-ESP32 libraries. The chain to the CA and the name are checked. Expiry is not, so rotating a broker certificate is something you schedule.

### Client certificates

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="static const char\* CERT_NS        = \"thesada-tls\";" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="type: client_cert\|client_key" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.h match="static constexpr size_t CERT_MAX_LEN = 4000;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="if \(validateClientCertKey\(_clientCert, _clientKey\)\) \{" -->
<!-- claim: repo=thesada-fw file=src/thesada_config.h match="#define MQTT_MTLS_PORT 8884" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="if \(_brokerPort == MQTT_MTLS_PORT\) \{" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="mqtt.mtls_port_mismatch port=%u mtls_port=%u fallback=password" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/MQTTClient.cpp match="ok = _client.connect\(clientId, nullptr, nullptr, \w+, 0, true, \"offline\"\);" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Shell.cpp match="Cert \+ key present - rebooting in 3s to apply \(mTLS on next boot\)" -->

The client certificate and key are not compiled in and not in the config file. They live in NVS, and `cert.set` puts them there on a running device:

| Step | What happens |
|---|---|
| Push | `cert.set` over MQTT, once for `client_cert` and once for `client_key`, PEM, under 4000 bytes each |
| Apply | `cert.apply` restarts the device |
| Connect | the pair is loaded from NVS and checked with mbedTLS: the certificate must parse and the key must be its private half |
| Listener | the pair is only presented when `mqtt.port` is the mTLS port, 8884 by default. On any other port the session uses the username and password |
| Login | on the mTLS listener no username or password is sent. The broker takes the identity from the certificate, as in step 6 |

So a device can start on 8883 with a password, receive its certificate over that session, and move to 8884 once `mqtt.port` says so.

Where `/ca.crt` comes from, how to replace it on a running device, and the public roots in the built-in bundle are in the [CA certificate reference]({{ site.baseurl }}/firmware/architecture/connectivity.html#ca-certificate).

## Sources

| Topic | Source |
|---|---|
| `openssl` commands, distinct subjects | [mosquitto-tls(7)](https://mosquitto.org/man/mosquitto-tls-7.html) |
| `listener`, `certfile`, `keyfile`, `cafile`, `require_certificate`, `use_identity_as_username`, `acl_file` | [mosquitto.conf(5)](https://mosquitto.org/man/mosquitto-conf-5.html) |
| `setCACert`, `setCertificate`, `setPrivateKey`, `setInsecure`, SNI | [arduino-esp32: NetworkClientSecure](https://github.com/espressif/arduino-esp32/tree/master/libraries/NetworkClientSecure) |
| Buffer size, `state()` codes | [PubSubClient.h](https://github.com/knolleary/pubsubclient/blob/v2.8/src/PubSubClient.h) |
| `CONFIG_MBEDTLS_HAVE_TIME_DATE` | [ESP-IDF: components/mbedtls/Kconfig](https://github.com/espressif/esp-idf/blob/v5.5/components/mbedtls/Kconfig) |
| Name check, alternative names before CN | [Mbed TLS: library/x509_crt.c](https://github.com/Mbed-TLS/mbedtls/blob/v3.6.4/library/x509_crt.c) |
