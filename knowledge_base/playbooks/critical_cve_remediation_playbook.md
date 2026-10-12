# Playbook: Critical CVE Triage & Remediation

- **Playbook ID:** SEC-PB-005
- **Severity Trigger:** CVSS >= 9.0 or Actively Exploited In The Wild (CISA KEV)
- **Scope:** Zero-Day and Critical Known Vulnerabilities (e.g., Log4Shell, Spring4Shell)

## Phase 1: Vulnerability Assessment & Exposure Mapping
1. **NIST NVD Metrics Review:**
   - Confirm CVSS v3.1 vector: Check Attack Vector (Network), Attack Complexity (Low), Privileges Required (None), User Interaction (None).
   - Check CISA Known Exploited Vulnerabilities (KEV) catalog status.
2. **Exposure & Shodan Reconnaissance:**
   - Correlate external attack surface: query Shodan/Censys for organizational public IPs running vulnerable service banners or exposed ports.
   - Run software bill of materials (SBOM) and dependency scans (`trivy`, `syft`, `dependency-check`) across repository assets.

## Phase 2: Immediate Mitigation (Within 4 Hours)
1. **WAF Virtual Patching:**
   - Apply vendor or OWASP ModSecurity / Cloudflare WAF signature rules to block payload patterns in HTTP headers and request bodies.
2. **Network Perimeter Cloaking:**
   - Restrict public access to vulnerable endpoints by requiring internal corporate VPN or IP whitelist.
3. **Egress Blackholing:**
   - Block unexpected outbound protocols (such as LDAP port 389/636 and RMI port 1099) used in second-stage exploitation chains.

## Phase 3: Patching & Verification (Within 24 Hours)
1. Deploy vendor security patch or upgrade package in staging environment and run regression tests.
2. Execute automated canary deployment to production.
3. Verify mitigation: run safe vulnerability validation scanning or reproduce proof-of-concept in an isolated test harness to confirm payload rejection.
