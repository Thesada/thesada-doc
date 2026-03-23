---
title: SSH Identity Switching for Multiple GitHub Orgs
parent: Troubleshooting
nav_order: 4
description: "Use different SSH keys for different GitHub organisations with host aliases and includeIf."
---

# Using Different SSH Keys for Different GitHub Organisations

## Problem

You have multiple GitHub accounts or organisations and need to use
different SSH keys for each. The default SSH config sends the same
key for all github.com connections.

## Solution

Two mechanisms work together: an SSH host alias for cloning, and
`includeIf` in gitconfig for automatic identity switching by directory.

### 1. SSH Host Alias

Add to `~/.ssh/config`:

```
Host github-myorg
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_myorg
    IdentitiesOnly yes
```

`IdentitiesOnly yes` prevents SSH from trying other keys. This ensures
only the specified key is offered to GitHub.

Clone using the alias instead of `github.com`:

```bash
git clone git@github-myorg:MyOrg/my-repo.git
```

### 2. Automatic Identity by Directory

Add to `~/.gitconfig`:

```
[includeIf "gitdir:~/projects/myorg/"]
    path = ~/.gitconfig-myorg
```

Create `~/.gitconfig-myorg`:

```
[user]
    name = your-name
    email = your-email@example.com

[core]
    sshCommand = ssh -i ~/.ssh/id_myorg
```

Any repo cloned under `~/projects/myorg/` automatically uses the
correct SSH key and git identity. No manual switching needed.

### 3. Verify

```bash
cd ~/projects/myorg/my-repo
git config user.name    # should show: your-name
ssh -T git@github-myorg  # should show: Hi your-name!
```

## Notes

- The `gitdir` path in `includeIf` must end with a trailing slash.
- This works for any number of organisations. Add another `includeIf`
  block and SSH host alias for each.
- For HA's Git pull add-on, a separate deploy key is used instead of
  the SSH host alias. See [HA Git Pull](ha-git-pull).
