# MCP Server Deployment Guide

## Overview

The Azure MCP Server provides a unified interface to 42+ Azure services.
Contelligence supports two deployment modes:

| Mode | Transport | Best for |
|------|-----------|----------|
| **Stdio** (default) | Subprocess pipe | Development, simple deployments |
| **HTTP** | HTTP/SSE on port 5008 | Production, isolated scaling |

---

## 1. Stdio Mode (Development / Simple)

The MCP server runs as a subprocess **inside** the agent container.

### Setup

The Dockerfile already installs `msmcp-azure`:

```dockerfile
RUN pip install --no-cache-dir msmcp-azure && azmcp --version
```

No additional containers are needed. The Copilot SDK launches the MCP
server as a subprocess automatically using the config from
`app/mcp/config.py`.

### Configuration

```env
# .env — No AZURE_MCP_SERVER_URL means stdio mode is used
# AZURE_MCP_SERVER_URL=
```

### Pros / Cons

| | |
|---|---|
| **Pro** | Simplest deployment — single container |
| **Pro** | No network configuration needed |
| **Con** | Shares CPU/memory with the agent |
| **Con** | Restarts when the agent restarts |

---

## 2. HTTP Mode (Production)

The MCP server runs as a **sidecar container** or separate Container App,
exposing an HTTP endpoint.

### Azure Container Apps (Bicep)

Deploy with the provided Bicep module:

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/modules/mcp_sidecar.bicep \
  --parameters containerAppEnvironmentId=<env-id>
```

The sidecar runs at `http://azure-mcp-server:5008` (internal only).

### Configuration

```env
# .env — point the agent to the HTTP sidecar
AZURE_MCP_SERVER_URL=http://azure-mcp-server:5008
```

When `AZURE_MCP_SERVER_URL` is set, the agent config switches from stdio
to HTTP transport automatically.

### Docker Compose (local development)

```bash
docker-compose -f docker-compose.yml up
```

See `docker-compose.yml` at the project root for the full configuration
with the MCP sidecar.

### RBAC

The sidecar's managed identity needs the same RBAC roles as the agent.
See [RBAC_SETUP.md](../docs/RBAC_SETUP.md) for the full list.

After deploying the sidecar, assign roles to its principal ID:

```bash
MCP_PRINCIPAL_ID=$(az containerapp show \
  --name azure-mcp-server \
  --resource-group <rg-name> \
  --query identity.principalId -o tsv)

az role assignment create \
  --assignee $MCP_PRINCIPAL_ID \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>
```

### Pros / Cons

| | |
|---|---|
| **Pro** | Independent scaling and resource isolation |
| **Pro** | Health monitoring via Container Apps ingress |
| **Pro** | Can serve multiple agent replicas |
| **Con** | Additional container to manage |
| **Con** | Requires internal networking setup |

---

## 3. Telemetry

### Application Insights

Set the connection string to route MCP traces:

```env
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
```

The MCP server reads this automatically — no additional SDK setup.

### Disable Microsoft Telemetry

```env
AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT=false
```

This is the default in Contelligence. Set to `true` only if you want to
participate in Microsoft's telemetry programme.

### Viewing MCP Traces

1. Open the Application Insights resource in Azure Portal
2. Navigate to **Transaction search** or **Logs**
3. Query:
   ```kql
   traces
   | where customDimensions["source"] == "azure-mcp"
   | order by timestamp desc
   | take 50
   ```

---

## 4. Environment Variables (Phase 3)

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_MCP_SERVER_URL` | No | HTTP endpoint for MCP sidecar. Omit for stdio mode. |
| `AZURE_MCP_COLLECT_TELEMETRY_MICROSOFT` | No | `false` (default) to opt out. |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | No | Routes MCP telemetry to App Insights. |
| `KEY_VAULT_URL` | No | Key Vault for GitHub PAT resolution. |
| `AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT` | No | Default: `text-embedding-3-large`. |
| `AZURE_OPENAI_DEPLOYMENT` | No | Default: `gpt-4.1`. |
| `APPROVAL_TIMEOUT_SECONDS` | No | Default: 300 (5 minutes). |
