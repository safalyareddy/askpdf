#!/bin/bash
set -e

echo "AskPDF Frontend Build Pipeline starting..."

# Inject production API URL if provided via Vercel Environment Variables
if [ -n "$ASKPDF_API_URL" ]; then
  echo "Injecting ASKPDF_API_URL: $ASKPDF_API_URL into config.js"
  echo "window.ASKPDF_API_URL = \"$ASKPDF_API_URL\";" > config.js
elif [ -n "$RAILWAY_PUBLIC_DOMAIN" ]; then
  echo "Injecting RAILWAY_PUBLIC_DOMAIN: https://$RAILWAY_PUBLIC_DOMAIN into config.js"
  echo "window.ASKPDF_API_URL = \"https://$RAILWAY_PUBLIC_DOMAIN\";" > config.js
else
  echo "No ASKPDF_API_URL set; using dynamic/relative API routing."
  echo "window.ASKPDF_API_URL = window.ASKPDF_API_URL || \"\";" > config.js
fi

echo "Frontend build completed successfully."
