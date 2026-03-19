#!/usr/bin/env bash
# Build the Contelligence backend into a standalone binary with PyInstaller,
# then package the Cowork app with the backend bundled inside.
#
# Usage:
#   ./scripts/build-desktop.sh          # build both backend + cowork
#   ./scripts/build-desktop.sh backend  # build backend only
#   ./scripts/build-desktop.sh cowork # build cowork only (expects backend already built)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_DIR="${REPO_ROOT}/contelligence-agent"
COWORK_DIR="${REPO_ROOT}/contelligence-cowork"
BACKEND_DIST="${AGENT_DIR}/dist/contelligence-agent"

build_backend() {
  echo "==> Building Python backend with PyInstaller..."
  cd "${AGENT_DIR}"

  # Ensure PyInstaller is available
  if ! command -v pyinstaller &>/dev/null; then
    echo "    Installing PyInstaller..."
    pip install pyinstaller
  fi

  pyinstaller contelligence-agent.spec --noconfirm --clean
  echo "==> Backend built: ${BACKEND_DIST}"
}

build_cowork() {
  echo "==> Packaging Cowork app..."
  cd "${COWORK_DIR}"

  # Copy built backend into cowork resources
  local target="${COWORK_DIR}/resources/backend"
  rm -rf "${target}"
  if [ -d "${BACKEND_DIST}" ]; then
    echo "    Copying backend into cowork resources..."
    mkdir -p "${target}"
    cp -R "${BACKEND_DIST}/." "${target}/"
  else
    echo "WARNING: Backend dist not found at ${BACKEND_DIST}"
    echo "         Run './scripts/build-desktop.sh backend' first."
    exit 1
  fi

  npm install
  npm run make
  echo "==> Cowork app packaged — check ${COWORK_DIR}/out/"
}

case "${1:-all}" in
  backend)
    build_backend
    ;;
  cowork)
    build_cowork
    ;;
  all)
    build_backend
    build_cowork
    ;;
  *)
    echo "Usage: $0 [backend|cowork|all]"
    exit 1
    ;;
esac
