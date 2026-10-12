# Network Egress & DNS Security Filtering

- **Category:** Network Defense & Boundary Protection
- **Target Systems:** Cloud Gateways, Corporate Firewalls, Recursive DNS Resolvers
- **Focus Areas:** C2 Disruption, Data Exfiltration Prevention, Outbound Filtering

## 1. Zero-Trust Egress Filtering
By default, corporate and production server environments should enforce strict egress filtering:
- Block all outbound traffic on legacy or high-risk protocols:
  - Port 389 (LDAP), 636 (LDAPS)
  - Port 1099 (RMI)
  - Port 445 (SMB), 135-139 (NetBIOS)
  - Port 23 (Telnet), 21 (FTP), 25 (SMTP relay)
- Production compute instances (database servers, backend application clusters) should have **no direct egress to the public Internet** without passing through an explicit HTTP/HTTPS forward proxy with logging and SNI inspection.

## 2. DNS Sinkholing & Filtering
- Route all DNS lookups through managed recursive resolvers with Threat Intelligence feeds (e.g. Quad9, Cloudflare 1.1.1.2, or internal BIND/PowerDNS response policy zones (RPZ)).
- Configure RPZ to rewrite resolution for high-risk domains:
  - Returns `NXDOMAIN` or points to an internal sinkhole IP (`0.0.0.0`) for known malware and Cobalt Strike C2 domains.
  - Generates immediate SOC SIEM alerts when an internal client attempts to query a sinkholed domain.
- Implement rate limiting on outbound DNS traffic per client IP to mitigate DNS tunneling exfiltration.
