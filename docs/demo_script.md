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

In the sidebar you should see **Mode: Deterministic (no API key)** and a
**🔐 Security & execution** panel that lets you choose how CompuFix may act:

- **Python packages** — *Don't install* (default), *Install into a virtual
  environment*, or *Install into the current interpreter*.
- **Processes** — *Simulated* (default) or *Real*.
- **Network** — *Simulated switch* (default) or *Don't change my network*.

The sidebar also has clickable example inputs. Each option defaults to the
safest choice, so nothing touches your machine until you opt in.

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

**Security preference demo:** in the sidebar, switch **Python packages** to
*Install into a virtual environment*, approve step 2, and execute — CompuFix
creates `.venv` if needed, installs `opencv-python` there, and verifies the
import against that environment. Switch it back to *Don't install* to show the
tool returning the manual `pip install` command instead of touching anything.

Click **▶️ Execute approved actions** and review the per-step results and the
final answer.

---

## Use case 2 — Slow network

**Input:**

```text
My internet is very slow
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
(`"Switched to 'Home_5G' (simulated)"`); no real OS setting changes. Set
**Network** to *Don't change my network* in the sidebar to show the switch being
skipped entirely with a message telling the user how to do it manually.

---

## Use case 3 — High resource usage

**Input:**

```text
My computer is slow and using a lot of RAM
```

Click **🔍 Analyze problem**. Expect:

1. **Detected problem**: `high_resource_usage`.
2. **Diagnosis**: high CPU/RAM caused by one or more processes, citing
   `system/high_cpu_usage.md` / `system/high_memory_usage.md`.
3. **Action plan**:
   - Step 1 `list_top_processes(limit=5)` — no approval.

Click **▶️ Execute approved actions** to show the top processes. With
**Processes** set to *Real* (sidebar) these come from `psutil`; with the default
*Simulated* setting a deterministic mock list is shown and no real process is
inspected. Note that `kill_process` is **not** in the plan unless a specific PID
is suspected, and it would default to **dry-run** with approval required.

**Talking point:** mention the layered safety — the *Simulated* process mode, the
`ALLOW_REAL_PROCESS_KILL=false` config flag, and the protected process list
(`launchd`, `systemd`, `WindowServer`, ...).

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
