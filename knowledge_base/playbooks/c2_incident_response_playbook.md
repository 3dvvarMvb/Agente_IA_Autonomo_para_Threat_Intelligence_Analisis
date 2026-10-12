# Incident Response Playbook: Command and Control (C2) Containment

- **Playbook ID:** IR-PB-002
- **Severity Trigger:** HIGH / CRITICAL
- **Threat Scenario:** Active beaconing or network communication with confirmed C2 infrastructure.

## Phase 1: Identification & Validation
1. Verify indicator maliciousness:
   - Check VirusTotal detection ratio (e.g. > 10 vendors flagging as C2/trojan).
   - Check domain creation date and Shannon entropy (look for domain generation algorithms / DGA).
   - Review firewall and proxy logs for recurring connection periodicity (beaconing jitter between 10% and 30%).
2. Identify internal source host:
   - Extract source IP, MAC address, hostname, and logged-in user from DHCP/NetFlow records.

## Phase 2: Containment (Action within 15 Minutes)
1. **Network Isolation:**
   - Execute endpoint quarantine via EDR agent or place host in isolated containment VLAN.
   - Null-route or block the external destination IP and domain on edge border routers and perimeter firewalls.
2. **DNS Sinkhole:**
   - Inject domain into DNS Response Policy Zone (RPZ) resolving to `0.0.0.0` across all corporate DNS servers.
3. **Session Revocation:**
   - Invalidate all active Kerberos, OAuth, and VPN sessions for the impacted user account.

## Phase 3: Eradication & Forensic Analysis
1. Acquire forensic artifacts:
   - Capture volatile memory dump (`volatility` / LiME / dumpit).
   - Collect process execution tree, network socket listings (`ss -tunap`), and scheduled cron/systemd jobs.
2. Terminate malicious process trees and remove persistence mechanisms (registry keys, startup scripts, unauthorized SSH keys).
3. Re-image the compromised system from a verified golden image before returning to production.
