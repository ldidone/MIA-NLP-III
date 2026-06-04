# Safely terminating a process

Killing a process can cause data loss and system instability. CompuFix treats it
as a **high-risk action** with strict safeguards.

## Safety rules

1. **Explicit user approval is always required** before any process is killed.
2. Killing is **dry-run by default**. The tool reports what *would* happen
   without actually terminating anything unless real killing is both:
   - enabled via configuration (`ALLOW_REAL_PROCESS_KILL=true`), AND
   - explicitly approved by the user for that specific process.
3. **Critical / system processes are protected** and must never be killed
   (for example: `systemd`, `launchd`, `kernel_task`, `WindowServer`,
   `init`, `csrss.exe`, `wininit.exe`, and the tool's own process).

## Recommended procedure

1. List the top processes (read-only, safe).
2. Identify the offending non-critical process and its PID.
3. Prefer closing the application normally first.
4. If the user still wants to terminate it:
   - Present the PID and process name.
   - Ask for explicit approval.
   - Only then attempt termination (and only if configuration allows it).

## What is never allowed

- Killing without approval.
- Killing critical/system processes.
- Killing by running arbitrary shell commands.
