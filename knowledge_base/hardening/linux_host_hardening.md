# Linux Host Hardening Guide

- **Category:** Infrastructure Hardening
- **Target OS:** Ubuntu, Debian, RHEL, Rocky Linux, Alpine
- **Scope:** Host Configuration, Remote Access, System Services

## Baseline Hardening Measures

### 1. SSH Hardening (`/etc/ssh/sshd_config`)
Remote administrative access is the primary vector for brute-force and credential abuse:
- Disable root login: `PermitRootLogin no`
- Disable password authentication: `PasswordAuthentication no`
- Enforce public-key authentication: `PubkeyAuthentication yes`
- Set idle timeout interval: `ClientAliveInterval 300` and `ClientAliveCountMax 2`
- Limit allowed ciphers and MACs to modern cryptographic standards (e.g., `chacha20-poly1305@openssh.com`, `curve25519-sha256`).

### 2. Host Firewall (UFW / Nftables)
Maintain a strict **default-deny** ingress posture:
```bash
# UFW Example
ufw default deny incoming
ufw default allow outgoing
ufw allow proto tcp from <TRUSTED_ADMIN_CIDR> to any port 22
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

### 3. Service Minimization
- Audit running services with `systemctl list-units --type=service --state=running`.
- Disable and remove legacy or unneeded services (e.g. `rpcbind`, `cups`, `telnet`, `ftp`, `avahi-daemon`).
- Ensure databases (PostgreSQL, MySQL, Redis, MongoDB) bind strictly to `127.0.0.1` or internal private VPC interfaces, never to `0.0.0.0`.

### 4. Automatic Security Updates
- Configure `unattended-upgrades` on Debian/Ubuntu or `dnf-automatic` on RHEL to apply critical security patches automatically within 24 hours of vendor release.
