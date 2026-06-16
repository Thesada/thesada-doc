---
title: Build and Field Notes
parent: Firmware
nav_order: 8
description: "Build targets, the release and versioning workflow, and hardware-integration notes - including the SIM7080G cellular mTLS AT sequence."
---

# Build and Field Notes

Build-time and hardware-integration knowledge for `thesada-fw` that does not belong to a single runtime subsystem. Runtime behaviour lives in the other firmware pages; this one holds build targets, the release workflow, and modem-integration notes.

## Build targets

`main` builds ESP32-S3 targets only. The PlatformIO environments and the boards they map to are listed in the [hardware table]({{ site.baseurl }}/firmware/#hardware). Each environment selects its module set at compile time.

Classic ESP32 variants (WROOM, CYD, Ethernet) are maintained on a separate track and are not produced from `main`. Do not expect `main` to build a non-S3 image.

## Release and versioning

Bump `FIRMWARE_VERSION` in `src/thesada_config.h` **before** the merge commit that ships the release, then tag that commit.

The source of truth for the running version is `thesada_config.h` plus the git tags - never a version line written into prose docs. Bumping before the merge avoids having to force-move a tag that was placed ahead of the version constant.

## Cellular mTLS (SIM7080G)

mTLS over the SIM7080G is sensitive to the exact AT-command order. SIM7080G modem firmware `1951B17` silently fails the TLS handshake with the "obvious" concatenated-PEM approach.

Upload the CA, client certificate, and client key to the modem filesystem as **three separate files** (`server-ca.crt`, `client.crt`, `client.key`), then:

```text
+CSSLCFG="SSLVERSION",0,3                        # TLS 1.2 on SSL context 0
+CSSLCFG="CONVERT",2,"server-ca.crt"             # convert CA (type 2)
+CSSLCFG="CONVERT",1,"client.crt","client.key"   # convert client cert + key (type 1, 4-arg)
+CSSLCFG="sni",0,"<broker>"                       # optional; ignored harmlessly on a direct broker
+SMSSL=1,"server-ca.crt","client.crt"            # mode 1 = mutual TLS
```

Field notes:

- **Do not** concatenate cert and key into one PEM and use `+SMSSL=2`. It returns `OK` but the handshake never completes on fw `1951B17`. The 4-arg `CONVERT,1` flow above is the working pattern.
- The client key must be **PKCS#8**, not SEC1. Validated with both RSA-2048 and ECDSA P-256 client certs.
- Yield the AT bus between cellular MQTT retries. If the modem loops on `SMCONN` failure without releasing the bus, the main loop starves.
- Reference AT samples: LilyGo's published T-SIM7080G SSL and MQTT example sketches at `github.com/Xinyuan-LilyGO/LilyGo-T-SIM7080G`.
