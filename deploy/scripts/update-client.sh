#!/bin/bash

# Script to update a client project with the latest base library

set -e

CLIENT_NAME=$1

if [ -z "$CLIENT_NAME" ]; then
    echo "Usage: ./update-client.sh <client-name>"
    echo "Example: ./update-client.sh test-api-config"
    exit 1
fi

CLIENT_DIR="/home/aritz/data/proiektuak/LKS/IA-Core-Tools/ai-core-tools/clients/${CLIENT_NAME}"

if [ ! -d "$CLIENT_DIR" ]; then
    echo "❌ Client project not found: $CLIENT_DIR"
    exit 1
fi

echo "🔄 Updating client project: $CLIENT_NAME"

# Navigate to client frontend directory
cd "${CLIENT_DIR}/frontend"

echo "🗑️  Removing old dependencies..."
rm -rf node_modules package-lock.json

echo "📦 Installing updated dependencies..."
npm install

echo "✅ Client project updated successfully!"
echo "🚀 You can now run: npm run dev"
