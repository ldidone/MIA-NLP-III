# Architecture

CompuFix Agents is a multi-agent system that diagnoses and assists with three
classes of common computer problems:

1. Missing Python libraries (`ModuleNotFoundError` / `ImportError`)
2. Slow network / Wi-Fi
3. High CPU/RAM resource usage

It is designed to run **fully locally and deterministically** when no LLM API
key is configured, and to optionally use an LLM when one is available.

## High-level flow

```text
user input
  -> Triage Agent        classify problem + extract entities
  -> Diagnostic Agent    retrieve docs (RAG) + grounded diagnosis
  -> Planner & Safety     build a safe action plan, mark approvals
  -> Approval check       human approves sensitive steps (Streamlit)
  -> Executor Agent      run ONLY known, controlled tools
  -> final response
```

The orchestration is implemented in two complementary ways:

- **LangGraph graph** (`graph/workflow.py::build_workflow`) with nodes
  `triage_agent -> diagnostic_agent -> planner_agent -> executor_agent`, compiled
  with a `MemorySaver` checkpointer and `interrupt_before=["executor_agent"]` so
  a human can approve before execution.
- **Deterministic helpers** (`run_analysis`, `apply_approvals`, `run_execution`,
  `run_full`) that reuse the same agent functions. The Streamlit UI uses these
  helpers so the human-in-the-loop approval is simple and explicit.

## Agents

### 1. Triage Agent (`agents/triage_agent.py`)

Hybrid classifier:

- **Rule-based** (always available): regex extracts the missing module from
  `No module named '<x>'`; keyword scoring (English + Spanish) distinguishes
  network vs. resource problems.
- **LLM-based** (optional): used only when an API key is configured; falls back
  to rules on any error.

Returns a `TriageResult` (`problem_type`, `confidence`, `extracted_entities`,
`requires_retrieval`, `requires_system_tools`).

### 2. RAG Diagnostic Agent (`agents/diagnostic_agent.py` + `rag/`)

- Retrieves relevant chunks from the local knowledge base
  (`data/raw/knowledge_base/*.md`).
- Retrieval has two backends behind one interface
  (`rag/retriever.py::retrieve_relevant_docs`):
  - **Chroma vector store** when embeddings + an API key are available.
  - **Keyword fallback** (dependency-free, EN/ES stopwords) otherwise — this is
    what makes the MVP work offline.
- Produces a `DiagnosisResult` (`diagnosis`, `evidence`, `recommended_next_step`,
  `retrieved_docs`). The deterministic templates quote the retrieved docs and do
  **not** invent procedures; the optional LLM path is constrained to the
  retrieved context.

### 3. Planner & Safety Agent (`agents/planner_agent.py`)

Deterministic plan templates per problem type:

| Problem type           | Plan                                                       |
| ---------------------- | ---------------------------------------------------------- |
| python_missing_library | check → install (approval) → verify import                 |
| network_slow           | get current → list available → switch (approval, if better)|
| high_resource_usage    | list top processes → kill (approval, dry-run, if PID known)|

A final `_enforce_safety` pass drops any unknown tool, and forces the approval
flag and risk level from the shared registry. There is no path for an LLM to
introduce arbitrary tools.

### 4. Executor Agent (`agents/executor_agent.py`)

Three gates per step:

1. **Allowlist** — unknown tools are skipped (`SKIPPED_UNKNOWN_TOOL`).
2. **Approval** — sensitive steps without approval are skipped
   (`SKIPPED_NOT_APPROVED`).
3. **Execute** — calls the registered Python callable with the planned kwargs.

The executor never builds or runs arbitrary shell commands.

## Shared tool registry (`tools/registry.py`)

Single source of truth used by both the planner and the executor:

- `TOOL_REGISTRY`: name → callable allowlist.
- `SENSITIVE_TOOLS`: `install_python_package`, `switch_network`, `kill_process`.
- `is_known_tool`, `is_sensitive_tool` (unknown ⇒ sensitive, fail-safe),
  `risk_for`.

## Controlled tools (`tools/`)

| Tool                     | Module               | Side effects                         |
| ------------------------ | -------------------- | ------------------------------------ |
| `check_python_package`   | python_env_tools     | read-only                            |
| `install_python_package` | python_env_tools     | `sys.executable -m pip install`      |
| `verify_python_import`   | python_env_tools     | read-only (subprocess import)        |
| `get_current_network`    | network_tools        | read-only (mocked)                   |
| `list_available_networks`| network_tools        | read-only (mocked)                   |
| `switch_network`         | network_tools        | mutates in-memory mock only          |
| `list_top_processes`     | process_tools        | read-only (real, via psutil)         |
| `kill_process`           | process_tools        | dry-run by default; gated + protected|

## Data models (`schemas/`)

`TriageResult`, `DiagnosisResult` (+ `RetrievedDoc`), `ActionPlan` (+ `PlanStep`,
`RiskLevel`), `ExecutionResult` (+ `StepExecutionResult`, `StepStatus`), and the
aggregate `AgentState` (`graph/state.py`).

## Configuration (`config.py`)

Environment-driven `Settings`: `OPENAI_API_KEY`, `LLM_PROVIDER`,
`VECTORSTORE_PATH`, `ALLOW_REAL_PROCESS_KILL`. `llm_enabled` is true only when an
API key is present.

## Module map

```text
src/compufix_agents/
  agents/      triage, diagnostic, planner, executor
  graph/       state (AgentState), workflow (LangGraph + helpers)
  rag/         ingest, vectorstore, retriever
  tools/       python_env_tools, network_tools, process_tools, registry
  schemas/     triage, diagnosis, plan, execution
  prompts/     triage, diagnostic, planner prompts
  config.py, logging_config.py
app/streamlit_app.py
eval/run_eval.py, eval/test_cases.json
```
