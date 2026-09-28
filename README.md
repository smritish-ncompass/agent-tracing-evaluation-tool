# Agent Tracing & Evaluation Tool

An OpenTelemetry-based control plane for tracing LLM agent runs and evaluating them with deterministic assertions and LLM-as-a-judge scoring.

Version **0.1.0** (Beta) · Python 3.11+ · MIT License

---

## Problem

LLM agents fail in ways that logs and unit tests do not capture well: a tool is selected incorrectly, a JSON payload is malformed, a response hallucinates facts, or a run quietly burns tokens. Existing observability stacks ingest generic spans; they do not understand agent semantics, and they do not score whether a run actually succeeded.

This project is a self-hosted FastAPI service that:

1. Ingests OpenTelemetry Protocol (OTLP) traces from instrumented agents.
2. Persists traces and spans in PostgreSQL (JSONB), including GenAI token usage.
3. Runs evaluation suites — JSON Schema, regex, exact match, keyword containment, tool-selection accuracy, plus LLM judges for hallucination, goal adherence, tone, and custom rubrics — against either ad-hoc test cases or stored traces.

---

## Key Features

- **OTLP HTTP ingestion** of `ExportTraceServiceRequest` payloads, converted into traces and nested spans.
- **PostgreSQL persistence** with JSONB attributes, events, links, resource attributes, and instrumentation-scope metadata.
- **GenAI semantic conventions** — extracts `gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`, and `gen_ai.usage.total_tokens` (derived when only the first two are present).
- **Deterministic metrics**: JSON Schema validation, regex match, exact match, keyword containment, tool-selection accuracy.
- **LLM-as-a-judge metrics**: hallucination detection, goal adherence, tone/style, and a custom-rubric judge. Judges call an OpenAI-compatible Chat Completions API (`response_format: json_object`, `temperature: 0.0`).
- **Eval runner** with `asyncio.Semaphore`-bounded concurrency (`EVAL_MAX_WORKERS`, default 4) and aggregated suite reports (pass rate, average score, duration).
- **Trace-backed evaluation** — reconstructs prompt/completion/context from span attributes (`gen_ai.prompt`, `gen_ai.completion`, `gen_ai.context`) and scores the stored run.
- **Async throughout** — SQLAlchemy async + `asyncpg`, FastAPI, `httpx`.
- **Alembic migrations** for the `traces` and `spans` tables.
- **In-memory SQLite tests** (`aiosqlite`) so the suite runs without a live Postgres instance.

---

## Architecture

```mermaid
flowchart LR
    Agent["Instrumented LLM Agent"] -->|"OTLP HTTP JSON<br/>POST /v1/traces/"| API

    subgraph API["FastAPI Control Plane"]
        Health["GET /health"]
        TracesIn["POST /v1/traces/"]
        TracesList["GET /v1/traces/"]
        EvalsRun["POST /v1/evals/run"]
        EvalsTrace["POST /v1/evals/trace/{trace_id}"]
    end

    TracesIn --> OTLP["OTLPService"]
    OTLP --> Repo["TraceRepository"]
    TracesList --> Repo
    Repo --> PG[("PostgreSQL<br/>traces + spans JSONB")]

    EvalsRun --> Runner["EvalRunner"]
    EvalsTrace --> Repo
    EvalsTrace --> Runner

    subgraph Metrics["Evaluation Metrics"]
        Det["Deterministic<br/>JSON Schema · Regex<br/>Exact Match · Contains<br/>Tool Selection"]
        Judge["LLM-as-a-Judge<br/>Hallucination · Goal Adherence<br/>Tone · Custom Rubric"]
    end

    Runner --> Det
    Runner --> Judge
    Judge -->|"OpenAI-compatible<br/>/chat/completions"| LLM["LLM API<br/>(gpt-4o default)"]
```

### Layers

| Layer | Package | Responsibility |
|---|---|---|
| Control plane | `agent_tracing.main` | FastAPI app, CORS, lifespan (create tables, dispose engine) |
| Collector | `agent_tracing.collector` | OTLP Pydantic models, ingestion service, `/v1/traces` router |
| Storage | `agent_tracing.storage` | SQLAlchemy ORM, Pydantic create/read schemas, async repository |
| Evals | `agent_tracing.evals` | Metric interface, deterministic + judge metrics, runner, `/v1/evals` router |
| Config / DB | `agent_tracing.config`, `agent_tracing.database` | Pydantic Settings, async engine and session factory |

---

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ (classifiers include 3.12 and 3.13) |
| API | FastAPI ≥ 0.115, Uvicorn |
| Validation | Pydantic v2, pydantic-settings |
| Database | SQLAlchemy 2 async, asyncpg, PostgreSQL JSONB (`JSON` fallback for other dialects) |
| Migrations | Alembic (async env) |
| HTTP client | httpx (LLM judge calls) |
| Schema checks | jsonschema |
| Logging (declared) | structlog is a runtime dependency; no application code currently uses it |
| OpenTelemetry (declared) | `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-proto` are listed in `pyproject.toml`; the collector implements OTLP **message shapes in Pydantic**, not the OTel SDK exporter/processor pipeline |
| Tests | pytest, pytest-asyncio (`asyncio_mode = auto`), pytest-cov, aiosqlite |
| Lint / types | Ruff (line length 100), mypy (`strict = true`) |
| Packaging | Poetry (`package-mode = false`, `src/` layout) |

---

## Project Structure

```
agent-tracing-evaluation-tool/
├── src/agent_tracing/
│   ├── __init__.py              # package version 0.1.0
│   ├── __main__.py              # python -m agent_tracing → uvicorn
│   ├── main.py                  # FastAPI app, CORS, /health, routers
│   ├── config.py                # Pydantic Settings from env / .env
│   ├── database.py              # async engine, session, Base, get_db_session
│   ├── collector/
│   │   ├── models.py            # OTLP Pydantic messages (AnyValue … ExportTraceServiceRequest)
│   │   ├── service.py           # OTLP → TraceCreate / SpanCreate
│   │   └── router.py            # POST/GET /v1/traces/
│   ├── storage/
│   │   ├── models.py            # Trace, Span ORM
│   │   ├── schemas.py           # SpanCreate, TraceCreate, SpanRead, TraceRead
│   │   └── repository.py        # async CRUD
│   └── evals/
│       ├── schemas.py           # TestCase, EvalResult, TestSuiteReport, request models
│       ├── runner.py            # EvalRunner + instantiate_metric
│       ├── router.py            # POST /v1/evals/run, POST /v1/evals/trace/{trace_id}
│       └── metrics/
│           ├── base.py          # BaseMetric ABC
│           ├── deterministic.py # JSON Schema, regex, exact match, contains, tool selection
│           └── judge.py         # Hallucination, goal adherence, tone, custom LLM judge
├── tests/
│   ├── conftest.py              # in-memory SQLite fixtures
│   ├── test_collector.py        # OTLP ingest, retrieve, token-extraction
│   └── test_evals.py            # metrics, factory, runner, trace eval
├── alembic/
│   ├── env.py                   # async Alembic env, URL from settings
│   ├── script.py.mako
│   └── versions/0001_initial.py # traces + spans tables
├── alembic.ini
├── pyproject.toml
└── CLAUDE.md
```

Not present in this repository: Dockerfiles, `docker-compose`, GitHub Actions / CI config, a CLI implementation, example scripts, or a `LICENSE` file. `pyproject.toml` declares `agent-tracing = "agent_tracing.cli:main"` and `license = {text = "MIT"}`, but `src/agent_tracing/cli.py` does not exist.

---

## How the System Works

### 1. Startup

On FastAPI lifespan start, `Base.metadata.create_all` is run against the configured database. On shutdown the engine is disposed. Alembic is the intended path for production schema management; `create_all` is a convenience for local bring-up.

### 2. Trace ingestion

```
Agent  →  POST /v1/traces/  →  OTLPService.ingest()
       →  for each ResourceSpans × ScopeSpans:
              build TraceCreate + SpanCreate[]
              extract gen_ai.usage.* token ints
              compute duration_ms from unix-nano timestamps
       →  TraceRepository.create_trace()  (flush + refresh)
       →  { received, trace_ids, status: "accepted" }
```

Span IDs accept bytes, hex strings, or ints (normalized to hex). Duplicate attribute keys are collapsed into lists. Events are keyed by event name; links are keyed by `span_id`. Spans missing `trace_id` or `span_id`, and scope-span groups with no spans, are skipped.

### 3. Evaluation

**Ad-hoc suite** (`POST /v1/evals/run`): metric configs are instantiated, then every test case is evaluated against every metric concurrently (semaphore-limited). A case passes only if **all** of its metrics pass. The suite report includes `pass_rate`, `average_score` (mean of every metric score), wall-clock `duration_ms`, and per-case results.

**Stored trace** (`POST /v1/evals/trace/{trace_id}`): the runner walks spans and reads `gen_ai.prompt`, `gen_ai.completion`, and `gen_ai.context`. Fallbacks: first span `name` for prompt; last span `status_description` or `name` for completion. That reconstructed pair is scored as a single `TestCase` named `trace_{trace_id}`.

LLM judges POST to `{LLM_BASE_URL}/chat/completions` (default `https://api.openai.com/v1`) with Bearer auth. Missing `LLM_API_KEY` returns a failed `EvalResult` (`score=0.0`) rather than raising. Scores are clamped to `[0.0, 1.0]`. If the model omits `passed`, judges treat `score >= 0.7` as pass.

---

## Installation and Prerequisites

### Prerequisites

- Python 3.11 or later
- [Poetry](https://python-poetry.org/) 2.x (build backend is `poetry-core>=2.0.0`)
- PostgreSQL for local/production persistence (tests use in-memory SQLite via `aiosqlite`)
- An OpenAI-compatible API key **only if** you run LLM-as-a-judge metrics

### Install

```bash
git clone <repository-url>
cd agent-tracing-evaluation-tool

poetry install --with dev
# or, equivalently, install optional extra:
# poetry install --extras dev
```

The package lives under `src/agent_tracing` (`packages = [{include = "agent_tracing", from = "src"}]`).

---

## Environment Variables

Settings are loaded by Pydantic Settings from the process environment and from a `.env` file (`env_file=".env"`, nested delimiter `__`).

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `agent-tracing-evaluation-tool` | Application name |
| `ENVIRONMENT` | `development` | Environment label |
| `DEBUG` | `false` | Enables SQLAlchemy `echo` and uvicorn `--reload` when running via `__main__` |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost:5432/agent_tracing` | Async SQLAlchemy URL |
| `DATABASE_POOL_SIZE` | `10` | SQLAlchemy pool size |
| `DATABASE_MAX_OVERFLOW` | `20` | SQLAlchemy max overflow |
| `OTLP_HOST` | `0.0.0.0` | Bind host for `python -m agent_tracing` |
| `OTLP_PORT` | `8080` | Bind port for `python -m agent_tracing` |
| `LLM_API_KEY` | unset | Bearer token for judge metrics |
| `LLM_MODEL` | `gpt-4o` | Chat Completions model |
| `LLM_BASE_URL` | unset → `https://api.openai.com/v1` | OpenAI-compatible base URL (no trailing slash required) |
| `LLM_TIMEOUT_SECONDS` | `60` | Judge HTTP timeout |
| `EVAL_MAX_WORKERS` | `4` | Max concurrent metric evaluations |

Example `.env`:

```env
ENVIRONMENT=development
DEBUG=false
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/agent_tracing
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
OTLP_HOST=0.0.0.0
OTLP_PORT=8080
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=60
EVAL_MAX_WORKERS=4
```

---

## Local Development Setup

1. **Install dependencies** (see above).
2. **Start PostgreSQL** and create a database, e.g. `agent_tracing`.
3. **Configure** `.env` with a matching `DATABASE_URL`.
4. **Migrate** (preferred) or let lifespan `create_all` run on first start:

   ```bash
   poetry run alembic upgrade head
   ```

5. **Run the API**:

   ```bash
   # CLAUDE.md convention
   poetry run uvicorn src.main:app --reload

   # Package entry (binds OTLP_HOST:OTLP_PORT, default 0.0.0.0:8080)
   poetry run python -m agent_tracing
   ```

   Note: `src.main:app` is the path documented in `CLAUDE.md`. The actual application object is `agent_tracing.main:app` (`src/agent_tracing/main.py`). Use the latter, or `python -m agent_tracing`.

6. **OpenAPI** is served by FastAPI at `/docs` and `/redoc` once the process is up. Health check:

   ```bash
   curl http://localhost:8080/health
   # {"status":"ok","service":"agent-tracing-evaluation-tool"}
   ```

---

## Usage Examples

### Ingest an OTLP JSON trace

```bash
curl -X POST http://localhost:8080/v1/traces/ \
  -H "Content-Type: application/json" \
  -d '{
    "resource_spans": [
      {
        "resource": {
          "attributes": [
            {"key": "service.name", "value": {"string_value": "support-agent"}}
          ]
        },
        "scope_spans": [
          {
            "scope": {"name": "agent-sdk", "version": "1.0.0"},
            "spans": [
              {
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "span_id": "00f067aa0ba902b7",
                "name": "chat",
                "kind": 1,
                "start_time_unix_nano": 1710000000000000000,
                "end_time_unix_nano": 1710000001500000000,
                "attributes": [
                  {"key": "gen_ai.operation.name", "value": {"string_value": "chat"}},
                  {"key": "gen_ai.request.model", "value": {"string_value": "gpt-4o"}},
                  {"key": "gen_ai.prompt", "value": {"string_value": "What is 2+2?"}},
                  {"key": "gen_ai.completion", "value": {"string_value": "The answer is 4."}},
                  {"key": "gen_ai.usage.prompt_tokens", "value": {"int_value": 12}},
                  {"key": "gen_ai.usage.completion_tokens", "value": {"int_value": 8}}
                ],
                "status": {"code": 1, "message": "OK"}
              }
            ]
          }
        ]
      }
    ]
  }'
```

Example response:

```json
{
  "received": 1,
  "trace_ids": ["4bf92f3577b34da6a3ce929d0e0e4736"],
  "status": "accepted"
}
```

`total_tokens` is stored as `20` because the collector derives it when prompt and completion counts are both present.

### List traces

```bash
curl "http://localhost:8080/v1/traces/?limit=100&offset=0"
```

Response shape:

```json
{
  "total": 1,
  "limit": 100,
  "offset": 0,
  "traces": [
    {
      "id": 1,
      "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
      "resource_attributes": {"service.name": "support-agent"},
      "schema_url": null,
      "span_count": 1,
      "created_at": "2026-09-22T12:00:00+00:00"
    }
  ]
}
```

### Run a deterministic evaluation suite

```bash
curl -X POST http://localhost:8080/v1/evals/run \
  -H "Content-Type: application/json" \
  -d '{
    "suite_name": "support-agent-regression",
    "test_cases": [
      {
        "name": "json-reply",
        "input_data": "Return the user as JSON",
        "output_data": "{\"name\": \"Alice\"}",
        "expected": null
      },
      {
        "name": "tool-call",
        "input_data": "Search for refund policy",
        "output_data": "{\"name\": \"search\", \"arguments\": {\"query\": \"refund policy\"}}",
        "expected": "{\"name\": \"search\", \"arguments\": {\"query\": \"refund policy\"}}"
      }
    ],
    "metrics": [
      {
        "type": "json_schema",
        "schema": {
          "type": "object",
          "properties": {"name": {"type": "string"}},
          "required": ["name"]
        }
      },
      {
        "type": "tool_selection",
        "expected_tool": "search",
        "expected_arguments": {"query": "refund policy"},
        "exact_args": false
      }
    ]
  }'
```

### Evaluate a stored trace

```bash
curl -X POST http://localhost:8080/v1/evals/trace/4bf92f3577b34da6a3ce929d0e0e4736 \
  -H "Content-Type: application/json" \
  -d '{
    "metrics": [
      {"type": "regex", "pattern": "\\\\d"},
      {"type": "contains", "keywords": ["4"], "mode": "all"}
    ]
  }'
```

### Python: run metrics in-process

```python
import asyncio
from agent_tracing.evals import EvalRunner, ExactMatchMetric, RegexMetric, TestCase

async def main() -> None:
    runner = EvalRunner(metrics=[ExactMatchMetric(), RegexMetric(pattern=r"hello")])
    report = await runner.run_suite(
        suite_name="smoke",
        test_cases=[
            TestCase(name="greet", input_data="greet", output_data="hello world", expected="hello world"),
        ],
    )
    print(report.pass_rate, report.average_score, report.duration_ms)

asyncio.run(main())
```

---

## API Documentation

Base URL defaults to `http://localhost:8080`. CORS is configured with `allow_origins=["*"]`, `allow_credentials=True`, all methods and headers.

| Method | Path | Request | Success | Notes |
|---|---|---|---|---|
| `GET` | `/health` | — | `200` `{"status":"ok","service":"agent-tracing-evaluation-tool"}` | Liveness only; does not check the database |
| `POST` | `/v1/traces/` | `ExportTraceServiceRequest` JSON body | `200` `{received, trace_ids, status}` | Failures become `500` with `Failed to ingest traces: …` |
| `GET` | `/v1/traces/` | `limit=100`, `offset=0` | `200` `{total, limit, offset, traces[]}` | Ordered by `created_at` descending |
| `POST` | `/v1/evals/run` | `TestSuiteRunRequest` | `200` `TestSuiteReport` | Invalid metric config → `400` |
| `POST` | `/v1/evals/trace/{trace_id}` | `TraceEvalRequest` | `200` `TestCaseResult` | Unknown id → `404`; bad metric config → `400` |

### OTLP request (subset of fields the collector models)

Root: `resource_spans[]` → `resource.attributes[]`, `scope_spans[]` → `scope`, `spans[]`.

Each span: `trace_id`, `span_id`, `parent_span_id`, `name`, `kind`, `start_time_unix_nano`, `end_time_unix_nano`, `attributes`, `events`, `links`, `status.{code,message}`.

`AnyValue` variants: `string_value`, `bool_value`, `int_value`, `double_value`, `array_value`, `kvlist_value`, `bytes_value`. Extra keys are forbidden (`extra="forbid"`).

The router docstring claims protobuf (`application/x-protobuf`) support. The handler is `request: ExportTraceServiceRequest = Body(...)`, so FastAPI parses **JSON**. There is no protobuf decoder in the collector.

### Metric configuration objects (`metrics[]`)

`instantiate_metric` dispatches on `type` (case-insensitive):

| `type` aliases | Class | Config keys |
|---|---|---|
| `json_schema`, `jsonschema` | `JSONSchemaMetric` | `schema` (or `expected` as a JSON Schema string at eval time) |
| `regex` | `RegexMetric` | `pattern`, `flags` (int, default 0) |
| `exact_match` | `ExactMatchMetric` | `case_sensitive` (default true), `strip_whitespace` (default true); compares against `TestCase.expected` |
| `contains`, `keywords` | `ContainsMetric` | `keywords`, `mode` (`all` \| `any`, default `all`), `case_sensitive` (default false) |
| `tool_selection`, `tool_call` | `ToolSelectionMetric` | `expected_tool`, `expected_arguments`, `exact_args` (default false). Output must be a JSON object with `name`/`tool` and `arguments`/`args`/`parameters` |
| `hallucination`, `hallucination_detection` | `HallucinationMetric` | `model`, `api_key`, `base_url` |
| `goal_adherence` | `GoalAdherenceMetric` | `model`, `api_key`, `base_url` |
| `tone`, `tone_and_style` | `ToneMetric` | `target_tone` (default `"professional, concise, and helpful"`), `model`, `api_key`, `base_url` |
| `llm_judge`, `custom_judge` | `LLMJudgeMetric` | `rubric` (default `"Evaluate quality and accuracy."`), `name` (metric display name, default `custom_llm_judge`), `model`, `api_key`, `base_url` |

Unknown `type` → `ValueError` → HTTP 400.

### CLI

`pyproject.toml` defines:

```toml
[project.scripts]
agent-tracing = "agent_tracing.cli:main"
```

`agent_tracing.cli` is not in the source tree. The working process entrypoint is `python -m agent_tracing` (`agent_tracing/__main__.py`), which runs uvicorn against `agent_tracing.main:app`.

---

## Evaluation Methodology and Metrics

Every metric implements:

```python
async def evaluate(
    input_data: str,
    output_data: str,
    expected: str | None = None,
    context: str | None = None,
    **kwargs: Any,
) -> EvalResult
```

`EvalResult` fields: `metric_name`, `passed`, `score` (`0.0–1.0`), `reasoning`, `metadata`, `execution_time_ms`.

### Deterministic

| Metric | Pass condition | Score |
|---|---|---|
| JSON Schema | `json.loads(output)` then `jsonschema.validate` | `1.0` / `0.0` |
| Regex | `re.search(pattern, output)` | `1.0` / `0.0`; `metadata.matched_text` on hit |
| Exact match | optional strip + optional case-fold, then `==` | `1.0` / `0.0` |
| Contains | `all` or `any` keyword membership | `all`: `matched / total`; `any`: `1.0` or `0.0` |
| Tool selection | parsed tool name equals expected; optional arg subset or exact dict | name miss `0.0`; name hit / args miss `0.5`; both `1.0` |

Invalid JSON, invalid regex, missing schema/pattern/expected/keywords/tool name all fail with `score=0.0` and an explicit `reasoning` string. Errors are not swallowed.

### LLM-as-a-judge

Judges share `BaseLLMJudge._call_llm`:

- System + user messages, `response_format: {"type": "json_object"}`, `temperature: 0.0`.
- Expected JSON keys: `passed` (bool), `score` (float), `reasoning` (string).
- Default pass threshold when `passed` is absent: `score >= 0.7`.

| Metric | What the judge is asked to score |
|---|---|
| Hallucination | Factual claims must be supported by `context` or `expected` (fallback: `"No reference context provided."`). `1.0` = fully faithful |
| Goal adherence | Whether the output accomplishes the user request (`input_data`), optionally vs `expected` |
| Tone | Alignment with `target_tone` or `expected` |
| Custom judge | Arbitrary `rubric` string |

HTTP/parse failures become `passed=False`, `score=0.0`, `reasoning="LLM judge API call failed: …"`.

### Suite aggregation

- Case pass = every metric passed.
- `pass_rate = passed_cases / total_cases` (empty suite → `1.0`).
- `average_score` = mean of **all** metric scores across cases (no scores → `1.0`).
- Rates/scores rounded to 4 decimal places; `duration_ms` to 2.

---

## Testing Instructions

Tests use `sqlite+aiosqlite:///:memory:` (`tests/conftest.py`). Tables are created and dropped per `db_session` fixture. LLM judges are mocked with `httpx.AsyncClient`.

```bash
# full suite (project convention)
poetry run pytest -v

# coverage (pytest-cov is a dev extra; config in pyproject.toml)
poetry run pytest -v --cov=src/agent_tracing --cov-report=term-missing

# lint / format
poetry run ruff check .
poetry run ruff format .

# type check
poetry run mypy src/
```

`pyproject.toml` sets `testpaths = ["tests"]`, `pythonpath = ["src"]`, `asyncio_mode = auto`.

Covered today:

- Collector: ingest returns trace IDs; retrieve by `trace_id`; token attributes with null `AnyValue` stay `None`.
- Deterministic metrics: valid/invalid JSON, schema violations, regex hit/miss/invalid pattern, exact match (case, whitespace, missing expected), contains (`all`/`any`/case/missing), tool selection (name, partial args, exact-args mismatch).
- Judges: missing API key; mocked success for hallucination, goal adherence, tone, custom rubric.
- `instantiate_metric` for every known type plus unknown-type `ValueError`.
- `EvalRunner`: single case, full suite, mixed pass/fail, trace reconstruction, `max_workers=1`.

There are no HTTP-level FastAPI tests (no `TestClient` / `httpx.ASGITransport` coverage of the routers).

---

## Observability / Tracing Setup

This service is an **OTLP receiver**, not an auto-instrumented application.

**What exists**

- Ingestion of OTLP JSON `ExportTraceServiceRequest`.
- Persistence of resource attributes, span attributes/events/links, status, kind, timestamps, duration, scope name/version/attributes.
- Extraction of GenAI usage counters into first-class columns.
- Trace-eval reconstruction from `gen_ai.prompt`, `gen_ai.completion`, `gen_ai.context`.

**What does not exist**

- No OpenTelemetry SDK `TracerProvider`, span processor, or OTLP exporter is configured in application code (the OTel packages are declared but unused).
- No metrics or logs pipelines.
- No protobuf OTLP decoder despite the router description.
- `/health` does not probe PostgreSQL or the LLM API.
- `structlog` is not wired into the app.

**Suggested client-side attributes** (from `.claude/skills/otel-tracing/reference/otel-spans.md` and collector extraction):

| Attribute | Role |
|---|---|
| `gen_ai.operation.name` | `"chat"`, `"tool_call"`, or `"agent_run"` |
| `gen_ai.request.model` | Model identifier |
| `gen_ai.usage.prompt_tokens` | int |
| `gen_ai.usage.completion_tokens` | int |
| `gen_ai.usage.total_tokens` | int (optional; derived if omitted) |
| `gen_ai.prompt` | User/agent prompt — used by trace eval |
| `gen_ai.completion` | Model/agent output — used by trace eval |
| `gen_ai.context` | Retrieved/reference text — used by hallucination judge |

Point an OTLP HTTP exporter at `http://<host>:<port>/v1/traces/` with JSON encoding. The path is `/v1/traces/` (trailing slash), not the collector-default `/v1/traces`.

---

## Docker / Production Deployment

There is **no Dockerfile, docker-compose file, or CI workflow** in this repository. A production layout that matches the code would be:

1. PostgreSQL reachable via `DATABASE_URL` (`postgresql+asyncpg://…`).
2. `poetry run alembic upgrade head` (Alembic env reads `settings.database_url`; offline and async-online modes are both implemented).
3. `uvicorn agent_tracing.main:app --host 0.0.0.0 --port 8080` (or `python -m agent_tracing`).
4. Set `DEBUG=false` so SQL echo and reload stay off.
5. Supply `LLM_API_KEY` only if judge metrics will run.
6. Size `DATABASE_POOL_SIZE` / `DATABASE_MAX_OVERFLOW` and `EVAL_MAX_WORKERS` for load.

Lifespan `create_all` will create missing tables if migrations were skipped; it will not evolve an existing schema. Prefer Alembic in production.

The initial migration (`alembic/versions/0001_initial.py`, revision `0001`) creates:

- `traces`: `id`, unique indexed `trace_id` (64), JSONB `resource_attributes`, `schema_url`, timezone-aware `created_at` / `updated_at`.
- `spans`: FK `trace_id → traces.id` `ON DELETE CASCADE`, `span_id` (indexed), `parent_span_id`, `name`, `kind`, JSONB `attributes` / `events` / `links` / `metadata` / `scope_attributes`, status fields, `start_time_unix_nano` / `end_time_unix_nano` (`BigInteger`), `duration_ms`, token ints, `scope_name` / `scope_version`, `created_at`.

ORM JSON columns use `JSON().with_variant(JSONB, "postgresql")`, so SQLite tests store JSON as text.

---

## Configuration

| Area | Mechanism |
|---|---|
| Runtime | `Settings` in `src/agent_tracing/config.py` |
| Ruff | `[tool.ruff]` — py311, line length 100, rules E/W/F/I/UP/B/C4/SIM/TC/PTH; ignores E501, B008, TC004 |
| mypy | `[tool.mypy]` strict; `ignore_missing_imports` for `opentelemetry.*` and `structlog.*` |
| Alembic | `alembic.ini` + `[tool.alembic]`; URL overridden at runtime from `DATABASE_URL` |
| Pytest | `[tool.pytest.ini_options]`; `env` also sets a Postgres `DATABASE_URL` that tests **do not use** (fixtures hardcode SQLite) |
| Coverage | `[tool.coverage.run]` source `src/agent_tracing`, `branch = true` |

---

## Design Decisions and Trade-offs

| Decision | Rationale | Cost |
|---|---|---|
| Pydantic OTLP models instead of generated protobuf stubs | JSON ingestion is simple to test and validate (`extra="forbid"`) | Router advertises protobuf that is not implemented; `opentelemetry-proto` is unused |
| JSONB for attributes/events/links | Agent spans are schema-flexible | Weaker relational querying; events keyed by name overwrite duplicates |
| Token fields denormalized onto `spans` | Cheap aggregation without JSON path queries | Only `gen_ai.usage.*` ints are extracted |
| `create_all` on startup **and** Alembic | Faster local start | Two sources of truth for schema |
| SQLite in-memory tests | No Docker/Postgres required for CI-like local runs | Dialect differences (JSONB vs JSON) are not exercised in tests |
| Semaphore-bounded `asyncio.gather` | Caps concurrent judge HTTP calls | No retry, no per-metric timeout beyond `LLM_TIMEOUT_SECONDS` |
| OpenAI-compatible Chat Completions only | One HTTP client, `json_object` response format | Not Anthropic-native; providers without `json_object` will fail |
| Pass = all metrics passed | Conservative regression gate | A single failing metric fails the case |
| CORS `allow_origins=["*"]` with credentials | Convenient local UI/dev | Unsafe default for a public deployment |
| Repository `delete_trace` / `get_trace_by_pk` | Complete CRUD internally | No HTTP endpoints expose delete or get-by-id (list + ingest only) |
| Unique `traces.trace_id` | One row per OTLP trace id | Re-ingesting the same id will error at flush (not upserted) |

---

## Security Considerations

- **No authentication or authorization** on any route, including ingest and eval.
- **CORS** allows any origin with credentials.
- **Secrets**: `LLM_API_KEY` is read from the environment; `.claude/settings.json` denies the Claude Code agent from reading `./.env`.
- **SQL**: queries use SQLAlchemy bound parameters; user JSON is stored, not interpolated into SQL.
- **SSRF / egress**: judge metrics call whatever `LLM_BASE_URL` (or per-request `base_url`) is configured — treat that as a trusted setting.
- **Resource use**: `EVAL_MAX_WORKERS` bounds concurrency but there is no request-size limit, auth quota, or ingest payload cap beyond FastAPI defaults.
- **Error payloads**: ingest `500` responses include `str(exc)`; avoid leaking connection strings via misconfiguration.
- **Health**: `/health` does not verify DB connectivity, so a dead database still returns `ok`.

This is a **beta control-plane for trusted networks**, not a hardened multi-tenant SaaS.

---

## Limitations

- Protobuf OTLP is documented on the ingest route but not implemented.
- No `GET /v1/traces/{trace_id}`, no span-level query API, no delete API.
- Re-ingest of an existing `trace_id` is not an upsert (unique constraint).
- Duplicate span events with the same name overwrite each other.
- OpenTelemetry SDK packages are unused; the process does not emit its own traces.
- `structlog` is unused; exceptions in ingest are converted to HTTP 500 without structured logs.
- CLI script entry point is declared but missing (`agent_tracing.cli`).
- `poetry run uvicorn src.main:app --reload` (CLAUDE.md) does not match the real module path `agent_tracing.main:app`.
- No Docker, compose, or CI configuration.
- No LICENSE file, despite MIT in `pyproject.toml`.
- Judge metrics require an OpenAI-compatible JSON-mode endpoint; they fail closed without `LLM_API_KEY`.
- Trace evaluation only understands the three `gen_ai.*` string attributes listed above (plus crude name/status fallbacks).
- `ContainsMetric` in `all` mode can report `passed=False` with a fractional score; suite pass/fail uses `passed`, not the score.
- FastAPI routers are untested at the HTTP layer.
- `package-mode = false` — this is an application, not a published library, even though `[project.scripts]` is declared.

---

## Future Improvements

The following are **not implemented**; they follow directly from gaps in the current code:

- OTLP/protobuf (`application/x-protobuf`) decoder aligned with the route description.
- Implement or remove `agent_tracing.cli:main`.
- Authenticated ingest/eval (API keys or mTLS).
- Restrict CORS; make origins configurable.
- `GET /v1/traces/{trace_id}` and delete endpoints using existing repository methods.
- Upsert or append-spans behavior for duplicate `trace_id`s.
- Wire `structlog` and emit the service’s own OTel traces.
- Dockerfile / compose (API + Postgres) and a CI workflow running `pytest`, `ruff`, `mypy`.
- HTTP-level API tests.
- Retry/backoff and circuit breaking around judge calls.
- Persist `TestSuiteReport` alongside traces.
- Health check that pings PostgreSQL (and optionally the LLM base URL).

---

## Example Output

### Health

```json
{"status": "ok", "service": "agent-tracing-evaluation-tool"}
```

### Suite report (`POST /v1/evals/run`)

```json
{
  "suite_name": "support-agent-regression",
  "total_cases": 2,
  "passed_cases": 1,
  "failed_cases": 1,
  "pass_rate": 0.5,
  "average_score": 0.75,
  "results": [
    {
      "test_case_name": "json-reply",
      "passed": true,
      "metrics": [
        {
          "metric_name": "json_schema_validation",
          "passed": true,
          "score": 1.0,
          "reasoning": "Output successfully conforms to JSON Schema.",
          "metadata": {},
          "execution_time_ms": 1.23
        }
      ],
      "metadata": {}
    }
  ],
  "started_at": "2026-09-22T12:00:00+00:00",
  "completed_at": "2026-09-22T12:00:00.050000+00:00",
  "duration_ms": 50.12
}
```

### Metric failure (tool name mismatch)

```json
{
  "metric_name": "tool_selection_accuracy",
  "passed": false,
  "score": 0.0,
  "reasoning": "Selected tool 'database_query' does not match expected 'search'.",
  "metadata": {"actual_tool": "database_query", "expected_tool": "search"},
  "execution_time_ms": 0.4
}
```

---

## Development Commands (quick reference)

```bash
poetry run pytest -v
poetry run ruff check .
poetry run ruff format .
poetry run mypy src/
poetry run alembic upgrade head
poetry run python -m agent_tracing
```

---

## License

`pyproject.toml` declares **MIT**. There is no `LICENSE` file in the tree.
