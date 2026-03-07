# ---------------------------------------------------------------------------
# GitHub Copilot CLI — headless server container
# ---------------------------------------------------------------------------
# Installs the Copilot CLI binary from GitHub releases and runs it in
# headless mode on port 4321.  Used as a backend service for Copilot SDK
# connectivity (see docs/guides/setup/backend-services.md).
# ---------------------------------------------------------------------------

FROM debian:bookworm-slim

ARG COPILOT_CLI_VERSION=latest
ARG TARGETARCH

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Map Docker TARGETARCH to Copilot CLI arch naming
RUN case "${TARGETARCH}" in \
        amd64) ARCH="x64" ;; \
        arm64) ARCH="arm64" ;; \
        *)     echo "Unsupported architecture: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    if [ "${COPILOT_CLI_VERSION}" = "latest" ] || [ -z "${COPILOT_CLI_VERSION}" ]; then \
        DOWNLOAD_URL="https://github.com/github/copilot-cli/releases/latest/download/copilot-linux-${ARCH}.tar.gz"; \
        CHECKSUMS_URL="https://github.com/github/copilot-cli/releases/latest/download/SHA256SUMS.txt"; \
    else \
        case "${COPILOT_CLI_VERSION}" in v*) ;; *) COPILOT_CLI_VERSION="v${COPILOT_CLI_VERSION}" ;; esac; \
        DOWNLOAD_URL="https://github.com/github/copilot-cli/releases/download/${COPILOT_CLI_VERSION}/copilot-linux-${ARCH}.tar.gz"; \
        CHECKSUMS_URL="https://github.com/github/copilot-cli/releases/download/${COPILOT_CLI_VERSION}/SHA256SUMS.txt"; \
    fi && \
    TARBALL="copilot-linux-${ARCH}.tar.gz" && \
    echo "Downloading Copilot CLI from: ${DOWNLOAD_URL}" && \
    TMP_DIR="$(mktemp -d)" && \
    curl -fsSL "${DOWNLOAD_URL}" -o "${TMP_DIR}/${TARBALL}" && \
    curl -fsSL "${CHECKSUMS_URL}" -o "${TMP_DIR}/SHA256SUMS.txt" && \
    cd "${TMP_DIR}" && sha256sum -c --ignore-missing SHA256SUMS.txt && \
    tar -xzf "${TMP_DIR}/${TARBALL}" -C /usr/local/bin && \
    chmod +x /usr/local/bin/copilot && \
    rm -rf "${TMP_DIR}"

# Session state volume mount point
RUN mkdir -p /root/.copilot/session-state

# Workspace directory mount point (optional, for persistent workspaces)
RUN mkdir -p /workspace

EXPOSE 4321

ENTRYPOINT ["copilot"]
CMD ["--no-auto-update", \
"--headless", \
"--model", "claude-opus-4.6", \
"--add-dir", "/workspace", \
"--add-dir", "/root/.copilot/session-state", \
"--allow-all-tools", \
"--port", "4321"]
