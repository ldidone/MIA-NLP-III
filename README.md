# CompuFix Agents

A multi-agent system that **diagnoses and assists with common computer usage problems**.
Built for the *Natural Language Processing III* course as an MVP.

> ⚠️ This is an MVP focused on **safety**. Sensitive actions (installing packages,
> killing processes, switching networks) always require **explicit user approval**,
> and several of them are **simulated** rather than performed against the real OS.

## What it does

The system handles three use cases:

1. **Missing Python libraries** — detects errors like
   `ModuleNotFoundError: No module named 'cv2'`, maps the import name to the
   correct pip package (`cv2 -> opencv-python`), proposes a fix, asks for
   approval, installs, and verifies the import.
2. **Network slowness** — analyzes a *simulated* network state and recommends
   switching from a slower 2.4GHz Wi-Fi to a faster 5GHz Wi-Fi (mocked).
3. **High resource usage** — lists the top CPU/RAM consuming processes using
   `psutil` and, with explicit approval, can terminate one (dry-run by default).

## Architecture (overview)

```text
user input
  -> Triage Agent        (classify problem + extract entities)
  -> Diagnostic Agent    (RAG over local knowledge base)
  -> Planner & Safety    (build safe action plan, mark approvals)
  -> Approval check       (human approves sensitive steps)
  -> Executor Agent      (runs ONLY known, controlled tools)
  -> final response
```

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/safety_policy.md`](docs/safety_policy.md) for details.

## Project layout

This project follows a structure inspired by *Cookiecutter Data Science*.
Source code lives under `src/compufix_agents/`, the knowledge base under
`data/raw/knowledge_base/`, the UI under `app/`, tests under `tests/`, and
evaluation under `eval/`.

## Quickstart

> **Python version:** use **3.11 or 3.12**. The pinned LangChain 0.3 stack
> requires `numpy < 2.0`, which has no wheels for Python 3.13.

```bash
# 1. Create and activate a virtual environment (Python 3.11 or 3.12)
python3.12 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# Optional: offline semantic retrieval (local embeddings, no API key)
pip install -e ".[local]"

# 3. Copy environment template and edit as needed
cp .env.example .env

# 4. (later) Ingest the knowledge base into the vector store
python -m compufix_agents.rag.ingest

# 5. (later) Run the Streamlit UI
streamlit run app/streamlit_app.py
```

## Environment variables

| Variable                  | Default            | Description                                          |
| ------------------------- | ------------------ | ---------------------------------------------------- |
| `OPENAI_API_KEY`          | *(empty)*          | Optional. Enables LLM-backed paths. Falls back to deterministic logic when absent. |
| `LLM_PROVIDER`            | `openai`           | LLM provider identifier.                             |
| `VECTORSTORE_PATH`        | `data/vectorstore` | Where the vector store is persisted.                 |
| `ALLOW_REAL_PROCESS_KILL` | `false`            | If `true`, real process kills are *possible* (still require approval). |
| `EMBEDDING_BACKEND`       | `auto`             | `auto` / `openai` / `local` / `none`. Selects embeddings for semantic retrieval; `none` forces the keyword fallback. |
| `LOCAL_EMBEDDING_MODEL`   | `sentence-transformers/all-MiniLM-L6-v2` | Model used when `EMBEDDING_BACKEND` resolves to `local`. |

## Ingesting the knowledge base

```bash
python -m compufix_agents.rag.ingest
```

- With an `OPENAI_API_KEY` (and `langchain-openai` installed), this builds and
  persists a **Chroma** vector store under `VECTORSTORE_PATH`.
- Without a key, ingestion reports the document/chunk counts and the system uses
  the **deterministic keyword retriever** — no action required.

## Running the app

```bash
streamlit run app/streamlit_app.py
```

The UI lets you analyze a problem, review the diagnosis and proposed plan,
approve sensitive steps individually, then execute and view results. Example
inputs are available in the sidebar.

### Security & execution preferences

Beyond per-step approval, the sidebar asks **how** CompuFix is allowed to act on
your machine. Each group defaults to the safest option:

| Group           | Options                                                                                                           |
| --------------- | --------------------------------------------------------------------------------------------------------------- |
| Python packages | **Don't install** (just show the command) · **Install into a virtual environment** (created automatically if missing) · **Install into the current interpreter** |
| Processes       | **Simulated** (never touch real processes) · **Real** (psutil listing; kills stay dry-run + approval gated)       |
| Network         | **Simulated switch** (demo) · **Don't change my network**                                                         |

These choices are stored as runtime preferences
(`compufix_agents.tools.runtime.RuntimePreferences`) and applied before any plan
runs. When you pick the virtual-environment option, CompuFix runs
`python -m venv` for you if the folder doesn't exist and installs/verifies the
package against that environment's interpreter. See
[`docs/safety_policy.md`](docs/safety_policy.md) for details.

## Running tests

```bash
pytest
```

Tests cover the import→package mapping, triage classification, mocked network
tools, real process listing + safe killing, planner safety rules, executor
allowlist/approval enforcement, and the end-to-end workflow.

## Running the evaluation

```bash
python eval/run_eval.py            # pretty table
python eval/run_eval.py --json     # machine-readable report
```

Reports triage accuracy, expected-tool coverage, approval-decision accuracy, and
package-mapping accuracy over `eval/test_cases.json`. Exits non-zero if triage
accuracy drops below 80%.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — agents, workflow, tools, schemas.
- [`docs/safety_policy.md`](docs/safety_policy.md) — approvals, blocked actions, rationale.
- [`docs/demo_script.md`](docs/demo_script.md) — step-by-step demo of the three use cases.

## Limitations

- Network tools are **fully simulated**; no real OS network settings are read or
  changed.
- Real process killing is disabled by default (`ALLOW_REAL_PROCESS_KILL=false`)
  and always requires approval even when enabled.
- The default (no-API-key) triage and diagnosis are rule/template based; they
  cover the three target use cases but are not general-purpose.
- The keyword retriever is a lexical fallback, not semantic search; quality
  improves with the Chroma + embeddings path.
- Package installation targets whatever you choose in the sidebar (the current
  interpreter, a dedicated virtual environment, or nothing at all); when it does
  install, results depend on network access and PyPI availability.

## Future work

- Real (opt-in, sandboxed) network inspection and switching per OS.
- Semantic retrieval by default (local embeddings) and richer knowledge base.
- LLM-assisted planning constrained to the tool allowlist.
- More problem categories (disk space, driver issues, DNS, etc.).
- Persisted audit log and a proper approval queue in the LangGraph checkpointer.

## Development

```bash
pytest            # run tests
ruff check .      # lint
```

The system is designed to run **fully locally and deterministically** when no
LLM API key is configured.
