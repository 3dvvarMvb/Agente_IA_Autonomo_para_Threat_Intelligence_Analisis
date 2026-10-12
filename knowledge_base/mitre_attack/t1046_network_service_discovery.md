# MITRE ATT&CK Technique T1046: Network Service Discovery

- **Technique ID:** T1046
- **Tactic:** Discovery (TA0007)
- **Platforms:** Linux, Windows, macOS, Network

## Description
Adversaries may attempt to get a listing of services running on remote hosts and local network systems, including ports, protocols, application versions, and service banners. This reconnaissance enables adversaries to identify vulnerable services, unauthenticated management portals (Redis, Elasticsearch, Kubernetes API, SSH, RDP), and exploitable endpoints.

Public search engines such as **Shodan**, Censys, and ZoomEye allow threat actors to perform passive discovery of exposed organizational assets and unpatched CVEs without sending active scan packets directly to the victim network.

## Observable Telemetry & Indicators
- High rate of TCP SYN packets across multiple ports originating from external scanning nodes or cloud providers.
- Shodan telemetry indexing exposed non-standard ports (e.g., 8080, 8443, 9200, 6379, 2375) or sensitive administrative consoles.
- Banner leaks revealing precise software names and unpatched patch versions (e.g., `Apache/2.4.49`, `OpenSSH_7.4p1`).

## Actionable Mitigations
1. **Attack Surface Reduction:** Close or block all ports that do not require public Internet ingress. Put internal admin interfaces behind VPN, zero-trust network access (ZTNA), or bastion hosts.
2. **Banner Masking:** Disable or sanitize server version banners (e.g. `ServerTokens Prod` in Apache, `server_tokens off` in Nginx).
3. **Firewall Ingress Rules:** Enforce strict default-deny firewall policies for all ingress network ports on public cloud security groups and host firewalls.
