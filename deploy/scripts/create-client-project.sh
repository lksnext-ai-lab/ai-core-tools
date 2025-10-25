#!/bin/bash

CLIENT_NAME=$1
CLIENT_DIR="/home/aritz/data/proiektuak/LKS/IA-Core-Tools/clients/${CLIENT_NAME}"

if [ -z "$CLIENT_NAME" ]; then
    echo "Usage: ./create-client-project.sh <client-name>"
    exit 1
fi

echo "Creating client project: ${CLIENT_NAME}"

# Create client directory
mkdir -p "${CLIENT_DIR}"

# Copy only frontend template
cp -r /home/aritz/data/proiektuak/LKS/IA-Core-Tools/ai-core-tools/deploy/templates/client-template/frontend "${CLIENT_DIR}/"

# Replace placeholders
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_ID_HERE/${CLIENT_NAME}/g" {} +
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_NAME_HERE/${CLIENT_NAME}/g" {} +
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_COMPANY_NAME/${CLIENT_NAME}/g" {} +
find "${CLIENT_DIR}" -type f -exec sed -i "s/CLIENT_HEADER_TITLE/${CLIENT_NAME}/g" {} +

echo "Client project created at: ${CLIENT_DIR}"
echo "Next steps:"
echo "1. cd ${CLIENT_DIR}"
echo "2. npm install"
echo "3. Update src/config/clientConfig.ts with client details"
echo "4. npm run dev"
