#!/bin/bash
set -Eeuo pipefail

trap 'echo "❌ Update failed on line $LINENO. Aborting." >&2' ERR

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "❌ Required command not found: $1" >&2
    exit 1
  }
}

run_step() {
  local message="$1"
  shift
  echo "$message"
  "$@"
}

echo "🚀 Initializing Fetchy System Update..."

require_command git
require_command sudo
require_command docker

if [ ! -f "docker-compose.yml" ]; then
  echo "❌ docker-compose.yml not found. Run this script from the Fetchy project root." >&2
  exit 1
fi

run_step "📥 Syncing with the remote repository..." git pull --ff-only
run_step "🏗️ Rebuilding Docker infrastructure..." sudo docker compose build
run_step "🟢 Deploying the updated system..." sudo docker compose up -d

echo "✅ Update successfully deployed! Fetchy is now operating on the latest version. 🎉"
