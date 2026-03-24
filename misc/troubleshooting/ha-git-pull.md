---
title: HA Git Pull Add-on with Deploy Keys
parent: Troubleshooting
nav_order: 6
description: "Fix Home Assistant Git pull add-on authentication with SSH deploy keys."
---

# Home Assistant Git Pull Add-on Authentication

## Problem

The Git pull add-on fails to pull from a private GitHub repo. Log shows
authentication errors or "Permission denied (publickey)."

## Background

The Git pull add-on syncs a GitHub repo to HA's `/config` directory on
a schedule. For private repos, it needs SSH authentication via a deploy
key. The add-on cannot use passphrase-protected keys.

## Setup

### 1. Generate a dedicated key on the HA terminal

Settings > Apps > SSH & Terminal > Open Web UI:

```bash
ssh-keygen -t ed25519 -C "ha-git-sync" -f ~/.ssh/id_ha_git_sync
```

Leave the passphrase empty. The Git pull add-on cannot handle passphrases.

### 2. Add the public key as a deploy key on GitHub

```bash
cat ~/.ssh/id_ha_git_sync.pub
```

Copy the output. In GitHub:

1. Go to the repo Settings > Deploy keys
2. Click "Add deploy key"
3. Title: something descriptive (e.g. "ha-git-sync")
4. Paste the public key
5. Do **not** check "Allow write access" (read-only is sufficient for one-way sync)
6. Click "Add key"

### 3. Configure git to use the deploy key

```bash
cat > ~/.gitconfig << 'EOF'
[user]
    name = your-name
    email = your-email@example.com

[core]
    sshCommand = ssh -i ~/.ssh/id_ha_git_sync
EOF
```

### 4. Set the remote URL

```bash
cd /config
git remote set-url origin git@github.com:YourOrg/your-repo.git
```

### 5. Test

```bash
git fetch
```

No errors means authentication is working.

### 6. Configure the Git pull add-on

In the add-on Configuration tab, the deployment key must be formatted
as a YAML list with each line as a separate quoted item:

```yaml
repository: git@github.com:YourOrg/your-repo.git
git_branch: main
git_remote: origin
auto_restart: true
restart_ignore:
  - ui-lovelace.yaml
  - .gitignore
git_command: pull
git_prune: true
deployment_key:
  - "-----BEGIN OPENSSH PRIVATE KEY-----"
  - "line1-of-key-content"
  - "line2-of-key-content"
  - "line3-of-key-content"
  - "-----END OPENSSH PRIVATE KEY-----"
deployment_user: ""
deployment_password: ""
deployment_key_protocol: ed25519
repeat:
  active: true
  interval: 3600
```

Get the private key contents:

```bash
cat ~/.ssh/id_ha_git_sync
```

Each line of the output (including the BEGIN/END headers) becomes a
separate quoted list item in the YAML.

### 7. Verify

Check the add-on Log tab. Successful output:

```
Fetching changes for branch main
Already up to date.
```

## Common Mistakes

**Key with passphrase:** The add-on cannot prompt for a passphrase. Generate
the key with an empty passphrase.

**Write access enabled:** Not needed for one-way sync (GitHub to HA). Read-only
deploy keys are more secure.

**deployment_key as a string instead of a list:** The add-on expects each line
of the private key as a separate YAML list item. A single multi-line string
will fail silently.

**Wrong interval units:** The `interval` field is in seconds, not minutes.
3600 = 1 hour.

## Workflow

1. Edit HA config files on your workstation or in GitHub
2. Commit and push to main
3. Git pull add-on syncs within the configured interval (default: 1 hour)
4. To pull immediately: Settings > Apps > Git pull > Restart

## What to .gitignore

These should never be committed:

```
secrets.yaml
.storage/auth
.storage/auth_provider.homeassistant
.storage/onboarding
home-assistant_v2.db
home-assistant_v2.db-shm
home-assistant_v2.db-wal
home-assistant.log
home-assistant.log.1
home-assistant.log.fault
.cache/
.ha_run.lock
.cloud/
.HA_VERSION
deps/
tts/
```

Manage `secrets.yaml` directly on the HA instance. It never leaves the box.
