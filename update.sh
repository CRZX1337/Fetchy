#!/bin/bash

echo "🚀 Initializing Fetchy System Update..."

# 1. Pull latest code from GitHub
echo "📥 Syncing with the remote repository..."
git pull

# 2. Build Docker images completely fresh (no cache)
echo "🏗️ Rebuilding Docker infrastructure..."
sudo docker compose build

# 3. Start/Update the Docker container in the background
echo "🟢 Deploying the updated system..."
sudo docker compose up -d

echo "✅ Update successfully deployed! Fetchy is now operating on the latest version. 🎉"
