# CLAUDE.md - Project Brain: Agent Tracing & Evaluation Tool

## 1. Tech Stack Declaration
- **Language:** Python 3.11+
- **Core Frameworks & Libraries:** 
  - FastAPI (REST API / Control Plane)
  - OpenTelemetry SDK (`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-*`)
  - Pydantic v2 (Data validation & schemas)
  - SQLAlchemy + PostgreSQL with JSONB (Trace & Eval storage)
  - Pytest & Pytest-Asyncio (Testing suite)
- **Asynchronous Processing:** `asyncio`, `httpx`

---

## 2. Universal Conventions & Architecture
- **Modular Architecture:** Separate concerns cleanly into layers:
  - `collector/`: OpenTelemetry span processors and ingestion endpoints.
  - `storage/`: Database models, migrations (Alembic), and repository query patterns.
  - `evals/`: LLM-as-a-judge orchestrator and deterministic assertion checkers (JSON schema, regex, tool-selection accuracy).
- **Error Handling:** 
  - Never swallow errors silently. Explicitly catch known exceptions, log with structured context, and raise descriptive custom exceptions or return structured error models.
  - No empty `except:` blocks or returning empty arrays/objects to mask failures.
- **Typing & Validation:** All function signatures must have complete type hints. Use Pydantic models for all API inputs/outputs and configuration schemas.

---

## 3. Behavioral Rules for Claude
- **Modify Existing Files First:** Always look for existing files to modify before creating new ones. Never generate duplicate service files or suffix files with `-v2` unless explicitly instructed.
- **Verify Before Complete:** Never claim a feature or test is "complete" until you have successfully run the test suite and verified output. 
- **No Hallucinated Imports/APIs:** Ensure OpenTelemetry and evaluation metrics match stable versions of their respective SDK specs. Do not guess deprecated methods.

---

## 4. Common Development Commands
- **Run Tests:** `poetry run pytest -v`
- **Run Linting & Formatting:** `poetry run ruff check .` and `poetry run ruff format .`
- **Type Checking:** `poetry run mypy src/`
- **Database Migrations:** `poetry run alembic upgrade head`
- **Start Local Server:** `poetry run uvicorn src.main:app --reload`