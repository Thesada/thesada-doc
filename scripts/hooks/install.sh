#!/bin/sh
# Link scripts/hooks/pre-push into .git/hooks. Re-run after the hook changes.

set -eu

repo_root="$(git rev-parse --show-toplevel)"
src="$repo_root/scripts/hooks/pre-push"
dst="$repo_root/.git/hooks/pre-push"

chmod +x "$src"
ln -sfn "$src" "$dst"
echo "linked pre-push -> $src"
