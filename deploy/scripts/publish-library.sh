#!/bin/bash

# Script to publish the base library to npm registry

set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

echo "📦 Publishing @lksnext/ai-core-tools-base to npm registry..."

# Navigate to frontend directory
cd "$FRONTEND_DIR"

# Check if user is logged in to npm
if ! npm whoami &>/dev/null; then
    echo "⚠️  Not logged in to npm. Please run: npm login"
    echo "   You'll need an npm account. Create one at: https://www.npmjs.com/signup"
    exit 1
fi

# Show current version
VERSION=$(node -p "require('./package.json').version")
echo "📌 Current version: $VERSION"

# Ask for confirmation
read -p "Publish version $VERSION to npm? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Publish cancelled"
    exit 1
fi

# Build and publish
echo "🔨 Building library..."
npm run build:lib

echo "📤 Publishing to npm registry..."
npm publish --access public

echo ""
echo "✅ Successfully published @lksnext/ai-core-tools-base@$VERSION to npm!"
echo ""
echo "🔗 Package URL: https://www.npmjs.com/package/@lksnext/ai-core-tools-base"
echo ""
echo "📥 Users can now install with:"
echo "   npm install @lksnext/ai-core-tools-base"

