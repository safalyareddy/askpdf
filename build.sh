#!/bin/bash
set -e

echo "AskPDF Frontend Build Pipeline starting..."

# Create clean distribution directory
mkdir -p public

# Inject production API URL if provided via Vercel Environment Variables, defaulting to Render
DEFAULT_API_URL="https://documind-ai-ddt8.onrender.com"
TARGET_API_URL="${ASKPDF_API_URL:-$DEFAULT_API_URL}"

echo "Injecting ASKPDF_API_URL: $TARGET_API_URL into config.js"
echo "window.ASKPDF_API_URL = \"$TARGET_API_URL\";" > public/config.js

# Keep root config.js in sync for local execution
cp public/config.js config.js

# Copy static frontend HTML files
cp index.html public/
cp admin.html public/
mkdir -p public/admin
cp admin.html public/admin/index.html

echo "Frontend build completed successfully."
