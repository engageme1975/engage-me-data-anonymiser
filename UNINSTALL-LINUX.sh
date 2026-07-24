#!/usr/bin/env bash
set -euo pipefail

APP_ID="engage-me-data-anonymiser"
rm -f "${HOME}/.local/bin/${APP_ID}"
rm -f "${HOME}/.local/share/applications/${APP_ID}.desktop"
rm -rf "${HOME}/.local/share/${APP_ID}"

echo "Removed ${APP_ID}."