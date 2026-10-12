# Java & JVM Application Security Hardening

- **Category:** Application Security Hardening
- **Target Platforms:** OpenJDK 11, 17, 21, Spring Boot, Quarkus, Micronaut
- **Focus Areas:** Dependency Vulnerabilities, Deserialization, Log4Shell Mitigation

## 1. Log4j Mitigation & Defense in Depth
For Java applications managing dependencies:
- **Primary Fix:** Upgrade `org.apache.logging.log4j:log4j-core` and `log4j-api` to `>= 2.17.1` (which disables JNDI lookups by default, removes support for message lookups, and protects against CVE-2021-44228, CVE-2021-45046, and CVE-2021-45105).
- **Temporary Flag Mitigation (JDK/JVM):** 
  ```bash
  -Dlog4j2.formatMsgNoLookups=true
  ```
  Or set environment variable:
  ```bash
  LOG4J_FORMAT_MSG_NO_LOOKUPS=true
  ```
- **Physical Class Removal (Emergency):** If patching is impossible, remove the JndiLookup class from the classpath jar:
  ```bash
  zip -q -d log4j-core-*.jar org/apache/logging/log4j/core/lookup/JndiLookup.class
  ```

## 2. Insecure Deserialization Controls (CWE-502)
- Avoid using native Java serialization (`ObjectInputStream`) on untrusted network data.
- Utilize JEP 290 / JEP 415 Serial Filtering:
  ```bash
  -Djdk.serialFilter="maxbytes=100000;maxdepth=10;!*"
  ```
- Use safe serialization formats such as JSON or Protocol Buffers with strict schema validation.

## 3. Container Runtime Constraints
- Never execute JVM processes as `root`. Run under a dedicated system user (e.g., `appuser:10001`).
- Mount `/tmp` as `noexec,nosuid`.
- Restrict outbound network access using egress Kubernetes `NetworkPolicy` objects.
