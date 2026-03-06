# RBAC Setup & Security Guide

> **Phase 3** — MCP Authentication, RBAC Role Assignments, Key Vault, and Network Isolation

---

## 1. Required RBAC Role Assignments

The Container App's **system-assigned managed identity** requires the following
RBAC roles. Follow the principle of **least privilege** — scope each role to the
specific resource, never to the subscription.

| Azure Service            | RBAC Role                            | Role Definition ID                     | Scope               |
|--------------------------|--------------------------------------|----------------------------------------|----------------------|
| Storage Account          | Storage Blob Data Contributor        | `ba92f5b4-2d11-453d-a403-e96b0029c9fe` | Storage account      |
| AI Search                | Search Index Data Contributor        | `8ebe5a00-799e-43f5-93ac-243d3dce84a7` | AI Search service    |
| Cosmos DB                | Cosmos DB Built-in Data Contributor  | `00000000-0000-0000-0000-000000000002` | Cosmos DB account    |
| Document Intelligence    | Cognitive Services User              | `a97b65f3-24c7-4388-baec-2e87135dc908` | Doc Intelligence     |
| Azure OpenAI             | Cognitive Services OpenAI User       | `5e0bd9bd-7b93-4f28-af87-19fc36ad61bd` | Azure OpenAI         |
| Key Vault                | Key Vault Secrets User               | `4633458b-17de-408a-b874-0445c86b69e6` | Key Vault            |

### CLI Commands

Replace `<principal-id>` with the Container App's managed identity principal ID
and `<resource-id>` with each resource's full ARM ID.

```bash
# Storage Blob Data Contributor
az role assignment create \
  --assignee <principal-id> \
  --role "Storage Blob Data Contributor" \
  --scope <storage-account-resource-id>

# Search Index Data Contributor
az role assignment create \
  --assignee <principal-id> \
  --role "Search Index Data Contributor" \
  --scope <search-service-resource-id>

# Cosmos DB Built-in Data Contributor
az cosmosdb sql role assignment create \
  --account-name <cosmos-account> \
  --resource-group <rg> \
  --scope "/" \
  --principal-id <principal-id> \
  --role-definition-id 00000000-0000-0000-0000-000000000002

# Cognitive Services User (Document Intelligence)
az role assignment create \
  --assignee <principal-id> \
  --role "Cognitive Services User" \
  --scope <doc-intelligence-resource-id>

# Cognitive Services OpenAI User
az role assignment create \
  --assignee <principal-id> \
  --role "Cognitive Services OpenAI User" \
  --scope <openai-resource-id>

# Key Vault Secrets User
az role assignment create \
  --assignee <principal-id> \
  --role "Key Vault Secrets User" \
  --scope <keyvault-resource-id>
```

### Verification

```bash
az role assignment list --assignee <principal-id> --output table
```

---

## 2. GitHub PAT in Key Vault

The GitHub MCP Server requires a Personal Access Token stored in Azure Key Vault.

### Creating the PAT

1. Go to **GitHub → Settings → Developer settings → Fine-grained tokens**
2. Create a new token with:
   - **Scope:** `copilot` (required)
   - **Scope:** `read:org` (optional — for org-level repository access)
3. Copy the token value

### Storing in Key Vault

```bash
az keyvault secret set \
  --vault-name <vault-name> \
  --name "github-copilot-token" \
  --value "<github-pat-value>"
```

> **Security:** Never store the PAT in source code, `.env` files, container
> images, or environment variables directly. Always use Key Vault.

### Rotation

Set a reminder to rotate the PAT before expiration. Update the Key Vault secret
with the new value — the agent resolves the secret at startup.

---

## 3. DefaultAzureCredential Chain

The Azure MCP Server and all Azure SDK connectors use `DefaultAzureCredential`,
which tries the following credential sources in order:

1. **Environment Variables** — `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`
2. **Managed Identity** — System-assigned or user-assigned (production)
3. **Azure CLI** — `az login` credentials (development)
4. **VS Code** — Azure Account extension credentials (development)
5. **Azure PowerShell** — `Connect-AzAccount` (development)

### Production (Container Apps)

The Container App must have **system-assigned managed identity** enabled:

```bash
az containerapp identity assign \
  --name hikmaforge-agent \
  --resource-group <rg> \
  --system-assigned
```

No explicit credential configuration is needed — `DefaultAzureCredential`
automatically uses the managed identity.

### Development

Ensure you are logged in via Azure CLI:

```bash
az login
az account set --subscription <subscription-id>
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `CredentialUnavailableError` | No credential source found | Run `az login` or enable managed identity |
| `AuthenticationError: AADSTS700016` | Incorrect tenant/client | Verify `AZURE_TENANT_ID` or `az account show` |
| `ForbiddenError` on storage | Missing RBAC role | Assign `Storage Blob Data Contributor` |
| `403` on Key Vault | Missing role or access policy | Assign `Key Vault Secrets User` |
| `AuthorizationFailure` on Cosmos | Data-plane RBAC not enabled | Use `az cosmosdb sql role assignment create` |

---

## 4. Network Isolation (Production Guidance)

> **Note:** Actual VNet/private endpoint provisioning is deferred to **Phase 4
> (Production Hardening)**. This section documents the target architecture.

### Target Architecture

- **VNet Integration:** Container App Environment connected to a VNet
- **Private Endpoints** for all data services:
  - Azure Storage (blob, table)
  - Azure Cosmos DB
  - Azure AI Search
  - Azure Key Vault
  - Azure OpenAI
  - Azure Document Intelligence
- **NSG Rules:** Restrict MCP server (sidecar) traffic to only the agent container
- **No public endpoints** for data services in production

### MCP Server Network Considerations

- In **stdio mode**, the MCP server runs inside the agent container — no network
  exposure
- In **HTTP mode** (sidecar), configure internal-only ingress — the MCP server
  should not be externally accessible
- The MCP server inherits the Container App's VNet and managed identity

### Reference

- [Microsoft MCP Server Security Guidance](https://learn.microsoft.com/en-us/azure/developer/model-context-protocol)
- [Container Apps VNet Integration](https://learn.microsoft.com/en-us/azure/container-apps/vnet-custom)
- [Private Endpoints Overview](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview)
