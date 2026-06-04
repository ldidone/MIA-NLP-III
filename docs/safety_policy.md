# Safety Policy

CompuFix Agents can take actions that affect the user's machine. The system is
built so that **no irreversible or dangerous action happens without explicit
human approval**, and several actions are simulated in the MVP. This document
explains the policy and how it is enforced in code.

## Principles

1. **Human-in-the-loop for sensitive actions.** The agents may *propose* actions,
   but a human must approve anything that changes the system.
2. **Least privilege.** The executor can only call a fixed allowlist of Python
   callables. It cannot run arbitrary commands.
3. **Fail-safe defaults.** If a tool's risk is unclear, it is treated as
   sensitive and requires approval. Process killing defaults to dry-run.
4. **Determinism without an LLM.** The default path is rule/template based, so
   behavior is predictable and auditable.

## Actions that require approval

| Action                   | Tool                     | Why                                  |
| ------------------------ | ------------------------ | ------------------------------------ |
| Install a Python package | `install_python_package` | Mutates the environment.             |
| Switch Wi-Fi network     | `switch_network`         | Changes system/network configuration.|
| Terminate a process      | `kill_process`           | Can cause data loss / instability.   |

These are defined in `tools/registry.py::SENSITIVE_TOOLS`. The planner sets
`requires_approval=True` for them, and the executor **skips** any sensitive step
that is not explicitly approved (`StepStatus.SKIPPED_NOT_APPROVED`).

Read-only diagnostics (`check_python_package`, `verify_python_import`,
`get_current_network`, `list_available_networks`, `list_top_processes`) never
require approval.

## Actions that are blocked entirely

- **Arbitrary shell command execution.** The executor only calls functions in
  `TOOL_REGISTRY` with planned keyword arguments. There is no "run this command"
  tool, and the LLM cannot inject one — the planner's `_enforce_safety` pass
  drops any tool name not in the registry.
- **Deleting files.** There is no file-deletion tool.
- **Modifying real system/network settings.** Network tools are fully mocked in
  the MVP; `switch_network` only mutates in-memory state.
- **Killing critical/system processes.** `process_tools.PROTECTED_PROCESS_NAMES`
  (e.g. `launchd`, `systemd`, `kernel_task`, `WindowServer`, `csrss.exe`) and
  PIDs `0`/`1`/the tool's own PID are always protected.

## Why arbitrary shell commands are not allowed

An LLM-generated shell command is an arbitrary, high-privilege action with no
reliable way to bound its effects (it could delete files, exfiltrate data, or
break the system). By restricting execution to a small set of audited,
purpose-built Python functions:

- the set of possible effects is known and reviewable,
- each tool can enforce its own safeguards (timeouts, dry-run, protected lists),
- and every call is logged.

## Process killing specifics

`kill_process(pid, dry_run=True)`:

- defaults to **dry-run** (reports what would happen, kills nothing);
- requires `ALLOW_REAL_PROCESS_KILL=true` in the environment to ever really
  terminate a process;
- still requires explicit user approval even when real killing is enabled;
- refuses to kill protected/critical processes and the tool's own process.

## Logging / auditability

All tools and agents log through `logging_config.get_logger`, so every tool call
and decision (including refusals and skips) produces an audit trail.

## Summary table

| Capability                        | Status in MVP                          |
| --------------------------------- | -------------------------------------- |
| Install package                   | Allowed **with approval**              |
| Switch network                    | **Simulated**, with approval           |
| Kill process                      | **Dry-run** by default, gated, approval|
| Read-only diagnostics             | Allowed, no approval                   |
| Arbitrary shell commands          | **Blocked**                            |
| Deleting files                    | **Blocked**                            |
| Killing critical processes        | **Blocked**                            |
