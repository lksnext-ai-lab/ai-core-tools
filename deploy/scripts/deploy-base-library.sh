#!/bin/bash

# Script to deploy/rebuild the base library for client projects

set -e

echo "🚀 Deploying AI Core Tools Base Library..."

# Navigate to base frontend directory
cd /home/aritz/data/proiektuak/LKS/IA-Core-Tools/ai-core-tools/frontend

echo "📦 Building base library..."
npm run build:lib

echo "✅ Base library built successfully!"
echo "📁 Library location: /home/aritz/data/proiektuak/LKS/IA-Core-Tools/ai-core-tools/frontend/dist/"

echo ""
echo "🔄 To update client projects, run:"
echo "   cd /path/to/client/frontend"
echo "   rm -rf node_modules package-lock.json"
echo "   npm install"
echo ""
echo "Or use the update-client script:"
echo "   ./deploy/scripts/update-client.sh <client-name>"
