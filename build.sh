#!/bin/bash
set -e

echo "AskPDF Frontend Build Pipeline starting..."

# Create clean distribution directory
mkdir -p public

# Inject production API URL if provided via environment, defaulting to same-origin
DEFAULT_API_URL="window.location.origin"
TARGET_API_URL="${ASKPDF_API_URL:-}"

if [ -n "$TARGET_API_URL" ]; then
    echo "Injecting custom ASKPDF_API_URL: $TARGET_API_URL into config.js"
    echo "window.ASKPDF_API_URL = \"$TARGET_API_URL\";" > public/config.js
else
    echo "Using same-origin API configuration"
    echo "window.ASKPDF_API_URL = window.location.origin;" > public/config.js
fi

# Keep root config.js in sync
cp public/config.js config.js

# Copy static frontend HTML files
cp index.html public/
cp admin.html public/
mkdir -p public/admin
cp admin.html public/admin/index.html

echo "Frontend build completed successfully."
