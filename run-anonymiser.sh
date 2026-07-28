#!/usr/bin/env bash
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/engageme1975/engage-me-data-anonymiser:latest}"
CONTAINER_NAME="${CONTAINER_NAME:-engage-me-data-anonymiser}"
PORT="${PORT:-8501}"
INSTALL_URL="https://www.docker.com/products/docker-desktop/"

prompt_to_continue() {
  local message="$1"
  echo "$message"
  read -r -p "Press Enter after you finish, or Ctrl+C to stop. " _
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed on this machine."
  echo "Install Docker Desktop from: $INSTALL_URL"

  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$INSTALL_URL" >/dev/null 2>&1 || true
  fi

  prompt_to_continue "Install Docker Desktop, start it, then come back here."
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed, but the Docker engine is not running."
  prompt_to_continue "Open Docker Desktop, wait until it is running, then continue."
fi

docker pull "$IMAGE"
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER_NAME" \
  -p "$PORT:8501" \
  "$IMAGE"

echo "App is starting. Open http://localhost:$PORT in your browser."

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
fi