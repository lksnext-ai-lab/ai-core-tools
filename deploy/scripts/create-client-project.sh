#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Get the project root (two levels up from scripts/)
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

CLIENT_NAME=$1
CLIENT_DIR="${PROJECT_ROOT}/clients/${CLIENT_NAME}"
TEMPLATE_DIR="${PROJECT_ROOT}/deploy/templates/client-template"

if [ -z "$CLIENT_NAME" ]; then
    echo "Usage: ./create-client-project.sh <client-name>"
    exit 1
fi

echo "Creating client project: ${CLIENT_NAME}"

# Create client directory
mkdir -p "${CLIENT_DIR}"

# Copy frontend template
cp -r "${TEMPLATE_DIR}/frontend" "${CLIENT_DIR}/"

# Copy hello-world-plugin (sample plugin)
cp -r "${TEMPLATE_DIR}/hello-world-plugin" "${CLIENT_DIR}/"

# Copy plugin documentation
cp "${TEMPLATE_DIR}/PLUGIN_EXAMPLES.md" "${CLIENT_DIR}/"

# Replace placeholders
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_ID_HERE/${CLIENT_NAME}/g" {} +
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_NAME_HERE/${CLIENT_NAME}/g" {} +
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_COMPANY_NAME/${CLIENT_NAME}/g" {} +
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_HEADER_TITLE/${CLIENT_NAME}/g" {} +

echo "Client project created at: ${CLIENT_DIR}"
echo ""
echo "📁 Project Structure:"
echo "  frontend/          - Main client application"
echo "  hello-world-plugin/ - Sample plugin demonstrating plugin architecture"
echo "  PLUGIN_EXAMPLES.md - Guide for creating and using plugins"
echo ""
echo "Next steps:"
echo "1. cd ${CLIENT_DIR}/frontend"
echo "2. npm install"
echo "3. Update src/config/libraryConfig.ts with client details"
echo "4. Add your logo to public/client-logo.png"
echo "5. Add your favicon to public/client-favicon.ico"
echo "6. npm run dev"
echo ""
echo "🔌 Plugin Development:"
echo "1. cd ${CLIENT_DIR}/hello-world-plugin"
echo "2. npm install"
echo "3. npm run build"
echo "4. Check PLUGIN_EXAMPLES.md for customization guide"
echo ""
echo "🚀 Features Available:"
echo "- Modular components (Header, Sidebar, Footer, Layout)"
echo "- Advanced theme system with multiple themes"
echo "- Plugin architecture with sample Hello World plugin"
echo "- Route extensibility with ExtraRoute"
echo "- Component customization options"
echo "- Check out /extensibility-demo and /hello-world for examples!"
