---
title: Home Assistant DNS & SSL
parent: Getting Started
nav_order: 2
---

# Home Assistant DNS & SSL

This guide covers setting up Cloudflare DDNS, obtaining a Let's Encrypt TLS certificate, and enabling HTTPS on Home Assistant. The same certificate is reused by Mosquitto and ESPHome - no additional certificate work is needed for those services.

---

## Prerequisites

- Home Assistant running and accessible (see [Proxmox - HAOS Install](proxmox-haos.md))
- A Cloudflare account managing your domain

---

## 1. Create a Cloudflare API Token

1. Cloudflare dashboard → **My Profile → API Tokens**
2. Click **Create Token**
3. Use the **Edit zone DNS** template
4. The template includes `Zone:DNS:Edit` - manually add `Zone:DNS:Read` as an additional permission
5. Scope both permissions to your specific zone (domain)
6. Copy the token - you will need it below

---

## 2. Cloudflare DDNS

Since your home IP is likely dynamic, you need a DNS record that updates automatically when it changes.

### Create the DNS record

1. Log in to Cloudflare
2. Select your domain
3. **DNS → Records → Add record**
   - Type: `A`
   - Name: `mqtt` (resolves to `mqtt.yourdomain.com`)
   - IPv4: your current public IP (find it at [ifconfig.me](https://ifconfig.me))
   - Proxy: **OFF** (grey cloud - DNS only) - MQTT is TCP, Cloudflare proxy does not support it

### Install Cloudflare DDNS integration

1. In Home Assistant go to **Settings → Devices & services → Add integration**
2. Search **Cloudflare**
3. Select **Cloudflare** (**not Cloudflare R2**)
4. Enter your API token and click **Submit**
5. Select the Zone, then the Domain to update and click **Submit**

The integration checks your public IP periodically and updates the Cloudflare A record automatically when it changes.

---

## 3. Obtain a Let's Encrypt Certificate

The certificate is obtained via the Cloudflare DNS challenge - no port 80 or port forwarding required.

1. In Home Assistant go to **Settings → Apps**
2. Open the **Let's Encrypt** app (install from the App Store if not present)
3. Go to the **Configuration** tab and set:

```yaml
domains:
  - yourdomain.com
  - mqtt.yourdomain.com
certfile: fullchain.pem
keyfile: privkey.pem
challenge: dns
email: you@yourdomain.com
dns:
  provider: dns-cloudflare
  cloudflare_api_token: YOUR_CLOUDFLARE_API_TOKEN
```

4. Click **Save**, then **Start**

The app will obtain a certificate and store it at:
- `/ssl/fullchain.pem`
- `/ssl/privkey.pem`

---

## 4. Auto-Renewal

Let's Encrypt certificates expire every 90 days. The app does **not** auto-renew - set up an automation to restart it every 60 days.

**Settings → Automations → Create Automation → Edit in YAML:**

```yaml
alias: Let's Encrypt Auto-Renew
description: Restart Let's Encrypt app every 60 days to renew certificate
trigger:
  - platform: time
    at: "03:00:00"
condition:
  - condition: template
    value_template: >
      {{ states.automation.lets_encrypt_auto_renew.attributes.last_triggered is none
         or (now() - states.automation.lets_encrypt_auto_renew.attributes.last_triggered).days >= 60 }}
action:
  - action: hassio.addon_restart
    data:
      addon: core_letsencrypt
mode: single
```

---

## 5. Enable HTTPS on Home Assistant

Home Assistant can serve HTTPS directly without a reverse proxy. Once enabled, plain HTTP on port 8123 is disabled.

Open `configuration.yaml` in Studio Code Server or SSH terminal and add:

```yaml
http:
  ssl_certificate: /ssl/fullchain.pem
  ssl_key: /ssl/privkey.pem
```

**Settings → System → Restart**

---

## 6. Verify

Home Assistant should now be accessible at:

```
https://YOUR_DOMAIN:8123
```

**Use your domain name, not the IP address.** The Let's Encrypt certificate is issued to your domain - accessing HA by IP will show a certificate warning in the browser.

### Internal DNS override

Keep Home Assistant off the public internet - do not expose port 8123 externally. To reach HA by domain name inside your network, set up a local DNS override on your router or internal DNS server:

- Point `yourdomain.com` → `YOUR_HA_IP`

How to do this depends on your router or DNS server. Common options include a static DNS entry in your router's admin interface, or a local override in Pi-hole / AdGuard if you run one.

Once the override is in place, `https://yourdomain.com:8123` will load with a valid padlock on any device inside your network.

**Note:** Plain HTTP (`http://YOUR_HA_IP:8123`) will no longer work. Update any bookmarks, mobile app connections, or integrations accordingly.

---

## 7. Verify ESPHome App

1. **Settings → Apps → ESPHome Device Builder → Open Web UI**
2. Confirm the browser shows `https://` with a valid padlock

The ESPHome app uses the same certificate - no additional configuration needed there beyond what is covered in the [ESPHome Setup](esphome.md) guide.