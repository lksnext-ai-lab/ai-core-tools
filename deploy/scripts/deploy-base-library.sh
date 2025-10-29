#!/bin/bash

# Script to deploy/rebuild the base library for client projects

set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "🚀 Deploying AI Core Tools Base Library..."

# Navigate to base frontend directory
cd "$FRONTEND_DIR"

echo "📦 Building base library..."
npm run build:lib

echo "✅ Base library built successfully!"
echo "📁 Library location: $FRONTEND_DIR/dist/"

echo ""
echo "📤 To publish to npm registry (OSS):"
echo "   cd $FRONTEND_DIR"
echo "   npm login  # First time only"
echo "   npm run publish:npm"
echo ""
echo "   Or test with dry-run:"
echo "   npm run publish:npm:dry-run"
echo ""
echo "🔄 To update client projects from npm:"
echo "   cd /path/to/client/frontend"
echo "   npm install @lksnext/ai-core-tools-base@latest"
echo ""
echo "🔄 To update client projects locally:"
echo "   cd /path/to/client/frontend"
echo "   rm -rf node_modules package-lock.json"
echo "   npm install"
echo ""
echo "Or use the update-client script:"
echo "   ./deploy/scripts/update-client.sh <client-name>"
