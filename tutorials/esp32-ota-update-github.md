---
title: ESP32 OTA update from a GitHub release
parent: Tutorials
nav_order: 2
description: "ESP32 OTA update from a GitHub release URL with Arduino-ESP32: follow the redirect over TLS, check the SHA256 before the image is activated, and make rollback actually work."
---

# ESP32 OTA update from a GitHub release, with SHA256 check and rollback

You build a `firmware.bin`, attach it to a GitHub release, and want the ESP32 to pull it over HTTPS, refuse a damaged download, and fall back to the old firmware when the new one does not come up. This page covers the general mechanism on Arduino-ESP32 first, with one sketch that compiles, then how Thesada does the same thing.

The short version:

| Step | What does it | The trap |
|---|---|---|
| Find the file | a release asset URL | it answers with a redirect to another host |
| Trust the server | a root CA for every host in the chain | one pinned root is not enough |
| Trust the file | SHA256 over the bytes as they are written | compare before `Update.end()`, not after |
| Switch over | `Update.end()` sets the boot slot | needs two OTA slots and `otadata` |
| Fall back | bootloader rollback | Arduino-ESP32 confirms the new image before `setup()` |

## 1. The partition table

OTA needs a partition table with at least two OTA app slots, `ota_0` and `ota_1`, and an OTA data partition (`otadata`). The update is written to whichever slot is not selected for booting, and `otadata` records which slot boots next. A table with a single `factory` app and no OTA slots cannot do any of this.

A table that works on a 4 MB module:

```text
# Name,   Type, SubType, Offset,   Size
nvs,      data, nvs,     0x9000,   0x5000
otadata,  data, ota,     0xe000,   0x2000
app0,     app,  ota_0,   0x10000,  0x1E0000
app1,     app,  ota_1,   0x1F0000, 0x1E0000
spiffs,   data, spiffs,  0x3D0000, 0x30000
```

Your binary has to fit one slot, not the whole flash.

## 2. The release URL redirects

GitHub gives every uploaded release asset two stable URLs:

| URL | Points at |
|---|---|
| `https://github.com/OWNER/REPO/releases/download/TAG/firmware.bin` | the asset of one tag |
| `https://github.com/OWNER/REPO/releases/latest/download/firmware.bin` | the same file name on the latest release |

Neither serves the file. Both answer `302` with a `Location` header, and the bytes come from a separate asset host. Look at it yourself:

```bash
curl -sIL https://github.com/OWNER/REPO/releases/latest/download/firmware.bin | grep -iE '^(HTTP|location)'
```

Two things follow for the ESP32:

- `HTTPClient` does not follow redirects by default. Turn it on with `setFollowRedirects()`, or the request ends with status 302 and no body.
- The TLS client needs a root CA for `github.com` and one for the asset host. They are different hosts and their certificates can come from different CAs. Load the roots as one PEM string, one certificate after the other. Check which roots you need with `openssl s_client -connect HOST:443 -showcerts` for each host in the chain, and check again when an update starts failing with a certificate error.

`setInsecure()` makes the error go away and lets anyone on the path hand you a firmware image.

## 3. Check the SHA256 before the image is activated

`Update.write()` only puts bytes into the spare slot. Nothing changes for the next boot until `Update.end()` succeeds. So hash the stream while writing, compare at the end, and call `Update.abort()` on a mismatch. The running firmware stays the boot image.

Know what the hash proves. A SHA256 you publish next to the binary proves the download is complete and unchanged. It does not prove who built it: whoever can replace the binary on the server can replace the hash too. The TLS check in step 2 is what ties both to the server you meant. Signed images are a separate ESP-IDF feature and not covered here.

## 4. Rollback, and why it does nothing by default

With rollback support in the bootloader, a freshly installed image boots in state `ESP_OTA_IMG_PENDING_VERIFY`. The app then has to say it works:

| Call | Result |
|---|---|
| `esp_ota_mark_app_valid_cancel_rollback()` | image is confirmed and stays |
| `esp_ota_mark_app_invalid_rollback_and_reboot()` | image is marked invalid, the previous one boots |
| neither, then any reset | the bootloader marks the image aborted and boots the previous one |

The prebuilt Arduino-ESP32 bootloader has this enabled. The catch is in the core: `initArduino()` runs before your `setup()` and, when the image is pending, calls `esp_ota_mark_app_valid_cancel_rollback()` right there. A firmware that crashes in `setup()` is already confirmed by then and boot-loops forever.

The core has a hook for it. Define `verifyRollbackLater()` and return `true`, and the core leaves the image pending. From then on the confirm is your job:

- Confirm only after something that proves the firmware works, for example WiFi is up and your server answered.
- A firmware that hangs without resetting is never rolled back. Give the self-test a timeout and call `esp_ota_mark_app_invalid_rollback_and_reboot()` when it runs out.
- A power cut before the confirm also rolls back. Keep the self-test short.

Rollback only exists between OTA slots. A serial upload from the Arduino IDE or PlatformIO also rewrites `otadata`, so that image is never pending and there is nothing to roll back to.

## 5. A complete sketch

This compiles against Arduino-ESP32 3.3 for an ESP32-S3. It has not been run against a device for this page. Press `u` on the serial console to start the update.

```cpp
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <mbedtls/sha256.h>

const char* WIFI_SSID = "your-ssid";
const char* WIFI_PASS = "your-password";

// A release asset pinned to one tag, and the SHA256 of that exact file.
const char* FW_URL    = "https://github.com/OWNER/REPO/releases/download/1.2.0/firmware.bin";
const char* FW_SHA256 = "paste-the-64-hex-characters-here";

// Root CAs for every host in the redirect chain, PEM, one after the other.
const char* ROOT_CAS = R"PEM(
-----BEGIN CERTIFICATE-----
...
-----END CERTIFICATE-----
)PEM";

// Arduino-ESP32 confirms a new image before setup() unless this returns true.
extern "C" bool verifyRollbackLater() { return true; }

bool otaUpdate() {
  WiFiClientSecure tls;
  tls.setCACert(ROOT_CAS);
  HTTPClient http;
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  if (!http.begin(tls, FW_URL)) return false;
  if (http.GET() != HTTP_CODE_OK) { http.end(); return false; }

  // -1 without Content-Length, which includes a chunked body. The raw stream
  // would carry the chunk framing into the slot, so refuse it.
  int total = http.getSize();
  if (total <= 0) {
    Serial.println("ota: no Content-Length, refusing the download");
    http.end();
    return false;
  }
  WiFiClient* stream = http.getStreamPtr();  // nullptr once the server has hung up
  if (!stream) { http.end(); return false; }
  if (!Update.begin(total)) { http.end(); return false; }

  mbedtls_sha256_context sha;
  mbedtls_sha256_init(&sha);
  mbedtls_sha256_starts(&sha, 0);  // 0 = SHA-256

  uint8_t buf[1024];
  int got = 0;
  uint32_t lastData = millis();
  while (got < total && millis() - lastData < 10000) {
    int n = stream->available();
    if (n <= 0) {
      if (!http.connected()) break;
      delay(10);
      continue;
    }
    n = stream->readBytes(buf, min(n, (int)sizeof(buf)));
    if (Update.write(buf, n) != (size_t)n) break;
    mbedtls_sha256_update(&sha, buf, n);
    got += n;
    lastData = millis();
  }
  http.end();

  uint8_t digest[32];
  mbedtls_sha256_finish(&sha, digest);
  mbedtls_sha256_free(&sha);
  char hex[65];
  for (int i = 0; i < 32; i++) snprintf(hex + 2 * i, 3, "%02x", digest[i]);

  if (got != total || strcasecmp(hex, FW_SHA256) != 0) {
    Update.abort();  // short stream or wrong hash: the boot slot stays as it was
    return false;
  }
  return Update.end(true);  // makes the new slot the one to boot
}

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) delay(250);
  bool healthy = WiFi.status() == WL_CONNECTED;  // your self-test goes here

  esp_ota_img_states_t state;
  if (esp_ota_get_state_partition(esp_ota_get_running_partition(), &state) == ESP_OK &&
      state == ESP_OTA_IMG_PENDING_VERIFY) {
    if (healthy) esp_ota_mark_app_valid_cancel_rollback();
    else esp_ota_mark_app_invalid_rollback_and_reboot();
  }
}

void loop() {
  if (Serial.read() == 'u' && otaUpdate()) ESP.restart();
}
```

The sketch only accepts a response with a `Content-Length`. `getStreamPtr()` hands over the raw connection, so a chunked body would put the chunk sizes between the firmware bytes and the hash would fail. GitHub release assets come with a length, so this costs nothing there. The stream pointer is checked before `Update.begin()`, so a server that hangs up after the headers ends the update before anything is written. A stream that stops early leaves `got` short of `total`, and `Update.abort()` drops the partial image.

Get the hash on the build machine with `sha256sum firmware.bin` (`shasum -a 256` on macOS).

A hard-coded URL and hash only update once. The usual next step is a small JSON manifest at a fixed URL that names the version, the binary URL and the hash, so the device can ask "is there something newer" on a timer. That is what the next section does.

## 6. How Thesada does it

[Thesada](https://github.com/Thesada/thesada-fw) is an open-source ESP32 firmware built on Arduino-ESP32. Its OTA client is the sketch above grown up. Everything in this section is read from the firmware source.

### The manifest

<!-- claim: repo=thesada-fw file=scripts/generate_manifest.py match="releases/download/\{version\}/firmware.bin" -->
<!-- claim: repo=thesada-fw file=examples/config.json.example match="releases/latest/download/firmware.json" -->
<!-- claim: repo=thesada-fw file=.github/workflows/ci.yml match="artifacts/firmware.bin \\\n\s+artifacts/firmware_minimal.bin \\\n\s+artifacts/firmware.json" -->
The build writes `build/firmware.json` next to the binary, and the release job uploads both as assets. The example config points the device at the `latest/download` URL of the manifest, and the manifest points at the binary of one exact tag, so the hash always belongs to the file it names:

```json
{
  "version": "26.11.1",
  "url": "https://github.com/Thesada/thesada-fw/releases/download/26.11.1/firmware.bin",
  "sha256": "64 hex characters",
  "size": 2682320
}
```

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="return \*version && \*url && \*sha256;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="return rPatch > lPatch;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="#define OTA_MANIFEST_CAP \(8u \* 1024u\)" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="Required for the cellular chunked Range path" -->

| Field | Rule |
|---|---|
| `version` | required. Three numbers, `N.N.N`. A check installs it only when it is newer than the running version |
| `url` | required |
| `sha256` | required |
| `size` | optional on WiFi. The cellular download needs it to fetch the binary in ranges |

A manifest over 8 KB is refused.

### Fetch and verify

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="http.setFollowRedirects\(HTTPC_DISABLE_FOLLOW_REDIRECTS\);" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="static const int OTA_REDIRECT_MAX = 5;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="return strncmp\(to, scheme, n\) == 0 && to\[n\] != '\\0' && to\[n\] != '/';" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="if \(LittleFS.exists\(\"/ca.crt\"\)\)" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="_otaCaCert = String\(FPSTR\(OTA_CA_PROGMEM\)\);" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_ca_progmem.h match="ISRG Root X1[^\n]*\n[^\n]*ISRG Root X2[^\n]*\n[^\n]*DigiCert Global Root CA[^\n]*\n[^\n]*DigiCert Global Root G2[^\n]*\n[^\n]*DigiCert Global Root G3[^\n]*\n[^\n]*USERTrust ECC" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="return allowInsecure \? OTA_TLS_INSECURE : OTA_TLS_REFUSED;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="mbedtls_sha256_update\(&sha_ctx, buf, len\);" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_verify_policy.h match="if \(strlen\(expectedHex\) != OTA_SHA256_HEX_LEN\) return false;\n  return strcasecmp\(computedHex, expectedHex\) == 0;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="reason=sha256_mismatch computed=%s\", computedHex\);\n    Update.abort\(\);" -->

| Step | Thesada |
|---|---|
| Redirects | `HTTPClient` following is off. The client follows up to 5 hops itself, one request each, and only to an absolute URL with the same scheme, so an `https` fetch never drops to `http` |
| Root CAs | `/ca.crt` on the LittleFS partition when present. Otherwise a bundle compiled into the firmware: ISRG Root X1 and X2, DigiCert Global Root CA, G2 and G3, USERTrust ECC |
| No CA at all | OTA stays off unless `ota.allow_insecure` is set in the config |
| Hash | SHA256 over the stream while it is written, the same way as the sketch. The manifest value must be exactly 64 hex characters, either case |
| Mismatch | `Update.abort()`, logged as `reason=sha256_mismatch` with the computed hash. The running image stays |

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="not MITM protection because an attacker who can MITM controls both" -->
The hash is treated as an integrity check and nothing more, for the reason in step 3: without a verified TLS channel the manifest and the binary can be swapped together.

<!-- claim: repo=thesada-fw file=src/main.cpp match="if \(_otaEnabled && networkConnected\(\)\) \{" -->
<!-- claim: repo=thesada-fw file=src/main.cpp match="OTAUpdate::checkNow\(\);  // immediate check while heap is clean" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="cfg\[\"ota\"\]\[\"check_interval_s\"\] \| 21600;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Shell.cpp match="registerCommand\(\"ota.check\"," -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/Shell.cpp match="ota.check --force      - fetch config manifest_url, install regardless" -->
A check runs at boot before MQTT connects when WiFi is already up, then on a timer of `ota.check_interval_s` seconds (default 21600, six hours), and on demand with the `ota.check` shell command. `ota.check --force` installs whatever the manifest names, newer or not.

### Rollback

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="extern \"C\" bool verifyRollbackLater\(\) \{" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_health_policy.h match="if \(mqttUp\) return true;\n  return uptimeMs >= OTA_HEALTH_MIN_MS;" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_health_policy.h match="#define OTA_HEALTH_MIN_MS \(5u \* 60u \* 1000u\)" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="ota.state_change from=pending to=valid reason=healthy" -->
Thesada overrides `verifyRollbackLater()` and confirms a pending image itself: after the first MQTT session of that boot, or after five minutes of uptime, whichever comes first.

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_health_policy.h match="#define OTA_HEALTH_CRASH_LIMIT 3u" -->
<!-- claim: repo=thesada-fw file=src/main.cpp match="logBootCause\(\);\n  OTAUpdate::rollbackIfCrashLoop\(\);" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="esp_ota_mark_app_invalid_rollback_and_reboot\(\) != ESP_OK" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="esp_ota_set_boot_partition\(other\) != ESP_OK" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="otherState != ESP_OTA_IMG_VALID \|\| imageAbandoned\(other\) \|\| !imageVerifies\(other\)" -->
The bootloader only catches an image that resets before the confirm. Thesada adds a crash streak on top, counted in NVS on every boot. Panics, watchdog resets and unplanned software restarts add one. A power-on clears it. At three, the first lines of `setup()` leave the running image, provided the other slot holds a valid image that verifies and is not the one just left:

| Running image | What happens at a streak of three |
|---|---|
| Pending | marked invalid, the bootloader boots the previous slot |
| Confirmed | the other slot becomes the boot slot and the device restarts |

Without such a target the running image stays. So a release that survives its first five minutes and starts crash-looping a day later still gets replaced by the previous one.

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_health_policy.h match="A USB flash leaves its slot UNDEFINED, which the bootloader never rolls" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_health_policy.h match="if \(state != OTA_IMG_UNDEFINED \|\| !streakKnown\) return false;\n  return otaHealthSettleDue\(uptimeMs, lastFailMs\);" -->
<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ota_health_policy.h match="#define OTA_HEALTH_SETTLE_MS \(60u \* 60u \* 1000u\)" -->
An image flashed over USB is not pending, as in step 4. Thesada counts it as confirmed and writes it valid after one hour of uptime.

<!-- claim: repo=thesada-fw file=partitions_owb_16mb.csv match="app0,       app,  ota_0,    0x10000,   0x600000,\napp1,       app,  ota_1,    0x610000,  0x600000," -->
<!-- claim: repo=thesada-fw file=partitions_owb_16mb.csv match="Factory rescue partition intentionally omitted" -->
The 16 MB boards run two 6 MB OTA slots and no factory partition.

The full state machine, the log lines and the config keys are in the [OTA reference]({{ site.baseurl }}/firmware/architecture/connectivity.html#ota-update-otaupdate).

## Sources

| Topic | Source |
|---|---|
| OTA slots, `otadata`, app states, rollback | [ESP-IDF: Over The Air Updates](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/ota.html) |
| `verifyRollbackLater()`, the confirm in `initArduino()` | [arduino-esp32: cores/esp32/esp32-hal-misc.c](https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/esp32-hal-misc.c) |
| Rollback enabled in the prebuilt bootloader | [esp32-arduino-lib-builder: configs/defconfig.common](https://github.com/espressif/esp32-arduino-lib-builder/blob/master/configs/defconfig.common) |
| `Update`, `HTTPClient` redirect modes | [arduino-esp32: libraries](https://github.com/espressif/arduino-esp32/tree/master/libraries) |
| Release asset URLs | [GitHub Docs: Linking to releases](https://docs.github.com/en/repositories/releasing-projects-on-github/linking-to-releases) |
