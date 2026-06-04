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

```bash
# 1. Create and activate a virtual environment (Python 3.11+)
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

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

## Development

```bash
pytest            # run tests
ruff check .      # lint
```

## Status

🚧 MVP in progress. See the task breakdown in the project brief.
The system is designed to run **fully locally and deterministically** when no
LLM API key is configured.
