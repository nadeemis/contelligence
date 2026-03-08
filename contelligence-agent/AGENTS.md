# AGENTS.md — contelligence-agent

Python/FastAPI backend service for the Contelligence platform. Handles agent orchestration, document processing, Azure service integration, and the REST API.

## Tech stack

- Python 3.12+, FastAPI, Uvicorn (async ASGI)
- GitHub Copilot SDK (`github-copilot-sdk`) for agent sessions and tool invocation
- Pydantic v2 for all data validation and settings
- Azure SDK: Cosmos DB, Blob Storage, AI Search, Document Intelligence, OpenAI, Key Vault
- MCP (Model Context Protocol) for Azure and GitHub tool access
- OpenTelemetry + Application Insights for observability
- APScheduler for cron/interval scheduling
- pytest with `asyncio_mode = "auto"` for testing

## Architecture layers

```
routers/        → Thin HTTP handlers (validation, auth, delegation to services)
services/       → Business logic (session orchestration, scheduling, approvals)
connectors/     → Azure service adapters (Blob, Cosmos, Search, Doc Intel, OpenAI)
tools/          → Atomic tool definitions registered in the tool registry
  extraction/   → PDF, DOCX, XLSX, PPTX extraction tools
  storage/      → Blob, Search, Cosmos CRUD tools
  ai/           → Embeddings, Document Intelligence, transcription tools
  agents/       → Sub-agent delegation, skill reading tools
  skills/       → Skill invocation and listing tools
models/         → Pydantic request/response models and custom exceptions
agents/         → Agent definitions, dynamic registry, system prompts
skills/         → Skill management (SKILL.md parsing, validation, Cosmos persistence)
store/          → Cosmos DB CRUD for sessions and agents
auth/           → JWT middleware, RBAC models, token management
caching/        → Extraction result caching (Cosmos-backed, blob_url + etag key)
scheduling/     → APScheduler engine, leader election, cron handling
rate_limiting/  → Per-session quotas, OpenAI/Doc Intel RPM limits
retention/      → TTL-based session and blob cleanup
observability/  → OpenTelemetry setup, structured logging, custom metrics
core/           → Copilot SDK client factory, session factory, event loop management
mcp/            → MCP server config (stdio vs HTTP mode) and health checks
```

## Key patterns

### Dependency injection

All services are initialized at startup and injected via `Depends()`:

```python
# dependencies.py
def get_agent_service(request: Request) -> PersistentAgentService:
    return request.app.state.agent_service

# routers/agent.py — thin router delegates to service
@router.post("/instruct")
async def instruct(
    body: InstructRequest,
    agent_service: PersistentAgentService = Depends(get_agent_service),
    user: User = Depends(get_current_user),
) -> InstructResponse:
```

### Pydantic models

Separate models for requests, responses, and persistence:

```python
class InstructRequest(BaseModel):
    instruction: str
    session_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
```

### Settings via environment

```python
class AppSettings(BaseSettings):
    AZURE_COSMOS_ENDPOINT: str = ""
    model_config = {"env_file": ".env", "extra": "ignore"}

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
```

### Tool definitions

```python
@define_tool(name="extract_pdf", description="Extract text from a PDF")
async def extract_pdf(params: ExtractPdfParams, context: dict) -> dict:
    ...
```

### Custom exceptions

```python
# models/exceptions.py — domain exceptions with structured data
class QuotaExceededError(Exception):
    def __init__(self, session_id: str, resource: str): ...

# Handled globally via FastAPI exception_handler → 429 response
```

### Startup lifecycle

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await on_startup(app)   # Initialize all connectors, services, registries
    yield
    await on_shutdown(app)  # Cleanup
```

## Good examples to follow

- Routers: `app/routers/agent.py` — clean dependency injection, thin handlers
- Services: `app/services/persistent_agent_service.py` — core orchestration pattern
- Connectors: `app/connectors/blob_connector.py` — Azure adapter abstraction
- Tools: `app/tools/extraction/` — atomic, well-scoped tool definitions
- Models: `app/models/session_models.py` — Pydantic models with enums and defaults
- Tests: `tests/unit/test_tool_registry.py` — isolated unit test pattern
- Fixtures: `tests/conftest.py` — shared sample data factories

## Patterns to avoid

- `app/` files with `# TODO` or `# FIXME` — address these rather than copying the pattern
- Direct Azure SDK calls outside of connectors — always use the connector layer
- Synchronous blocking calls — the entire backend is async
- `print()` statements — use structured logging via `app/observability/`

## Testing conventions

- Tests go in `tests/unit/` for isolation tests (no external services)
- Tests go in `tests/integration/` when multiple components interact
- Tests go in `tests/e2e/` for full workflow tests
- Tests go in `tests/behavioral/` for behavior-driven scenarios
- Tests go in `tests/smoke/` for quick deployment verification
- Shared fixtures live in `tests/conftest.py` — use `create_sample_session()` and friends
- All async tests run automatically — `asyncio_mode = "auto"` in pyproject.toml
- Use `unittest.mock.AsyncMock` for mocking async dependencies

```bash
# Run tests for a specific file
python -m pytest tests/unit/test_tool_registry.py -v

# Run a single test by name
python -m pytest tests/unit/test_tool_registry.py -k "test_register_and_get_tool"

# Run all unit tests
python -m pytest tests/unit/ -v
```

## API reference

Base URL: `/api/v1/`

| Router | Prefix | Purpose |
|--------|--------|---------|
| `agent.py` | `/agent` | Session lifecycle (instruct, stream, reply, list, logs, outputs) |
| `agents.py` | `/agents` | Custom agent CRUD |
| `skills.py` | `/skills` | Skill CRUD and validation |
| `schedules.py` | `/schedules` | Schedule CRUD, pause/resume/trigger, run history |
| `dashboard.py` | `/dashboard` | Metrics and aggregates |
| `health.py` | `/health` | Service health and MCP status |
| `admin.py` | `/admin` | Cache and rate-limit management |
| `events.py` | `/events` | Azure Event Grid subscriptions |
| `webhooks.py` | `/webhooks` | Inbound webhook triggers |
