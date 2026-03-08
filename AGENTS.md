# AGENTS.md

Contelligence is an AI-native, agentic content intelligence platform powered by the GitHub Copilot SDK. It replaces brittle content processing pipelines with autonomous AI agents that ingest content from any source/format, understand data by meaning, and deliver structured intelligence — all orchestrated through natural language.

## Project structure

This is a two-service monorepo deployed via Azure Developer CLI (`azd`).

- `contelligence-agent/` — Python/FastAPI backend (REST API, agent orchestration, Azure connectors)
- `contelligence-web/` — React/TypeScript frontend (SPA with Vite, Tailwind, Shadcn/ui)
- `infra/` — Azure infrastructure-as-code (Bicep)
- `docs/` — Architecture docs, specs, and plans
- `.github/skills/` — Copilot skills (code-free domain knowledge)
- `azure.yaml` — Azure Developer CLI service definitions

For backend internals, see [contelligence-agent/AGENTS.md](contelligence-agent/AGENTS.md).
For frontend internals, see [contelligence-web/AGENTS.md](contelligence-web/AGENTS.md).

## Setup commands

```bash
# Backend — install deps and start dev server
cd contelligence-agent
pip install -r requirements.txt
uvicorn main:app --reload --port 8081

# Frontend — install deps and start dev server
cd contelligence-web
npm install
npm run dev

# Full stack — Docker Compose (includes Copilot CLI + Azure MCP sidecar)
docker compose -f docker-compose.agent.yml up --build

# Deploy to Azure
azd up
```

## Testing commands

```bash
# Backend — run all tests
cd contelligence-agent && python -m pytest

# Backend — run a single test file
python -m pytest tests/unit/test_tool_registry.py

# Backend — run a single test by name
python -m pytest tests/unit/test_tool_registry.py -k "test_register_and_get_tool"

# Backend — run tests by category
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/e2e/
python -m pytest tests/behavioral/
python -m pytest tests/smoke/

# Frontend — run tests
cd contelligence-web && npm test

# Frontend — lint
cd contelligence-web && npm run lint
```

Always run relevant tests after modifying code. Use file-scoped test runs, not full suite runs.

## Code style

### Do

- Use Python 3.12+ features (type unions with `|`, match statements where appropriate)
- Use `async`/`await` throughout the backend — all I/O is async
- Use Pydantic `BaseModel` for all request/response schemas and data models
- Use FastAPI dependency injection via `Depends()` — never instantiate services in routers
- Use the connector abstraction layer (`app/connectors/`) for all Azure service calls
- Use the service layer (`app/services/`) for business logic — routers stay thin
- Use Tailwind CSS utility classes and Shadcn/ui components in the frontend
- Use React Query (`@tanstack/react-query`) for server state management
- Use `zod` schemas for frontend form validation
- Use path aliases (`@/components/...`, `@/lib/...`) in frontend imports
- Use `DefaultAzureCredential` for all Azure authentication — no hardcoded keys
- Keep components small and focused — one concern per file
- Keep diffs small and focused — avoid repo-wide rewrites unless explicitly asked
- Write tests for new code paths — prefer unit tests in `tests/unit/`
- Add or update tests when fixing bugs — add a failing test first, then fix to green

### Don't

- Don't use synchronous I/O in the backend — everything must be `async`
- Don't hardcode Azure connection strings, keys, or secrets — use environment variables via `AppSettings`
- Don't fetch data directly in React components — use React Query hooks or `lib/api.ts`
- Don't use inline styles in the frontend — use Tailwind utilities or CSS variables
- Don't add heavy new dependencies without discussion
- Don't bypass the connector/service layer to make direct Azure SDK calls from routers
- Don't use `print()` — use structured logging via the observability module
- Don't commit `.env` files, secrets, or credentials

## Domain concepts

- **Session** — a conversation between a user and the agent; has turns, tool calls, and output artifacts
- **Agent** — a configurable persona with a system prompt, tool set, and optional skills (custom agents are stored in Cosmos DB)
- **Skill** — a code-free domain knowledge package (SKILL.md format) that extends agent capabilities
- **Schedule** — a cron/interval/webhook trigger that automatically runs an agent with a given instruction
- **Tool** — an atomic capability (extract PDF, query search, store blob) registered in the tool registry
- **Connector** — an adapter for an Azure service (Blob, Cosmos, Search, Doc Intelligence, OpenAI)
- **Output artifact** — a structured result (JSON, markdown, blob URL) produced during a session
- **MCP server** — a Model Context Protocol sidecar providing Azure or GitHub tool access to the Copilot SDK
- **Approval** — a human-in-the-loop checkpoint for high-stakes agent decisions

## Environment configuration

All configuration is environment-based via Pydantic `BaseSettings` (loaded from `.env`).
See `contelligence-agent/app/settings.py` for the full list of 100+ config options.

Key groups:
- `AZURE_STORAGE_*`, `AZURE_COSMOS_*`, `AZURE_SEARCH_*` — Azure service endpoints
- `AZURE_OPENAI_*` — LLM and embedding model configuration
- `GITHUB_COPILOT_TOKEN`, `COPILOT_CLI_*` — Copilot SDK connection
- `AZURE_MCP_SERVER_URL` — MCP server mode (empty = stdio, URL = HTTP sidecar)
- `AUTH_ENABLED`, `AZURE_AD_*` — Entra ID / JWT authentication
- `SESSION_MAX_*`, `RATE_LIMIT_*` — Quotas and rate limiting
- `LOG_LEVEL` — Logging verbosity (`INFO` or `DEBUG`)

## Infrastructure

Infrastructure-as-code lives in `infra/` using Azure Bicep. Deployed via `azd up`.

Key Azure resources:
- Container Apps (agent, web, copilot-cli)
- Cosmos DB (sessions, agents, skills, cache, schedules)
- Blob Storage (documents, output artifacts)
- Azure AI Search (full-text + vector + hybrid)
- Azure OpenAI (gpt-4.1, text-embedding-3-large)
- Document Intelligence (OCR, layout analysis)
- Key Vault (secrets management)
- Application Insights (tracing, metrics, alerts)

## API design

REST API base: `/api/v1/`

Key routers:
- `agent.py` — session lifecycle (instruct, stream, reply, list, logs, outputs)
- `agents.py` — custom agent CRUD
- `skills.py` — skill CRUD and validation
- `schedules.py` — schedule CRUD, pause/resume/trigger, run history
- `dashboard.py` — metrics and aggregates
- `health.py` — service health and MCP status

All endpoints use Pydantic models for request/response validation.
SSE streaming via `EventSourceResponse` for real-time agent events.

## Safety and permissions

Allowed without prompt:
- Read files, list directories, search code
- Run single-file tests, lint, type checks
- Read environment/config files (not `.env`)

Ask first:
- Package installs (`pip install`, `npm install`)
- Git push, force push, branch deletion
- Deleting files or directories
- Running full test suites or builds
- Modifying infrastructure (Bicep) files
- Modifying Docker or deployment configuration
- Database schema changes (Cosmos container definitions)

## When stuck

- Ask a clarifying question or propose a short plan before making large speculative changes
- Check `docs/` for architecture decisions and specs
- Check `contelligence-agent/docs/` for KQL queries, MCP deployment, and RBAC setup guides
- Review existing tests in `tests/` for expected behavior patterns

## PR checklist

- Title: `feat(scope): short description` or `fix(scope): short description`
- Lint and type check: green
- Relevant tests: passing (add tests for new code paths)
- Diff: small and focused with a brief summary of what changed and why
- No secrets, credentials, or `.env` content in the diff
- No excessive logs or debug comments
