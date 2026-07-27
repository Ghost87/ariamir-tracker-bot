#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example and set BOT_TOKEN"
  exit 1
fi
mkdir -p data/backups
python3 bot.py
