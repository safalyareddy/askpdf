#!/bin/bash
set -e

echo "AskPDF Frontend Build Pipeline starting..."

# Create clean distribution directory
mkdir -p public

# Inject production API URL if provided via Vercel Environment Variables
if [ -n "$ASKPDF_API_URL" ]; then
  echo "Injecting ASKPDF_API_URL: $ASKPDF_API_URL into config.js"
  echo "window.ASKPDF_API_URL = \"$ASKPDF_API_URL\";" > public/config.js
elif [ -n "$RAILWAY_PUBLIC_DOMAIN" ]; then
  echo "Injecting RAILWAY_PUBLIC_DOMAIN: https://$RAILWAY_PUBLIC_DOMAIN into config.js"
  echo "window.ASKPDF_API_URL = \"https://$RAILWAY_PUBLIC_DOMAIN\";" > public/config.js
else
  echo "No ASKPDF_API_URL set; using dynamic/relative API routing."
  echo "window.ASKPDF_API_URL = window.ASKPDF_API_URL || \"\";" > public/config.js
fi

# Keep root config.js in sync for local execution
cp public/config.js config.js

# Copy static frontend HTML files
cp index.html public/
cp admin.html public/
mkdir -p public/admin
cp admin.html public/admin/index.html

echo "Frontend build completed successfully."
