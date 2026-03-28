---
title: Spotify + Home Assistant
parent: Troubleshooting
grand_parent: Misc
nav_order: 7
description: "Setting up the Spotify integration in Home Assistant with a custom domain and OAuth redirect."
---

# Spotify + Home Assistant

## Prerequisites

- Spotify Premium account
- Home Assistant with MQTT broker (Mosquitto)
- HA accessible via custom domain (e.g. `ha.example.com`) with HTTPS

## Setup

### 1. Create a Spotify Developer App

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create an app (name: "Home Assistant", description: anything)
3. Note the **Client ID** and **Client Secret**
4. Under **Settings > Redirect URIs**, add:
   ```
   https://my.home-assistant.io/redirect/oauth
   ```
5. Save

### 2. Register your HA instance with my.home-assistant.io

1. Open [https://my.home-assistant.io](https://my.home-assistant.io) in your browser
2. It will ask for your Home Assistant URL
3. Enter your public URL (e.g. `https://ha.example.com`)
4. Save

This is required because HA uses `my.home-assistant.io` as the OAuth relay. Spotify sends the auth token there, and the relay redirects it back to your HA instance.

**If the URL was set wrong previously:** Browse to `my.home-assistant.io` directly and update the URL. This is stored in your browser's local storage.

### 3. Configure HA external URL

In HA, verify these are set (Settings > System > Network, or `configuration.yaml`):

```yaml
homeassistant:
  external_url: "https://ha.example.com"
  internal_url: "http://192.168.66.20:8123"
```

### 4. Add the Spotify Integration

1. Settings > Devices & Services > Add Integration > Spotify
2. HA redirects to Spotify login via `my.home-assistant.io`
3. Authorize the app
4. Spotify redirects back to `my.home-assistant.io` which redirects to your HA
5. Integration appears with a `media_player.spotify_<name>` entity

## Troubleshooting

### "redirect_uri: Not matching configuration"

The redirect URI in your Spotify Developer app doesn't match. Add exactly:
```
https://my.home-assistant.io/redirect/oauth
```

### Auth redirects but nothing comes back

1. **Wrong URL in my.home-assistant.io** - Browse to `https://my.home-assistant.io` and verify/update your HA URL. If it was set to an old or wrong URL previously, clear it and re-enter.

2. **HA not reachable from internet** - `my.home-assistant.io` needs to redirect to your HA's `external_url`. Verify `ha.example.com` (or your domain) is publicly accessible on port 443.

3. **HAProxy not forwarding** - If HA is behind HAProxy, verify the HTTPS frontend forwards to the HA backend. Check HAProxy logs:
   ```bash
   journalctl -u haproxy --since "1 min ago"
   ```

4. **Missing trusted_proxies** - HA needs to trust the HAProxy IP:
   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 192.168.66.0/24
   ```

### Spotify Connect add-on vs Spotify integration

These are different things:
- **Spotify Connect add-on** (v0.17.0) - turns HA into a Spotify playback device. Not needed for display control.
- **Spotify integration** - creates a `media_player` entity for controlling playback, reading track info. This is what you need.

## MQTT Bridge for CYD Display

After the integration is working, add these automations to publish Spotify state to MQTT and accept commands back:

### Publish state changes

```yaml
automation:
  - alias: "Spotify to MQTT"
    trigger:
      - platform: state
        entity_id: media_player.spotify_<your_name>
    action:
      - service: mqtt.publish
        data:
          topic: "thesada/spotify/state"
          payload_template: >
            {
              "state": "{{ states('media_player.spotify_<your_name>') }}",
              "title": "{{ state_attr('media_player.spotify_<your_name>', 'media_title') }}",
              "artist": "{{ state_attr('media_player.spotify_<your_name>', 'media_artist') }}",
              "album": "{{ state_attr('media_player.spotify_<your_name>', 'media_album_name') }}",
              "image": "{{ state_attr('media_player.spotify_<your_name>', 'entity_picture') }}",
              "duration": {{ state_attr('media_player.spotify_<your_name>', 'media_duration') or 0 }},
              "position": {{ state_attr('media_player.spotify_<your_name>', 'media_position') or 0 }}
            }
          retain: true
```

### Accept playback commands

```yaml
automation:
  - alias: "MQTT Spotify Control"
    trigger:
      - platform: mqtt
        topic: "thesada/spotify/command"
    action:
      - choose:
          - conditions: "{{ trigger.payload == 'play' }}"
            sequence:
              - service: media_player.media_play
                target:
                  entity_id: media_player.spotify_<your_name>
          - conditions: "{{ trigger.payload == 'pause' }}"
            sequence:
              - service: media_player.media_pause
                target:
                  entity_id: media_player.spotify_<your_name>
          - conditions: "{{ trigger.payload == 'next' }}"
            sequence:
              - service: media_player.media_next_track
                target:
                  entity_id: media_player.spotify_<your_name>
          - conditions: "{{ trigger.payload == 'prev' }}"
            sequence:
              - service: media_player.media_previous_track
                target:
                  entity_id: media_player.spotify_<your_name>
```

Replace `<your_name>` with your Spotify username in the entity ID.

The CYD subscribes to `thesada/spotify/state` and publishes to `thesada/spotify/command`.
