#!/usr/bin/env bash
set -euo pipefail

# Simple helper to register Telegram webhook for this service.

BOT_TOKEN="${BOT_TOKEN:-}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-}"
BASE_URL="${BASE_URL:-${1:-}}"

if [[ -z "$BOT_TOKEN" || -z "$WEBHOOK_SECRET" || -z "$BASE_URL" ]]; then
  echo "Usage: BOT_TOKEN=... WEBHOOK_SECRET=... BASE_URL=... ./set_webhook.sh" >&2
  echo "Or pass BASE_URL as the first argument: ./set_webhook.sh https://<service>.onrender.com" >&2
  exit 1
fi

WEBHOOK_URL="${BASE_URL%/}/telegram/webhook"

curl -X POST "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"${WEBHOOK_URL}\",\"secret_token\":\"${WEBHOOK_SECRET}\"}"
