# High CPU usage / computer running slow

## Symptom

The computer feels slow, the fan is loud ("la computadora está lenta",
"el ventilador hace ruido", "high CPU"). A process may be consuming most of the
CPU.

## Diagnosis

1. List the **top processes by CPU usage** (for example, the top 5).
2. Identify whether a single process dominates CPU time.
3. Consider whether that process is expected (e.g. a build, a video encoder) or
   unexpected (e.g. a runaway script, a hung application).

## Recommended fix

1. Review the top CPU consumers with a read-only listing tool (no approval
   needed — listing is safe).
2. If a non-critical process is clearly misbehaving and the user wants to stop
   it, terminating it can free CPU.
3. **Killing a process always requires explicit user approval.** Never kill a
   process automatically. See `safe_process_kill.md`.

## Notes

- Listing processes is read-only and safe.
- Prefer closing the application normally before killing it.
- Do not kill critical system processes.
