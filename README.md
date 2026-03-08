<!-- <p align="center">
    <h1 align="left" style="font-size:6em;">
    <picture>
    <img src="./assets/Contelligence-logo.png" alt="Contelligence Logo" />
    </picture>
    Contelligence
    </h1>
</p> -->

|  |  |
|--------|---------------------|
| <picture><img src="./assets/Contelligence-logo.png" alt="Contelligence Logo" /></picture> | <h1 align="left" style="font-size:6em;">Contelligence</h1> |

**AI-native, agentic content intelligence platform powered by GitHub Copilot SDK.**

Contelligence replaces brittle, hard-coded content processing pipelines with an autonomous AI agent that reasons step-by-step, ingests any content — documents, spreadsheets, presentations, web pages, audio, images — understands data by meaning, and delivers structured intelligence. All orchestrated through natural language.

---

[![Azure](https://img.shields.io/badge/Azure-Powered-0078D4?logo=microsoft-azure)](https://azure.microsoft.com)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776ab?logo=python)](https://www.python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8+-3178c6?logo=typescript)](https://www.typescriptlang.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Modern_API-009485)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## The Problem

Enterprise content processing is broken:

- **Format fragility** — Custom code is required for every content format, source, and vendor layout. A single template change can break an entire pipeline.
- **Siloed content** — Organizations sit on vast stores of PDFs, contracts, emails, transcripts, web content, and scanned records, but insights are locked inside individual files. Correlating information across sources requires manual effort or purpose-built integrations.
- **Manual data entry** — Extracting and reconciling data from heterogeneous content is expensive and error-prone (industry average: ~$12.90 per document error).
- **Rigid pipelines** — Traditional DAG-based pipelines require configuration, hard-coded field mappers, and months of engineering work to integrate a new content source or format.
- **No cross-content reasoning** — Even when extraction works, pipelines process files in isolation. Spotting trends, contradictions, or actionable patterns across a corpus requires a separate analytics layer that rarely exists.
- **Opaque decision-making** — When something goes wrong, there is no clear trail of *why* a field was mapped, a value was chosen, or an error was ignored.

## The Solution

Users describe their needs in **plain English**. The Copilot agent reasons about what to do, ingests content from any source and format, understands data semantically (knows that "Invoice Total" = "Grand Total" = "Amount Due"), correlates information across multiple sources, and delivers structured intelligence to any destination.

**No pipeline configuration. No IT tickets. No redeployment.**

| Aspect | Traditional Pipeline | Contelligence |
|--------|---------------------|---------------|
| Orchestration | DAG of executors, YAML config | LLM reasoning decides the next step |
| New content source | Code update required (weeks) | Agent adapts automatically |
| Data transformation | Hard-coded field mappers | LLM transforms by understanding meaning |
| Cross-content analysis | Not supported — files processed in isolation | Agent reasons across all ingested content |
| New format | New executor code required | Agent handles immediately |
| Error handling | Retry policies, fail flags | Agent observes failure, reasons, adapts |
| Audit trail | Limited, executor-centric | Complete: every decision, reasoning step, tool call |

---

## Typical Use Cases

### Content Extraction & Processing

| Use Case | Example Instruction |
|----------|-------------------|
| **Invoice processing** | *"Extract all invoices from the vendor folder, normalize dates and amounts, upload to the finance search index"* |
| **Multi-format ingestion** | *"Ingest the Q3 board pack — pull data from the PDF narrative, the Excel financials, the PowerPoint strategy deck, and the recorded earnings call audio — produce a unified summary"* |
| **Customer onboarding** | *"When a new customer doc arrives, extract company info, validate against the regulatory DB, create an account record"* |
| **Knowledge base building** | *"Ingest 1,000 legacy PDFs, extract and embed content, index in AI Search for semantic discovery"* |

### Multi-Content Intelligence & Deep Analysis

| Use Case | Example Instruction |
|----------|-------------------|
| **Cross-document trend analysis** | *"Analyze all vendor contracts from the past 3 years — identify pricing trends, flag terms that have become more aggressive, and surface vendors whose SLAs have degraded over time"* |
| **Competitive intelligence synthesis** | *"Ingest the last 8 quarterly earnings transcripts from our top 5 competitors, extract strategic themes, compare R&D investment signals, and produce a competitive landscape report with actionable insights"* |
| **Regulatory change impact** | *"Compare the new draft regulation against our current policy library — identify every clause that creates a compliance gap, rank by risk severity, and generate remediation action items with owners"* |
| **M&A due diligence** | *"Analyze the data room — cross-reference the financial statements, material contracts, IP filings, and litigation history to surface risks, contradictions, and items requiring further investigation"* |
| **Multi-source research synthesis** | *"Gather findings from these 30 research papers and 12 internal experiment reports — identify consensus conclusions, conflicting results, knowledge gaps, and recommended next steps"* |

### Automation & Scheduled Workflows

| Use Case | Example Instruction |
|----------|-------------------|
| **Financial close** | Scheduled nightly: *"Collect all transactions, reconcile against source documents, flag discrepancies, generate GL entries"* |
| **Contract compliance monitoring** | Scheduled weekly: *"Scan all active contracts for upcoming deadlines, expiring terms, and unmet obligations — generate an action-item report for the legal team"* |
| **QA & audit** | Scheduled weekly: *"Sample 10% of this week's processed content, validate extraction accuracy, generate a quality report with confidence scores"* |
| **Event-driven processing** | *"When a new vendor contract arrives in blob storage, extract key terms, compare against our standard template, flag deviations, and route for approval"* |

---

## Architecture

![Architecture Diagram](assets/Contelligence-deployment-architecture.jpg)

## Solution Components
![Solution Components](assets/Contelligence-solution-components.jpeg)

### Frontend — `contelligence-web`

React 18 SPA built with Vite, TypeScript, Tailwind CSS, and shadcn/ui. Ships with a chat-first UX supporting real-time SSE streaming, tool call visualization, approval workflows, and a full dashboard with session analytics, schedule management, and agent/skill authoring.

### Backend — `contelligence-agent`

FastAPI application with the GitHub Copilot SDK as the orchestration runtime. Key layers:

- **20 atomic tools** — document extraction (PDF, DOCX, XLSX, PPTX, scanned images via OCR, web scraping, audio transcription), storage and querying (Blob, Cosmos DB, AI Search), AI operations (embeddings, OpenAI calls), and agent delegation.
- **3 built-in agents** — `doc-processor` (extraction specialist), `data-analyst` (analysis and querying), `qa-reviewer` (validation and confidence scoring). Users can create additional custom agents via the web UI.
- **Skills system** — Markdown + YAML packages of domain expertise (e.g., invoice processing) with three levels of progressive disclosure. Skills are loaded into agent context on demand.
- **Scheduling engine** — APScheduler + Cosmos DB distributed locking. Supports cron, interval, Event Grid, and webhook triggers.
- **Human-in-the-loop approvals** — Destructive operations (writes, deletes, upserts) can trigger approval gates with configurable timeouts.
- **Session persistence** — Full conversation history, tool call logs, output artifacts, and metrics stored in Cosmos DB for audit and replay.

---

## Extensibility — Custom Agents & Skills

Contelligence is built around a plugin architecture that makes it easy to extend the platform's capabilities without writing code or redeploying.

### Custom Agents

Custom agents are specialized personas with a focused purpose, a restricted set of tools, and a tailored system prompt. The platform ships with three built-in agents (`doc-processor`, `data-analyst`, `qa-reviewer`), but any user can create new ones directly from the web UI:

1. **Name & description** — Give the agent an identity and purpose (e.g., "legal-contract-reviewer").
2. **System prompt** — Define the agent's personality, domain expertise, and behavioral rules in plain text.
3. **Tool subset** — Select which of the 20 platform tools the agent is allowed to use. A QA agent might only read data; an extraction agent might only access document tools.
4. **Bound skills** — Attach one or more skills that are automatically loaded into the agent's context whenever it runs.
5. **Clone & iterate** — Clone any existing agent as a starting point and customize from there.

Once saved, custom agents are immediately available in the chat agent picker and can be selected for scheduled jobs and delegated sub-tasks. The main orchestrator can also delegate work to custom agents at runtime — for example, routing a contract to a user-created "legal-reviewer" agent with domain-specific instructions.

Agents are stored in Cosmos DB, cached with a 60-second TTL for performance, and fully governed by RBAC — so each team can maintain its own library of specialists.

### Skills — Packaged Domain Expertise

Skills are self-contained knowledge packages — written in Markdown with YAML frontmatter — that inject domain expertise into agent context on demand. Think of them as reusable "playbooks" that teach the agent how to handle a specific domain.

Each skill uses a three-level progressive disclosure model:

| Level | Content | When Loaded |
|-------|---------|-------------|
| **Level 1 — Metadata** | Name, description, trigger phrases (~100 tokens) | Always visible to the agent for skill selection |
| **Level 2 — Instructions** | Full step-by-step workflow, field mappings, edge cases | Loaded when the skill is activated for a session |
| **Level 3 — Resources** | Validation schemas, templates, reference data, scripts | Loaded on demand during execution |

**Creating a skill from the web UI:**

- Use the built-in editor to author skill content inline, or upload a ZIP package containing the skill definition and any supporting assets (schemas, templates, sample data).
- Define metadata: name, description, applicable content types, trigger conditions.
- Validate the skill structure before saving.
- Export skills as ZIP packages to share across environments or teams.

**Example:** The built-in `invoice-processing` skill teaches the agent the complete invoice workflow — discover, extract, validate, normalize, output, report — along with field mappings (knows "Invoice Total" = "Grand Total" = "Amount Due"), multi-page invoice handling, credit note detection, and validation rules for amounts, dates, and tax calculations.

Skills are stored in Cosmos DB (metadata + instructions) and Blob Storage (assets). They can be bound to custom agents for automatic activation, or selected per session in the chat UI.

### How It All Fits Together

```
User creates in Web UI
        │
        ├── Custom Agent: "medical-records-analyst"
        │     ├── Tools: extract_pdf, call_doc_intelligence, query_search_index
        │     ├── Prompt: "You are a HIPAA-aware medical records specialist..."
        │     └── Bound Skill: "medical-terminology"
        │
        └── Skill: "medical-terminology"
              ├── L1: "Use for medical records, clinical notes, lab results"
              ├── L2: Field mappings, ICD-10 code handling, PHI redaction rules
              └── L3: Validation schema for required fields

At runtime
        │
        User: "Extract patient demographics from these intake forms"
        │
        Agent selects "medical-records-analyst" → loads "medical-terminology" skill
        → processes content with domain expertise → applies validation rules
        → outputs structured, compliant data
```

No code changes. No deployments. New domain expertise is live the moment you click **Save**.

---

## Prerequisites

### Azure Resources

| Resource | Purpose |
|----------|---------|
| Azure Subscription | With quota for Container Apps, Cosmos DB, AI Search, OpenAI, Document Intelligence |
| Azure AD Tenant | For Entra ID authentication and app registration |
| Azure OpenAI | GPT-4.1 deployment + `text-embedding-3-large` embedding model |
| Azure Cosmos DB | NoSQL account — session state, agents, skills, schedules, cache |
| Azure Blob Storage | Document storage, outputs, skill assets |
| Azure AI Search | Full-text, vector, hybrid, and semantic search index |
| Azure Document Intelligence | OCR and layout analysis for scanned documents |
| Azure Key Vault | Secrets management (API keys, connection strings, GitHub PAT) |
| Application Insights | Observability (traces, metrics, logs) |

### Development Tools

- **Docker** + **Docker Compose** — container orchestration for local development
- **Python 3.12+** — backend runtime
- **Node.js 20+** — frontend build
- **Azure CLI** — infrastructure provisioning and deployment
- **GitHub Personal Access Token** — with `copilot` scope (for the Copilot SDK)

---

## Getting Started

### 1. Clone the repository

```bash
git clone <repository-url>
cd contelligence
```

### 2. Local development with Docker Compose

Create `contelligence-agent/.env` with your Azure credentials (or use `azd` to provision them — see [Deployment](#deployment)):

```env
COPILOT_GITHUB_TOKEN=<your-github-pat-with-copilot-scope>
COSMOS_ENDPOINT=https://<account>.documents.azure.com:443/
COSMOS_DATABASE=contelligence
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4.1
SEARCH_ENDPOINT=https://<service>.search.windows.net
DOC_INTELLIGENCE_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
KEYVAULT_URL=https://<vault>.vault.azure.net/
APPLICATIONINSIGHTS_CONNECTION_STRING=<connection-string>
AUTH_ENABLED=false
```

Then start the local stack:

```bash
docker compose -f docker-compose.agent.yml up --build
```

| Service | Port | Description |
|---------|------|-------------|
| `contelligence-agent` | 8000 | FastAPI backend |
| `copilot-cli` | 4321 | GitHub Copilot CLI sidecar |
| `azure-mcp` | 5008 | Azure MCP Server (HTTP transport) |

### 3. Run the frontend

```bash
cd contelligence-web
npm install
npm run dev
```

The web UI is available at `http://localhost:5173` and connects to the backend at `http://localhost:8000`.

---

## Deployment

Contelligence uses the **Azure Developer CLI (`azd`)** for end-to-end provisioning and deployment. A single `azd up` command provisions all infrastructure, builds both container images, pushes them to Azure Container Registry, and deploys to Azure Container Apps.

### Prerequisites

- [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd) (`azd`) installed
- Azure CLI (`az`) authenticated to your tenant
- Docker running locally (for container builds)

### One-command deployment

```bash
azd auth login
azd up
```

`azd up` performs three steps in sequence:

1. **Provision** (`azd provision`) — deploys the Bicep templates in `infra/` to create all Azure resources
2. **Package** (`azd package`) — builds Docker images for `agent` and `web` services, pushes to ACR
3. **Deploy** (`azd deploy`) — creates new Container App revisions from the pushed images

You will be prompted for:
- **Environment name** — a unique label for this deployment (e.g., `contelligence-dev`)
- **Azure location** — the region to deploy into (e.g., `eastus2`)

### What gets provisioned

The master template ([infra/main.bicep](infra/main.bicep)) orchestrates all resources using Azure Verified Modules (AVM):

| Resource | Naming | Details |
|----------|--------|---------|
| **Container Registry** | `cr{token}` | Basic SKU — stores agent and web images |
| **Container Apps Environment** | — | Integrated with Log Analytics |
| **Agent Container App** | `contelligence-agent` | 2 CPU / 4 GiB, 1–10 replicas, sticky sessions for SSE |
| **Web Container App** | `contelligence-web` | 0.5 CPU / 1 GiB, 1–5 replicas, reverse proxy to agent |
| **Cosmos DB** | `cosmos-{token}` | NoSQL, autoscale 4,000 RU/s, 6 containers (sessions, conversation, outputs, extraction-cache, scheduler-locks, agents) |
| **Storage Account** | `st{token}` | Standard_LRS, `agent-outputs` container, lifecycle policy (Hot → Cool @ 90d → Archive @ 365d → Delete @ 730d) |
| **Azure OpenAI** | `oai-{token}` | `gpt-4.1` + `text-embedding-3-large` deployments |
| **Azure AI Search** | `search-{token}` | Basic SKU, 1 replica, 1 partition |
| **Document Intelligence** | `docintel-{token}` | FormRecognizer, S0 SKU |
| **Key Vault** | `kv-{token}` | RBAC-enabled, soft-delete 90 days, purge protection |
| **Log Analytics** | `log-{token}` | 90-day retention |
| **Application Insights** | `ai-{token}` | Connected to Log Analytics |

### RBAC — least-privilege managed identity

The agent Container App receives a **system-assigned managed identity** with only the roles it needs:

| Role | Target Service |
|------|---------------|
| ACR Pull | Container Registry |
| Storage Blob Data Contributor | Storage Account |
| Search Index Data Contributor | AI Search |
| Cognitive Services OpenAI User | Azure OpenAI |
| Cognitive Services User | Document Intelligence |
| Key Vault Secrets User | Key Vault |
| Cosmos DB Data Contributor | Cosmos DB |

No static credentials. No service principals. All service-to-service auth flows through managed identity.

### Deployment outputs

After `azd up` completes, endpoints and resource names are exported to `.azure/<env-name>/.env`:

```
API_URI=https://contelligence-agent.<region>.azurecontainerapps.io
WEB_URI=https://contelligence-web.<region>.azurecontainerapps.io
AZURE_CONTAINER_REGISTRY_ENDPOINT=cr<token>.azurecr.io
AZURE_OPENAI_ENDPOINT=https://oai-<token>.openai.azure.com/
AZURE_COSMOS_ENDPOINT=https://cosmos-<token>.documents.azure.com:443/
AZURE_KEY_VAULT_NAME=kv-<token>
```

### Other `azd` commands

```bash
azd provision   # Provision infrastructure only (no build/deploy)
azd deploy      # Build + deploy only (infrastructure must already exist)
azd down        # Tear down all provisioned resources
azd monitor     # Open Application Insights in the browser
```

### Infrastructure layout

```
infra/
├── main.bicep                    # Master orchestration — all resources
├── main.parameters.json          # Environment name + location (injected by azd)
├── bicep/
│   ├── contelligence-agent.bicep # Agent Container App (scaling, env vars, sticky sessions)
│   ├── contelligence-web.bicep   # Web Container App (nginx reverse proxy)
│   ├── contelligence-cosmos.bicep# Cosmos DB account + containers with indices/TTL
│   ├── monitoring.bicep          # Log Analytics + Application Insights
│   └── alerts.bicep              # Azure Monitor alert rules
└── modules/
    ├── keyvault.bicep            # Key Vault with purge protection
    ├── rbac.bicep                # Role assignments for managed identity
    ├── mcp_sidecar.bicep         # Azure MCP Server sidecar container
    └── copilot_cli.bicep         # Copilot CLI headless server
```

---

## Security & Enterprise Boundaries

Contelligence is designed to run entirely within your organization's Azure tenant — no data leaves your secure perimeter.

### Data Sovereignty

- **All Azure services deploy into your subscription** — Cosmos DB, Blob Storage, AI Search, OpenAI, Document Intelligence, and Key Vault are provisioned as first-party Azure resources under your control.
- **No external API calls** — the Copilot SDK communicates with Azure OpenAI inside your tenant, not a public endpoint. Document content, extracted data, and session history never leave your Azure boundary.
- **Encryption at rest and in transit** — Azure services enforce TLS 1.2+ for all traffic. Cosmos DB and Blob Storage encrypt data at rest with Microsoft-managed or customer-managed keys.

### Identity & Access

- **Azure AD / Entra ID** — JWT tokens validated against your tenant. No local user/password stores.
- **Three built-in RBAC roles** — `admin`, `operator`, `viewer` — enforced on every API endpoint.
- **Session isolation** — each session is linked to the authenticated user identity; users cannot access sessions they do not own (admins excepted).
- **Managed Identity support** — production deployments use Azure Managed Identity for service-to-service authentication, eliminating static credentials.

### Secrets Management

- **Azure Key Vault** — API keys, connection strings, and the GitHub PAT are stored in Key Vault with automatic rotation support. The application refreshes secrets every 5 minutes.
- **No secrets in code or config** — environment variables reference Key Vault; secrets are never committed to source control or baked into container images.

### Network & Infrastructure

- **Azure Container Apps** — runs inside a managed VNet. Can be further locked down with private endpoints, NSGs, and internal-only ingress.
- **Private endpoints** — Cosmos DB, Blob Storage, AI Search, Key Vault, and OpenAI all support Azure Private Link, keeping traffic on the Microsoft backbone.
- **Bicep IaC** — all infrastructure is defined as code, auditable, and deployable through CI/CD with approval gates.

### Rate Limiting & Abuse Prevention

- **Per-user token-bucket rate limiting** on OpenAI (60 RPM) and Document Intelligence (15 RPM) APIs.
- **Session quotas** — hard limits on tool calls (200), documents (100), and tokens (500,000) per session prevent runaway costs and abuse.
- **Approval gates** — destructive operations require human sign-off before execution.

---

## Testing

```bash
cd contelligence-agent
pytest
```

The test suite is organized under `tests/`:

| Directory | Scope |
|-----------|-------|
| `unit/` | Tool functions, helpers, utilities |
| `integration/` | SDK integration, connector flows |
| `behavioral/` | User story validation |
| `smoke/` | Post-deployment health checks |
| `e2e/` | Full system end-to-end flows |

Tests use `pytest` with `asyncio_mode = "auto"` for native async test support.

---

## Responsible AI

Contelligence is designed with responsible AI principles at its core:

### Transparency & Explainability

- Every tool call is logged with its parameters, result, and duration.
- Agent reasoning is persisted alongside tool calls in the conversation history.
- Users can replay any session to see exactly *why* the agent made each decision.
- The QA Reviewer agent provides explicit confidence scoring: **HIGH**, **MEDIUM**, **LOW**, or **REQUIRES_REVIEW**.

### Human Control

- **Approval gates** — Destructive operations (writes, deletes, modifications) trigger human-in-the-loop approval before execution.
- **Configurable timeouts** — Approval requests expire after 5 minutes (default) to prevent indefinite blocking.
- **User can modify** — Approvers can amend the proposed operation before approving, not just accept/reject.

### Data Integrity

- The agent reads *actual* extracted data — it does not generate or hallucinate document content.
- Field mapping is based on semantic meaning, not brittle pattern matching.
- Source documents are always referenced in outputs.
- Extraction caching (keyed by SHA-256 of blob URL + ETag) ensures deterministic results for unchanged documents.
- Agent system prompts explicitly state: **"Never fabricate data."**

### Guardrails & Abuse Prevention

- **Session quotas** — Hard limits on tool calls (200), documents (100), and tokens (500,000) per session prevent runaway loops and uncontrolled costs.
- **Scoped tool access** — Custom agents are restricted to a declared subset of tools. A `qa-reviewer` cannot write data; a `doc-processor` cannot delete records.
- **Rate limiting** — Per-user, per-API rate limits prevent abuse and protect downstream services.

### Accountability & Audit

- Every session is linked to an authenticated user identity (Entra ID).
- All actions — tool calls, approvals, delegations, errors — carry timestamps and user attribution.
- Full session audit logs are suitable for SOC 2 and compliance review workflows.
- RBAC roles enforce least-privilege access across the platform.

### Fairness & Bias Awareness

- Skills can include domain-specific bias and fairness guidance.
- The QA Reviewer agent is designed to flag anomalies and inconsistencies rather than silently accept them.
- Custom agent prompts inherit governance rules from the base system prompt.

---

## Project Structure

```
contelligence/
├── contelligence-agent/          # Python backend (FastAPI + Copilot SDK)
│   ├── app/
│   │   ├── agents/               # Custom agent definitions & delegation
│   │   ├── auth/                 # JWT / Entra ID / RBAC middleware
│   │   ├── caching/              # Extraction cache (Cosmos-backed)
│   │   ├── connectors/           # Azure service connectors (5)
│   │   ├── core/                 # Client factory, session factory, event loop
│   │   ├── mcp/                  # MCP server integration
│   │   ├── models/               # Pydantic data models
│   │   ├── observability/        # OpenTelemetry instrumentation
│   │   ├── prompts/              # System prompts & prompt templates
│   │   ├── rate_limiting/        # Token-bucket rate limiter
│   │   ├── retention/            # Data retention policies
│   │   ├── routers/              # API route handlers (9 modules)
│   │   ├── scheduling/           # APScheduler engine + leader election
│   │   ├── services/             # Core business logic
│   │   ├── skills/               # Skills manager & loader
│   │   ├── store/                # Cosmos DB data access layer
│   │   ├── tools/                # 20 atomic tools
│   │   └── utils/                # Shared utilities
│   ├── skills/                   # Built-in skill packages
│   ├── tests/                    # Test suite (unit, integration, e2e)
│   └── docs/                     # Operational documentation
├── contelligence-web/            # React frontend (Vite + TypeScript)
│   └── src/
│       ├── components/           # UI components (shadcn/ui)
│       ├── hooks/                # React hooks (SSE streaming, queries)
│       ├── pages/                # Page components (15 pages)
│       └── types/                # TypeScript type definitions
├── infra/
│   ├── bicep/                    # Azure Bicep templates
│   └── modules/                  # Shared Bicep modules
└── docker-compose.agent.yml      # Local development orchestration
```

---

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🚀 Getting Help

- **Issues**: Report bugs and request features on [GitHub Issues](../../issues)
- **Discussions**: Ask questions and share ideas in [Discussions](../../discussions)
- **Documentation**: Check our comprehensive [docs](docs/README.md)

---
