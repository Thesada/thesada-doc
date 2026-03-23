---
title: Proxmox - HAOS Install
parent: Getting Started
nav_order: 1
description: "Install Home Assistant OS as a VM on Proxmox VE with dedicated networking and USB passthrough."
---

# Home Assistant OS on Proxmox VE 9 - Install & Initial Config

Personal reference. Manual install, no helper scripts.

---

## Prerequisites

- Proxmox VE 9.1.6 node up and reachable
- Shell access to the node (via web console or SSH)
- Storage pool available (e.g. `local-lvm`)
- Internet access from the node

---

## 1. Download the HAOS Image

On the node shell:

```bash
# Get the latest KVM/Proxmox image URL from:
# https://www.home-assistant.io/installation/alternative
# Right-click the KVM/Proxmox download link → Copy link address

wget <URL>
```

Then decompress:

```bash
unxz /root/haos_ova-<version>.qcow2.xz
```

> The file lands in `/root/` if you ran `wget` as root. Confirm with `pwd`.

---

## 2. Create the VM

In the Proxmox web UI, click **Create VM** and configure each tab as follows.

### General

| Setting | Value |
|---|---|
| VM ID | Your choice (e.g. `200`) |
| Name | e.g. `homeassistant` |
| Start at boot | ✅ Enabled |

### OS

| Setting | Value |
|---|---|
| Use CD/DVD disc image | **Do not use any media** |

### System

| Setting | Value |
|---|---|
| Machine | `q35` |
| BIOS | `OVMF (UEFI)` |
| EFI Storage | `local-lvm` (or your pool) |
| Pre-Enroll keys | ❌ Unchecked |

### Disks
- Delete the default SCSI disk. The HA image will be imported separately.

### CPU

| Setting | Value |
|---|---|
| Cores | Minimum **2** |

### Memory

| Setting | Value |
|---|---|
| RAM | Minimum **4096 MB** |

### Network
- Leave defaults (`vmbr0`, VirtIO) unless you need a specific setup.

**Finish the wizard. Do not start the VM yet.**

---

## 3. Import the Disk Image

Back on the **node shell** (not the VM shell):

```bash
qm importdisk <VMID> /root/haos_ova-<version>.qcow2 local-lvm
```

Example:

```bash
qm importdisk 600 /root/haos_ova-14.0.qcow2 local-lvm
```

---

## 4. Attach the Disk

In the Proxmox web UI, select the HA VM:

1. Go to **Hardware** tab
2. Select **Unused Disk 0** → click **Edit**
3. If using SSD: check **Discard**
4. Click **Add**

Then set the boot order:

1. Go to **Options** tab → **Boot Order** → **Edit**
2. Check `scsi0` (the imported disk)
3. Uncheck everything else
4. Click **OK**

---

## 5. Boot and Verify

Start the VM. Open its **Console** tab in Proxmox.

If it booted correctly you'll see the HAOS shell prompt with the local IP printed, e.g.:

```
Home Assistant login:
```

Note the IP address shown - you'll need it for web access and CLI config.

---

## 6. Initial Network Config via HA CLI

Access the HA CLI from the VM console (no login needed on HAOS):

![HA Onboarding]({{ site.baseurl }}/assets/img/getting-started/ha_ready.png)

```bash
ha network info
```

This shows current interfaces and their state.

### Set a Static IP

```bash
ha network update <INTERFACE> \
  --ipv4-method static \
  --ipv4-address <IP>/<PREFIX> \
  --ipv4-gateway <GATEWAY>
```

Example:

```bash
ha network update enp6s18 \
  --ipv4-method static \
  --ipv4-address 10.254.0.60/24 \
  --ipv4-gateway 10.254.0.1
```

### Set DNS Servers

```bash
ha network update <INTERFACE> \
  --dns 10.0.0.1
```

### Verify

```bash
ha network info
```

Confirm the address, gateway, and DNS are showing correctly before moving on.

---

## 7. First-Run Web Setup

Navigate to:

```
http://<IP>:8123
```
![HA Onboarding]({{ site.baseurl }}/assets/img/getting-started/ha_onboarding.png)

The onboarding wizard will walk through:

- Creating the owner account
- Setting location, timezone, and units
- Discovering devices on the network

---

## Troubleshooting Notes

| Symptom | Fix |
|---|---|
| No boot, BIOS access denied | Disable Secure Boot in the VM's OVMF BIOS |
| `non-existent or non-regular file` on `qm importdisk` | Check spelling - extension is `.qcow2` not `.gcow2` |
| Port 8123 not reachable after first boot | Delete VM and redo from step 2; known to resolve config.yaml issues |
| QEMU agent connected but CPU/RAM missing in PVE | Known HAOS limitation; network stats still work |