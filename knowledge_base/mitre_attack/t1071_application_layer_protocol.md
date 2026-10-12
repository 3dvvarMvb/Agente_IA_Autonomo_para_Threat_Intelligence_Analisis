# MITRE ATT&CK Technique T1071: Application Layer Protocol

- **Technique ID:** T1071
- **Tactic:** Command and Control (TA0011)
- **Sub-techniques:** T1071.001 (Web Protocols: HTTP/HTTPS), T1071.004 (DNS)
- **Platforms:** Linux, Windows, macOS, Network

## Description
Adversaries may communicate using application layer protocols to avoid detection by blending in with existing network traffic. Commonly abused protocols include HTTP, HTTPS, and DNS. Command and Control (C2) frameworks such as Cobalt Strike, Sliver, and Metasploit leverage malleable C2 profiles mimicking legitimate web browsing traffic, cloud API requests, or CDN routing.

In DNS tunneling (T1071.004), adversaries encode payloads and commands inside subdomains queried against an authoritative nameserver under attacker control.

## Observable Telemetry & Indicators
- Periodic beaconing patterns (regular intervals or jittered HTTP POST/GET requests to unfamiliar external domains).
- High-volume TXT or A record DNS queries with high Shannon entropy strings (e.g., `a8f3b9c1.c2-malicious-traffic.net`).
- VirusTotal multi-vendor flags indicating C2, Cobalt Strike, or trojan dropper associations.
- Unusual User-Agent strings or requests lacking standard browser HTTP headers.

## Actionable Mitigations
1. **Network Egress Proxy & TLS Inspection:** Inspect outbound traffic to detect non-standard TLS handshakes, self-signed certificates, and suspicious URI patterns.
2. **DNS Sinkholing:** Configure corporate recursive resolvers to redirect confirmed malicious C2 domains and newly registered domains (NRDs) to internal sinkholes (0.0.0.0).
3. **Reputation Filtering:** Automatically ingest threat intelligence IoC lists and block traffic to domains and IPs flagged with high malicious ratios on VirusTotal.
4. **Host Isolation:** Immediately disconnect endpoints exhibiting beaconing behaviors from the production subnet.
