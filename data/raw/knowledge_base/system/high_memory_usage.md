# High memory (RAM) usage

## Symptom

The computer is slow and consumes a lot of RAM ("consume mucha RAM",
"high memory", "out of memory"). The system may be swapping heavily.

## Diagnosis

1. List the **top processes by memory usage** (resident memory / RSS).
2. Identify processes with unexpectedly large memory footprints (e.g. a browser
   with many tabs, a leaking application).
3. Distinguish expected heavy users (IDEs, browsers, VMs) from runaway leaks.

## Recommended fix

1. Review the top memory consumers with a read-only listing tool (safe, no
   approval needed).
2. Closing or restarting the offending application usually frees memory.
3. If the user chooses to terminate a process, **killing requires explicit user
   approval** and should never be automatic. See `safe_process_kill.md`.

## Notes

- Listing processes is read-only and safe.
- Restarting an app is gentler than killing it and often enough.
- Do not kill critical system processes.
