# Demo Script

A step-by-step walkthrough of the three MVP use cases. Use it for a live demo or
to record a short video.

## Setup (once)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # no API key needed; deterministic mode works

# Optional: build the vector store (skipped automatically without an API key)
python -m compufix_agents.rag.ingest

# Launch the UI
streamlit run app/streamlit_app.py
```

In the sidebar you should see **Mode: Deterministic (no API key)** and
**Real process kill: disabled**. The sidebar also has clickable example inputs.

---

## Use case 1 — Missing Python library

**Input** (paste into the text area, or click the sidebar example):

```text
ModuleNotFoundError: No module named 'cv2'
```

Click **🔍 Analyze problem**. Expect:

1. **Detected problem**: `python_missing_library`, confidence ≈ 0.95,
   entities `{ "missing_module": "cv2", "package_name": "opencv-python" }`.
2. **Diagnosis**: explains the module is not installed and the pip name differs
   from the import name, citing `python/module_not_found.md` and
   `python/package_name_mapping.md`.
3. **Action plan**:
   - Step 1 `check_python_package(opencv-python)` — no approval.
   - Step 2 `install_python_package(opencv-python)` — **requires approval**.
   - Step 3 `verify_python_import(cv2)` — no approval.

**Talking point:** check the approval box for step 2 to demonstrate
human-in-the-loop, or leave it unchecked to show the install being **skipped**.

Click **▶️ Execute approved actions** and review the per-step results and the
final answer.

---

## Use case 2 — Slow network

**Input:**

```text
Mi internet está muy lento
```

Click **🔍 Analyze problem**. Expect:

1. **Detected problem**: `network_slow`.
2. **Diagnosis**: likely on a slow 2.4GHz band while a faster 5GHz is available,
   citing `network/slow_wifi.md` / `network/wifi_band_selection.md`.
3. **Action plan**:
   - Step 1 `get_current_network()` — no approval (shows `Home_2.4G`).
   - Step 2 `list_available_networks()` — no approval.
   - Step 3 `switch_network(Home_5G)` — **requires approval**.

**Talking point:** approve step 3 and execute — the switch is **simulated**
(`"Switched to 'Home_5G' (simulated)"`); no real OS setting changes.

---

## Use case 3 — High resource usage

**Input:**

```text
La computadora está lenta y consume mucha RAM
```

Click **🔍 Analyze problem**. Expect:

1. **Detected problem**: `high_resource_usage`.
2. **Diagnosis**: high CPU/RAM caused by one or more processes, citing
   `system/high_cpu_usage.md` / `system/high_memory_usage.md`.
3. **Action plan**:
   - Step 1 `list_top_processes(limit=5)` — no approval.

Click **▶️ Execute approved actions** to show the real top processes (via
`psutil`). Note that `kill_process` is **not** in the plan unless a specific PID
is suspected, and it would default to **dry-run** with approval required.

**Talking point:** mention `ALLOW_REAL_PROCESS_KILL=false` and the protected
process list (`launchd`, `systemd`, `WindowServer`, ...).

---

## Bonus — Command line / evaluation

Run the deterministic evaluation harness:

```bash
python eval/run_eval.py
```

Expect a table with **100%** triage accuracy, expected-tool coverage, approval
accuracy, and package mapping on the bundled test cases.

Run the test suite:

```bash
pytest
```
