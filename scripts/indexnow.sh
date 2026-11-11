#!/usr/bin/env bash

# Submit every URL in a live sitemap to IndexNow (Bing, Yandex, Seznam, Naver).
# usage: scripts/indexnow.sh <sitemap-url> <key>   DRY=1 prints the payload only.
set -euo pipefail

sitemap="${1:?usage: indexnow.sh <sitemap-url> <key>}"
key="${2:?usage: indexnow.sh <sitemap-url> <key>}"
[[ "$key" =~ ^[0-9a-f]{32}$ ]] || { echo "indexnow: key must be 32 hex characters" >&2; exit 2; }
origin="$(printf '%s' "$sitemap" | sed -E 's#^(https://[^/]+)/.*#\1#')"
[[ "$origin" == https://* ]] || { echo "indexnow: sitemap must be an https URL" >&2; exit 2; }
host="${origin#https://}"

# The engines reject the batch unless the key file is live.
live_key="$(curl -fsS --max-time 20 "$origin/$key.txt" | tr -d '[:space:]')"
[[ "$live_key" == "$key" ]] || { echo "indexnow: $origin/$key.txt does not serve the key, deploy first" >&2; exit 1; }

urls="$(curl -fsS --max-time 30 "$sitemap" | grep -oE '<loc>[^<]+</loc>' | sed -E 's#</?loc>##g' | grep -F "$origin/" || true)"
[[ -n "$urls" ]] || { echo "indexnow: no URLs under $origin in $sitemap" >&2; exit 1; }

list="$(printf '%s\n' "$urls" | sed -E 's/["\\]//g; s/.*/"&"/' | paste -sd, -)"
payload="{\"host\":\"$host\",\"key\":\"$key\",\"keyLocation\":\"$origin/$key.txt\",\"urlList\":[$list]}"
count="$(printf '%s\n' "$urls" | wc -l | tr -d ' ')"

if [[ "${DRY:-0}" == 1 ]]; then
  printf '%s\n' "$payload"
  echo "indexnow: dry run, $count URLs not sent" >&2
  exit 0
fi

code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -H 'Content-Type: application/json; charset=utf-8' \
  --data "$payload" https://api.indexnow.org/indexnow)"
case "$code" in
  200|202) echo "indexnow: $count URLs accepted for $host (HTTP $code)" ;;
  *) echo "indexnow: HTTP $code for $host" >&2; exit 1 ;;
esac
