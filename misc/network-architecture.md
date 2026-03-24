---
title: Network Architecture
parent: Misc
nav_order: 1
description: "Network design with VLAN segmentation -- IoT, DMZ, guest isolation on OpenWrt with firewall rules and traffic flows."
---

# Network Architecture and IPAM

Network design for a self-hosted Home Assistant deployment with isolated IoT,
DMZ, and guest segments. Built on OpenWrt or OPNsense with VLAN segmentation.

All IPs shown are examples. Adapt subnets and VLAN IDs to your environment.

---

## Addressing Scheme

Three RFC 1918 ranges, each with a clear purpose:

| Range | Purpose | Trust level |
|---|---|---|
| 10.0.0.0/8 | Private / trusted (management, workstations) | Full access |
| 172.16.0.0/12 | IoT / Home Automation (sensors, ESP32 nodes) | Restricted - no internet, local only |
| 192.168.0.0/16 | Public-facing / untrusted (DMZ, guest) | Isolated |

This scheme is expandable. Need another private subnet? Use 10.0.1.0/24.
Another IoT segment? 172.16.1.0/24. Another public zone? 192.168.3.0/24.

---

## Subnets

### Main LAN - 10.0.0.0/24

Management network. Workstations, servers, trusted devices.

| Attribute | Value |
|---|---|
| Subnet | 10.0.0.0/24 |
| Gateway | 10.0.0.1 (router) |
| VLAN | Untagged (native on br-lan). VLAN ID 10 if tagging is needed. |
| DHCP range | 10.0.0.100 - 10.0.0.199 |
| Internet | Yes |
| Firewall zone | lan |

**Static assignments:**

| IP | Device | Notes |
|---|---|---|
| 10.0.0.1 | Router | Gateway |
| 10.0.0.10 | Proxmox host | Hypervisor |

**IP allocation plan:**

| Range | Purpose |
|---|---|
| .1 | Gateway |
| .2 - .9 | Reserved (network infrastructure) |
| .10 - .49 | Static infrastructure (servers, VMs, NAS) |
| .50 - .99 | Reserved (future static assignments) |
| .100 - .199 | DHCP (workstations, laptops, phones) |
| .200 - .254 | Reserved |

### IoT VLAN - 172.16.0.0/24

All ESP32 sensor nodes. No internet access. Isolated from main LAN.
Nodes use mDNS hostnames (.local) for discovery. IPs are mostly static
reservations or DHCP with reservations.

| Attribute | Value |
|---|---|
| Subnet | 172.16.0.0/24 |
| Gateway | 172.16.0.1 (router) |
| VLAN ID | 20 |
| Interface | br-lan.20 |
| SSID | Dedicated 2.4 GHz (phy0-ap0) |
| DHCP range | 172.16.0.200 - 172.16.0.249 |
| Internet | No |
| Firewall zone | IOT |

**IP allocation plan:**

| Range | Purpose |
|---|---|
| .1 | Gateway |
| .2 - .99 | Reserved |
| .100 - .199 | Static / DHCP reservations (sensor nodes) |
| .200 - .249 | DHCP (new/unassigned devices) |
| .250 - .254 | Reserved |

**Firewall rules:**

| Rule | Purpose |
|---|---|
| IOT -> reject (default) | No outbound traffic from IoT |
| IOT -> DMZ: allow dst 192.168.2.20 port 1883 (TCP) | MQTT to Mosquitto |
| IOT -> DMZ: allow dst 192.168.2.20 port 8883 (TCP) | MQTT over TLS |
| Allow UDP 5353 to 224.0.0.251, no dest zone | mDNS - applies to input chain for mdns-repeater |
| Allow UDP 123 to gateway, no dest zone | NTP - IoT nodes sync time from the router (input chain) |

Note: IoT nodes reach MQTT in the DMZ, not the LAN. This is because
Home Assistant (and Mosquitto as its add-on) runs in the DMZ subnet.

**Why no internet for IoT?** Sensor nodes have no legitimate reason to
reach the internet. All data flows to the local MQTT broker. Blocking
internet access limits the blast radius if a node is compromised and
prevents firmware from phoning home to third-party servers. OTA updates
for custom firmware nodes are pulled from GitHub via the MQTT broker
or a local proxy -- not directly from the node.

**Connected devices (example):**

| Hostname | Device | Sensors |
|---|---|---|
| thesada-owb.local | LILYGO T-SIM7080-S3 | DS18B20 x4, ADS1115 |
| thesada-sht31.local | Freenove ESP32-S3 | SHT31 temp/humidity |

### DMZ VLAN - 192.168.2.0/24

Public-facing services on Proxmox VMs/containers. Static IPs only.
Home Assistant lives here because it has external access via port forwarding.

| Attribute | Value |
|---|---|
| Subnet | 192.168.2.0/24 |
| Gateway | 192.168.2.1 (router) |
| VLAN ID | 666 |
| Interface | br-lan.666 |
| DHCP | None - static only |
| Internet | Yes (outbound) |
| Firewall zone | DMZ |

**Static assignments:**

| IP | Device | Notes |
|---|---|---|
| 192.168.2.1 | Router | Gateway for DMZ |
| 192.168.2.20 | Home Assistant OS VM | Static in VM. Proxmox vmbr on VLAN 666. |

**Port forwards (WAN -> DMZ):**

| External port | Internal destination | Protocol | Purpose |
|---|---|---|---|
| 443 | 192.168.2.20:443 | TCP | HA external HTTPS access |
| 8883 | 192.168.2.20:8883 | TCP | MQTT over TLS (remote sensor nodes, cellular fallback) |

**Firewall rules:**

| Rule | Purpose |
|---|---|
| DMZ -> reject (default) | No access to lan, IOT, or guest |
| DMZ -> lan: allow dst 10.0.0.10 port 3493 (TCP) | HA NUT integration to Proxmox upsd |
| DMZ -> wan: allow | Internet access (Telegram outbound, NTP, updates) |
| wan -> DMZ: allow dst 192.168.2.20 port 443 (TCP) | HA external access (port forward) |
| wan -> DMZ: allow dst 192.168.2.20 port 8883 (TCP) | MQTT TLS external (port forward) |

**Future consideration:** A second NIC on the HA VM attached to the IoT
VLAN (172.16.0.0/24) would allow IoT nodes to reach MQTT directly without
crossing the firewall. This simplifies firewall rules and reduces the
dependency on cross-zone routing for sensor traffic. Not implemented yet.

### Guest VLAN - 192.168.128.0/24

Guest WiFi. Internet access only. No access to any other subnet.

| Attribute | Value |
|---|---|
| Subnet | 192.168.128.0/24 |
| Gateway | 192.168.128.1 (router) |
| VLAN ID | 40 |
| Interface | br-lan.40 |
| DHCP range | 192.168.128.100 - 192.168.128.199 |
| Internet | Yes |
| Firewall zone | guest |

**Firewall rules:**

| Rule | Purpose |
|---|---|
| guest -> reject (default) | No access to lan, IOT, or DMZ |
| guest -> wan: allow | Internet access only |

---

## VLAN Summary

| VLAN ID | Name | Subnet | Interface | Firewall Zone |
|---|---|---|---|---|
| untagged (10) | Main LAN | 10.0.0.0/24 | br-lan | lan |
| 20 | IoT | 172.16.0.0/24 | br-lan.20 | IOT |
| 40 | Guest | 192.168.128.0/24 | br-lan.40 | guest |
| 666 | DMZ | 192.168.2.0/24 | br-lan.666 | DMZ |

---

## Expansion Guide

To add a new subnet:

1. Pick the right range based on trust level:
   - Trusted/private: 10.0.x.0/24 (e.g. 10.0.1.0/24 for a second management network)
   - IoT/sensors: 172.16.x.0/24 (e.g. 172.16.1.0/24 for a second IoT segment)
   - Public/untrusted: 192.168.x.0/24 (e.g. 192.168.3.0/24 for a second DMZ)

2. Assign a VLAN ID. Keep a gap between IDs for future use.

3. Create the VLAN interface in OpenWrt (Network > Interfaces > Add new interface).

4. Create a firewall zone for it (Network > Firewall > Add zone).

5. Set default forwarding rules:
   - Trusted: allow to all zones
   - IoT: reject by default, allow specific ports to specific hosts
   - Public/untrusted: reject by default, allow to wan only

**VLAN ID allocation:**

| Range | Purpose | Current assignments |
|---|---|---|
| 1-16 | Management / main LAN | 10 = Main LAN (untagged) |
| 17-32 | IoT / sensors | 20 = IoT |
| 33-48 | Guest / untrusted | 40 = Guest |
| 49-665 | Future expansion | - |
| 666 | DMZ | 666 = DMZ |
| 667+ | Future use | - |

---

## Service Map

Where each service runs and what subnet it listens on.

| Service | Runs on | Subnet | Port | Notes |
|---|---|---|---|---|
| Router (DHCP, DNS, NAT) | Router (all gateways) | All | - | Edge router + firewall |
| Proxmox VE | 10.0.0.10 | Main LAN | 8006 (web UI) | Bare-metal hypervisor |
| Home Assistant OS | 192.168.2.20 (VM) | DMZ | 8123, 443 (HTTPS) | Single NIC on DMZ |
| Mosquitto MQTT | 192.168.2.20 (HA add-on) | DMZ | 1883, 8883 (TLS) | IoT nodes cross firewall to reach it |
| ESPHome | 192.168.2.20 (HA add-on) | DMZ | 6052 | Dashboard + OTA push for ESPHome nodes |
| NUT (upsd) | 10.0.0.10 (Proxmox) | Main LAN | 3493 | UPS monitoring. Bound to 0.0.0.0. |
| Telegram (outbound) | HA automations | - | 443 (HTTPS) | Webhook mode. Outbound from DMZ. |
| mdns-repeater | Router | LAN + IoT + DMZ | 5353 (UDP) | Bridges mDNS across all local VLANs |

---

## Traffic Flows

### Sensor to Alert (local WiFi - custom firmware)

```
ESP32 node (172.16.0.x, IoT VLAN)
    |
    | MQTT publish to thesada/node/alert (port 8883 TLS)
    | Allowed by: IOT -> DMZ firewall rule
    v
Mosquitto (HA add-on, 192.168.2.20:8883, DMZ)
    |
    | Two parallel paths:
    |
    |-- 1. Firmware sends directly to Telegram Bot API
    |      (if bot_token + chat_ids configured)
    |      IoT has no internet -> only works via cellular fallback
    |
    |-- 2. HA automation subscribes to MQTT alert topic
    |      HA -> Telegram API (outbound HTTPS from DMZ)
    |
    v
Phone notification
```

### Sensor to Alert (local WiFi - ESPHome nodes)

```
ESPHome node (172.16.0.x, IoT VLAN)
    |
    | MQTT publish (port 1883/8883)
    | Allowed by: IOT -> DMZ firewall rule
    v
Mosquitto (192.168.2.20, DMZ)
    |
    | MQTT discovery
    v
Home Assistant (192.168.2.20, DMZ)
    |
    | Automation trigger
    v
Telegram API (outbound HTTPS from DMZ)
    |
    v
Phone notification
```

### Sensor to Alert (cellular fallback)

```
ESP32 node (remote, via Cat-M1 cellular)
    |
    | MQTT publish over TLS (port 8883)
    | Hits WAN IP, port forwarded to DMZ
    v
Router WAN -> NAT -> 192.168.2.20:8883
    |
    v
Mosquitto (192.168.2.20:8883, DMZ)
    |
    | Same path as local from here
    v
Home Assistant -> Telegram -> Phone
```

### OTA - Custom firmware (pull from GitHub)

```
Firmware checks GitHub for new version (periodic or MQTT trigger)
    |
    | HTTPS to github.com (manifest) + release-assets (binary)
    | IoT VLAN has no internet -> OTA only works if:
    |   a) Node has cellular fallback, OR
    |   b) IoT firewall temporarily allows outbound HTTPS, OR
    |   c) Push OTA via web UI from the LAN (see below)
    v
Node downloads firmware.bin, verifies SHA256, flashes
    |
    v
Node reboots on new firmware
```

### OTA - Custom firmware (push via web UI)

```
Laptop/phone (10.0.0.x or 172.16.0.x)
    |
    | POST /ota with firmware.bin
    | From LAN: lan -> IOT (allowed by default)
    | From IoT: same subnet, no firewall needed
    v
Node (172.16.0.x) flashes firmware, reboots
    |
    | Page auto-refreshes after 10s
    v
Dashboard shows new version
```

### OTA - ESPHome (from HA dashboard)

```
ESPHome add-on (192.168.2.20, DMZ)
    |
    | mDNS query: thesada-sht31.local
    | Bridged by: mdns-repeater (DMZ <-> IoT)
    |
    | ESPHome OTA push (port 3232)
    | Requires: DMZ -> IOT firewall rule allowing port 3232
    v
ESPHome node (172.16.0.x, IoT VLAN)
    |
    v
Firmware updated
```

Note: OTA from the HA dashboard requires a DMZ -> IOT firewall rule
allowing port 3232. If this rule does not exist, OTA only works from
the laptop on the main LAN via `esphome upload`.

### HA to Proxmox NUT

```
Home Assistant (192.168.2.20, DMZ)
    |
    | NUT query (port 3493)
    | Allowed by: DMZ -> lan rule (dst 10.0.0.10:3493)
    v
upsd on Proxmox (10.0.0.10:3493, Main LAN)
    |
    v
UPS status returned to HA
```

---

## Cross-Zone Firewall Summary

All traffic between zones passes through the router. Default policy
for all zones is reject. Only explicitly allowed traffic passes.

| Source | Destination | Ports | Purpose |
|---|---|---|---|
| IOT | DMZ | 1883, 8883 TCP (dst .2.20) | MQTT to Mosquitto |
| IOT | (input) | 5353 UDP to 224.0.0.251 | mDNS for mdns-repeater |
| IOT | (input) | 123 UDP | NTP to router gateway |
| DMZ | lan | 3493 TCP (dst .0.10) | HA NUT to Proxmox upsd |
| DMZ | wan | any | Internet (Telegram, updates) |
| DMZ | IOT | 3232 TCP (optional) | ESPHome OTA from HA dashboard |
| lan | all | any | Trusted - full access |
| guest | wan | any | Internet only |
| wan | DMZ | 443, 8883 TCP (dst .2.20) | Port forwards to HA |

---

## Design Notes

### mDNS across VLANs

mDNS (multicast DNS, .local hostnames) does not cross subnet boundaries
by default. Running `mdns-repeater` on the router bridges mDNS queries
between VLANs. This allows OTA updates by hostname from the LAN to IoT
nodes without giving IoT nodes internet access.

The firewall rule for mDNS must target the **input chain** (no destination
zone), not a forward rule. This is because mdns-repeater listens on the
router itself.

### NTP for IoT nodes

IoT nodes have no internet access and cannot reach public NTP servers.
Configure nodes to use the router gateway (172.16.0.1) as their NTP
server. The router syncs its own clock from the internet and serves
time locally. Requires a firewall rule allowing UDP 123 on the input
chain for the IoT zone.

### Why DMZ for Home Assistant?

Home Assistant needs external access (HTTPS for mobile app, MQTT TLS
for cellular nodes). Placing it in the DMZ keeps it isolated from the
trusted LAN. If HA is compromised via an exposed port, the attacker
has no direct path to the management network or Proxmox host.

The tradeoff: IoT -> DMZ firewall rules are needed for MQTT. A dual-NIC
setup (one NIC on DMZ for external access, one on IoT for sensor traffic)
would eliminate this cross-zone dependency but adds complexity.

### Certificate management

TLS certificates for external access (HA HTTPS, MQTT TLS) are managed
by Let's Encrypt via the HA add-on using Cloudflare DNS-01 challenge.
The same certificate covers both `ha.yourdomain.com` and
`mqtt.yourdomain.com` (CNAME to the same host).

The LE add-on does not auto-renew. Set up an HA automation to restart
the add-on every 60 days to trigger renewal.

### Backup and resilience

- **UPS**: Proxmox host on a UPS. HA monitors via NUT. Automation can
  trigger a graceful VM shutdown on extended power loss.
- **Config backup**: HA config is version-controlled in Git. Git pull
  add-on syncs from GitHub on push.
- **Firmware backup**: Node config backed up to SD card via `/api/backup`.
  Firmware binaries stored as GitHub releases.
- **Network**: If the router fails, all local automation stops. Consider
  a cold-spare router with the same OpenWrt config backed up.
