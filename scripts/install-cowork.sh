#!/usr/bin/env bash
set -euo pipefail

REPO="nadeemis/contelligence"
API="https://api.github.com/repos/${REPO}/releases/latest"

os="$(uname -s | tr '[:upper:]' '[:lower:]')"
arch="$(uname -m)"
case "${arch}" in
  x86_64)  arch="x64" ;;
  arm64|aarch64) arch="arm64" ;;
esac

echo "→ Fetching latest Contelligence release…"
release_json="$(curl -fsSL -H 'Accept: application/vnd.github+json' "${API}")"
version="$(printf '%s' "${release_json}" | grep -oE '"tag_name":\s*"[^"]+"' | head -1 | cut -d'"' -f4)"

# Resolve asset URL based on os+arch (regex over asset names)
pattern=""
case "${os}" in
  darwin) pattern="Contelligence-darwin-${arch}-.*\\.zip" ;;
  linux)
    if command -v dpkg >/dev/null 2>&1; then pattern="contelligence_.*_amd64\\.deb"
    else pattern="contelligence-.*\\.x86_64\\.rpm"; fi ;;
  *) echo "Unsupported OS: ${os}" >&2; exit 1 ;;
esac

asset_url="$(printf '%s' "${release_json}" \
  | grep -oE '"browser_download_url":\s*"[^"]+"' \
  | cut -d'"' -f4 \
  | grep -E "${pattern}" | head -1)"

[[ -n "${asset_url}" ]] || { echo "No matching asset for ${os}/${arch}" >&2; exit 1; }

tmp="$(mktemp -d)"
file="${tmp}/$(basename "${asset_url}")"
echo "→ Downloading ${file}"
curl -fL --progress-bar -o "${file}" "${asset_url}"

# Checksum verification (optional — skipped if checksums.txt missing)
checksum_url="$(printf '%s' "${release_json}" \
  | grep -oE '"browser_download_url":\s*"[^"]+checksums\\.txt"' \
  | cut -d'"' -f4 | head -1 || true)"
if [[ -n "${checksum_url}" ]]; then
  echo "→ Verifying SHA-256"
  curl -fsSL "${checksum_url}" -o "${tmp}/checksums.txt"
  ( cd "${tmp}" && shasum -a 256 -c checksums.txt --ignore-missing )
fi

# Install
case "${os}" in
  darwin)
    echo "→ Installing to /Applications"
    unzip -q -o "${file}" -d "${tmp}/app"
    rm -rf "/Applications/Contelligence.app"
    mv "${tmp}/app/Contelligence.app" /Applications/
    xattr -dr com.apple.quarantine "/Applications/Contelligence.app" || true
    echo "✓ Installed Contelligence ${version}. Launch from /Applications/Contelligence.app"
    ;;
  linux)
    if [[ "${file}" == *.deb ]]; then sudo apt install -y "${file}"
    else sudo dnf install -y "${file}" || sudo rpm -Uvh "${file}"; fi
    echo "✓ Installed Contelligence ${version}"
    ;;
esac