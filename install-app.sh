#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Engage-Me Data Anonymiser"
APP_ID="engage-me-data-anonymiser"
IMAGE="${IMAGE:-parthiv1911/engage-me-data-anonymiser:24h}"
PORT="${PORT:-8501}"
INSTALL_DIR="${HOME}/.local/share/${APP_ID}"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
LAUNCHER_PATH="${BIN_DIR}/${APP_ID}"
DESKTOP_FILE_PATH="${DESKTOP_DIR}/${APP_ID}.desktop"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR"

cat > "$INSTALL_DIR/launch.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE}"
CONTAINER_NAME="${APP_ID}"
PORT="${PORT}"
INSTALL_URL="https://www.docker.com/products/docker-desktop/"

prompt_to_continue() {
  local message="\$1"
  echo "\$message"
  read -r -p "Press Enter after you finish, or Ctrl+C to stop. " _
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed on this machine."
  echo "Install Docker Desktop from: \$INSTALL_URL"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "\$INSTALL_URL" >/dev/null 2>&1 || true
  fi
  prompt_to_continue "Install Docker Desktop, start it, then come back here."
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed, but the Docker engine is not running."
  prompt_to_continue "Open Docker Desktop, wait until it is running, then continue."
fi

docker pull "\$IMAGE"
docker rm -f "\$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "\$CONTAINER_NAME" \
  -p "\$PORT:8501" \
  "\$IMAGE"

echo "App is starting. Open http://localhost:\$PORT in your browser."

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:\$PORT" >/dev/null 2>&1 || true
fi
EOF

chmod +x "$INSTALL_DIR/launch.sh"

cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
exec "$INSTALL_DIR/launch.sh"
EOF

chmod +x "$LAUNCHER_PATH"

cat > "$DESKTOP_FILE_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Launch the Engage-Me Data Anonymiser Docker app
Exec=${LAUNCHER_PATH}
Terminal=true
Categories=Utility;
EOF

echo "Installed ${APP_NAME}."
echo "You can launch it from your app menu or run: ${APP_ID}"
