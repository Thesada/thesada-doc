---
title: HA Git Sync (Optional)
parent: Getting Started
nav_order: 6
description: "Version-control Home Assistant config with Git -- private repo, deploy key, one-way sync from GitHub."
---

# Home Assistant Config — Git Setup
## Private repo, one-way sync (GitHub → HA)

This guide covers exporting your Home Assistant config to a private GitHub repository and keeping it in sync using the Git pull add-on.

---

## 1. Create a Private Repo on GitHub

1. Go to your GitHub account or organisation and create a new repository
2. Visibility: **Private**
3. Do not initialise with README
4. Click **Create repository**

---

## 2. First Export from Home Assistant

On the HA terminal (**Settings → Apps → SSH & Terminal → Open Web UI**):

```bash
cd /config

git init
git config user.name "your-username"
git config user.email "your@email.com"
git remote add origin git@github.com:YOUR_ORG/YOUR_REPO.git
```

### Create .gitignore

Some files should never be committed — secrets, tokens, the database, and runtime files:

```bash
cat > .gitignore << 'EOF'
# Secrets and credentials
secrets.yaml
.storage/auth
.storage/auth_provider.homeassistant
.storage/onboarding

# Database and logs
home-assistant_v2.db
home-assistant_v2.db-shm
home-assistant_v2.db-wal
home-assistant.log
home-assistant.log.1
home-assistant.log.fault

# Runtime and cache
.cache/
.ha_run.lock

# Generic
.cloud/
.HA_VERSION
deps/
tts/
EOF
```

Review this list against your actual `/config` directory and add any additional files you don't want tracked before the first commit.

### Initial commit and push

```bash
git add .
git commit -m "ha: initial config export"
git branch -M main
git push -u origin main
```

---

## 3. SSH Key for GitHub Access

### Generate a key

```bash
ssh-keygen -t ed25519 -C "homeassistant" -f ~/.ssh/id_ha
```

Leave the passphrase empty — the Git pull add-on cannot handle passphrases.

### Add the public key to GitHub as a deploy key

```bash
cat ~/.ssh/id_ha.pub
```

Copy the output. In GitHub:

1. Go to your repository → **Settings → Deploy keys**
2. Click **Add deploy key**
3. Give it a title (e.g. `homeassistant-node`)
4. Paste the public key
5. **Do not** check "Allow write access" — read-only is sufficient for one-way sync
6. Click **Add key**

### Configure git to use this key for /config

Use `includeIf` to scope the key to the `/config` repo only — no global SSH config changes needed:

```bash
cat >> ~/.gitconfig << 'EOF'

[includeIf "gitdir:/config/"]
    path = ~/.gitconfig-ha
EOF
```

```bash
cat > ~/.gitconfig-ha << 'EOF'
[user]
    name = your-username
    email = your@email.com

[core]
    sshCommand = ssh -i ~/.ssh/id_ha
EOF
```

### Test

```bash
cd /config
git fetch
```

No errors means authentication is working.

---

## 4. Install the Git Pull Add-on

1. **Settings → Apps → App Store**
2. Search **Git pull**
3. Install and enable **Start on boot**

### Configure

Go to the **Configuration** tab:

```yaml
repository: git@github.com:YOUR_ORG/YOUR_REPO.git
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
  - "YOUR_KEY_LINE_1"
  - "YOUR_KEY_LINE_2"
  - "-----END OPENSSH PRIVATE KEY-----"
deployment_user: ""
deployment_password: ""
deployment_key_protocol: ed25519
repeat:
  active: true
  interval: 3600
```

Each line of the private key must be a separate quoted list item. To get the key contents:

```bash
cat ~/.ssh/id_ha
```

Click **Save**, then **Start**.

---

## 5. Verify

Check the **Log** tab of the Git pull add-on. You should see:

```
[Info] Git origin is correctly set to git@github.com:YOUR_ORG/YOUR_REPO.git
[Info] Start git fetch...
[Info] Start git pull...
Already up to date.
```

If you see authentication errors, confirm the deploy key is added to the repo and the private key in the add-on config is correct.

---

## Workflow Going Forward

1. Edit files in your repo on your Mac or in GitHub
2. Commit and push to `main`
3. The Git pull add-on pulls the changes within 60 minutes automatically
4. To pull immediately: **Settings → Apps → Git pull → Restart**

---

## Notes

- `secrets.yaml` is never committed — manage it directly on the HA instance
- If you add new sensitive files later, add them to `.gitignore` before committing
- The add-on pulls changes from GitHub into HA only — changes made directly in HA are not pushed back automatically