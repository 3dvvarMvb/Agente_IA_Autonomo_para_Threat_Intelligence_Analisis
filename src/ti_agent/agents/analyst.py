"""Context Analyst Agent: RAG correlation, MITRE ATT&CK mapping, and risk scoring."""

from pydantic import BaseModel, ConfigDict, Field

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.i18n import resolve_language
from ti_agent.core.logging import get_logger
from ti_agent.models.indicator import IndicatorType
from ti_agent.models.report import ExtractionResult, Mitigation, MitreTechnique
from ti_agent.rag.retriever import KnowledgeRetriever, SourceCitation

logger = get_logger("ti_agent.agents.analyst")


class AnalysisResult(BaseModel):
    """Normalized output produced by the Context Analyst Agent."""

    model_config = ConfigDict(frozen=True)

    risk_score: float = Field(ge=0.0, le=10.0, description="Composite risk score (0-10)")
    severity_level: str = Field(description="Severity (CRITICAL, HIGH, MEDIUM, LOW, INFO)")
    risk_rationale: str = Field(description="Detailed scoring explanation")
    correlated_cves: list[str] = Field(default_factory=list)
    mitre_techniques: list[MitreTechnique] = Field(default_factory=list)
    mitigations: list[Mitigation] = Field(default_factory=list)
    rag_context: str = Field(description="Formatted knowledge context used during analysis")
    citations: list[SourceCitation] = Field(default_factory=list)


class ContextAnalystAgent:
    """Agent performing RAG retrieval, threat correlation, and risk prioritization."""

    def __init__(
        self,
        retriever: KnowledgeRetriever | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.retriever = retriever or KnowledgeRetriever(settings=self.settings)

    def _build_rag_query(self, extraction: ExtractionResult) -> str:
        """Formulate targeted RAG search query based on extraction telemetry."""
        indicator = extraction.indicator
        query_terms = [indicator.value]

        if indicator.type == IndicatorType.CVE and extraction.nvd:
            query_terms.append(extraction.nvd.cve_id)
            if extraction.nvd.cwe_ids:
                query_terms.extend(extraction.nvd.cwe_ids[:2])
            query_terms.append(extraction.nvd.description[:100])

        if extraction.virustotal:
            if extraction.virustotal.community_tags:
                query_terms.extend(extraction.virustotal.community_tags[:3])
            if extraction.virustotal.is_flagged_malicious:
                query_terms.append("command and control malware mitigation")

        if extraction.shodan and extraction.shodan.vulns:
            query_terms.extend(extraction.shodan.vulns[:3])

        if indicator.type == IndicatorType.URL or extraction.web_audit:
            query_terms.append("web application security headers CSP clickjacking hardening")

        return " ".join(query_terms)

    def calculate_risk(
        self, extraction: ExtractionResult, language: str | None = None
    ) -> tuple[float, str, str, list[str]]:
        """Calculate composite risk score based on CVSS, exploitability, and exposure."""
        lang = resolve_language(language, settings=self.settings)
        indicator = extraction.indicator
        correlated_cves: list[str] = []

        # If web dynamic audit is present, use web application security scoring
        if extraction.web_audit:
            web = extraction.web_audit
            final_score = web.security_score
            if final_score >= 9.0:
                severity = "CRITICAL"
            elif final_score >= 7.0:
                severity = "HIGH"
            elif final_score >= 4.0:
                severity = "MEDIUM"
            elif final_score >= 1.0:
                severity = "LOW"
            else:
                severity = "INFO"

            if lang == "es":
                rationale = (
                    f"La inspección de seguridad de la aplicación web concluyó con una puntuación de riesgo de {final_score}/10.0 (Calificación: {web.grade}). "
                    f"Se evaluaron {web.total_checks_count} controles de seguridad ({web.passed_checks_count} aprobados). "
                    f"Correlacionado con OWASP: {', '.join(web.owasp_tags)}."
                )
            else:
                rationale = (
                    f"Web application security inspection concluded with a risk score of {final_score}/10.0 (Grade: {web.grade}). "
                    f"Assessed {web.total_checks_count} security controls ({web.passed_checks_count} passed). "
                    f"Correlated with OWASP: {', '.join(web.owasp_tags)}."
                )
            return final_score, severity, rationale, correlated_cves

        base_cvss = 0.0
        # 1. Base CVSS from NVD or Shodan vulns
        if extraction.nvd and extraction.nvd.cvss:
            base_cvss = extraction.nvd.score
            correlated_cves.append(extraction.nvd.cve_id)

        if extraction.shodan and extraction.shodan.vulns:
            for v in extraction.shodan.vulns:
                if v not in correlated_cves:
                    correlated_cves.append(v)
            if base_cvss == 0.0:
                base_cvss = 7.5  # Assumed default for indexed unpatched vulnerabilities

        # 2. Exploitability Factor (0.0 to 1.0)
        exploit_factor = 0.1
        if extraction.virustotal:
            if extraction.virustotal.is_flagged_malicious:
                ratio = extraction.virustotal.stats.positive_engines / max(
                    1, extraction.virustotal.stats.total_engines
                )
                exploit_factor = min(1.0, 0.4 + (ratio * 0.6))
        elif extraction.nvd and extraction.nvd.cvss:
            if (extraction.nvd.cvss.exploitability_score or 0.0) >= 3.0:
                exploit_factor = 1.0
            else:
                exploit_factor = 0.7

        # 3. Exposure Factor (0.0 to 1.0)
        exposure_factor = 0.2
        if extraction.shodan and extraction.shodan.ports:
            num_ports = len(extraction.shodan.ports)
            exposure_factor = min(1.0, 0.4 + (num_ports * 0.15))
            # Critical administrative / vulnerable ports elevate exposure
            high_risk_ports = {22, 23, 445, 1099, 389, 3389, 8080, 2375, 9200, 6379}
            if any(p in high_risk_ports for p in extraction.shodan.ports):
                exposure_factor = min(1.0, exposure_factor + 0.3)
        elif indicator.type == IndicatorType.CVE:
            # CVE network exploitable vector
            if (
                extraction.nvd
                and extraction.nvd.cvss
                and "AV:N" in extraction.nvd.cvss.vector_string
            ):
                exposure_factor = 1.0
            else:
                exposure_factor = 0.8

        # Mathematical Synthesis Formula
        # Risk = Base * 0.5 + Exploit * 3.0 + Exposure * 2.0
        calculated = (base_cvss * 0.5) + (exploit_factor * 3.0) + (exposure_factor * 2.0)

        # Force minimum baseline if VT confirmed malicious
        if extraction.virustotal and extraction.virustotal.is_flagged_malicious:
            calculated = max(calculated, 7.5)

        # Force max 10.0
        final_score = round(min(10.0, max(0.0, calculated)), 1)

        # Determine severity label
        if final_score >= 9.0:
            severity = "CRITICAL"
        elif final_score >= 7.0:
            severity = "HIGH"
        elif final_score >= 4.0:
            severity = "MEDIUM"
        elif final_score >= 1.0:
            severity = "LOW"
        else:
            severity = "INFO"

        if lang == "es":
            rationale = (
                f"Calculado a partir de CVSS Base ({base_cvss:.1f} * 0.5) + "
                f"Factor de Explotabilidad ({exploit_factor:.2f} * 3.0) + "
                f"Exposición Observada ({exposure_factor:.2f} * 2.0)."
            )
        else:
            rationale = (
                f"Calculated from Base CVSS ({base_cvss:.1f} * 0.5) + "
                f"Exploitability Factor ({exploit_factor:.2f} * 3.0) + "
                f"Observed Exposure ({exposure_factor:.2f} * 2.0)."
            )

        return final_score, severity, rationale, correlated_cves

    def _derive_mitre_techniques(
        self,
        extraction: ExtractionResult,
        citations: list[SourceCitation],
        language: str | None = None,
    ) -> list[MitreTechnique]:
        """Map findings to MITRE ATT&CK techniques with contextual justification."""
        lang = resolve_language(language, settings=self.settings)
        techniques: list[MitreTechnique] = []
        seen_ids: set[str] = set()

        # 1. Techniques identified through RAG citations
        for c in citations:
            tid = c.technique_id.strip().upper()
            if tid and tid != "N/A" and tid not in seen_ids:
                seen_ids.add(tid)
                name = c.title.split(":")[-1].strip() if ":" in c.title else c.title
                if lang == "es":
                    tactic = (
                        "Acceso Inicial"
                        if tid == "T1190"
                        else ("Comando y Control" if tid == "T1071" else "Ejecución")
                    )
                    rel = f"Correlacionado mediante artículo de base de conocimiento '{c.source}'."
                else:
                    tactic = (
                        "Initial Access"
                        if tid == "T1190"
                        else ("Command and Control" if tid == "T1071" else "Execution")
                    )
                    rel = f"Correlated via internal knowledge base article '{c.source}'."
                techniques.append(
                    MitreTechnique(
                        technique_id=tid,
                        name=name,
                        tactic=tactic,
                        description=c.snippet[:150] + "...",
                        relevance_explanation=rel,
                    )
                )

        # 2. Direct telemetry mappings
        if extraction.indicator.type == IndicatorType.CVE and "T1190" not in seen_ids:
            seen_ids.add("T1190")
            if lang == "es":
                techniques.append(
                    MitreTechnique(
                        technique_id="T1190",
                        name="Explotación de Aplicación Pública",
                        tactic="Acceso Inicial",
                        description="Los atacantes pueden intentar explotar una vulnerabilidad en una aplicación expuesta a Internet.",
                        relevance_explanation="El objetivo es un CVE público que permite explotación remota no autorizada.",
                    )
                )
            else:
                techniques.append(
                    MitreTechnique(
                        technique_id="T1190",
                        name="Exploit Public-Facing Application",
                        tactic="Initial Access",
                        description="Adversaries may attempt to exploit a vulnerability in an Internet-facing application.",
                        relevance_explanation="Target is a public CVE that enables unauthorized remote exploitation.",
                    )
                )

        if (
            extraction.virustotal
            and extraction.virustotal.is_flagged_malicious
            and "T1071" not in seen_ids
        ):
            seen_ids.add("T1071")
            if lang == "es":
                techniques.append(
                    MitreTechnique(
                        technique_id="T1071",
                        name="Protocolo de Capa de Aplicación",
                        tactic="Comando y Control",
                        description="Los atacantes pueden comunicarse mediante protocolos de capa de aplicación para evadir defensas.",
                        relevance_explanation="Indicador marcado por múltiples proveedores de seguridad como malware activo o nodo C2.",
                    )
                )
            else:
                techniques.append(
                    MitreTechnique(
                        technique_id="T1071",
                        name="Application Layer Protocol",
                        tactic="Command and Control",
                        description="Adversaries may communicate using application layer protocols to bypass defenses.",
                        relevance_explanation="Indicator flagged by multiple security vendors as active malware/C2 node.",
                    )
                )

        if extraction.shodan and extraction.shodan.ports and "T1046" not in seen_ids:
            seen_ids.add("T1046")
            if lang == "es":
                techniques.append(
                    MitreTechnique(
                        technique_id="T1046",
                        name="Descubrimiento de Servicios de Red",
                        tactic="Descubrimiento",
                        description="Los atacantes intentan enumerar servicios accesibles y puertos abiertos expuestos.",
                        relevance_explanation=f"Shodan indexó {len(extraction.shodan.ports)} puertos públicos expuestos.",
                    )
                )
            else:
                techniques.append(
                    MitreTechnique(
                        technique_id="T1046",
                        name="Network Service Discovery",
                        tactic="Discovery",
                        description="Adversaries attempt to enumerate accessible services and exposed open ports.",
                        relevance_explanation=f"Shodan indexed {len(extraction.shodan.ports)} exposed public ports.",
                    )
                )

        if extraction.web_audit:
            if "T1190" not in seen_ids:
                seen_ids.add("T1190")
                if lang == "es":
                    techniques.append(
                        MitreTechnique(
                            technique_id="T1190",
                            name="Explotación de Aplicación Pública",
                            tactic="Acceso Inicial",
                            description="Los atacantes pueden intentar explotar controles o cabeceras de seguridad faltantes en la aplicación web.",
                            relevance_explanation=f"El objetivo web carece de cabeceras de seguridad en profundidad (Puntuación de riesgo: {extraction.web_audit.security_score}).",
                        )
                    )
                else:
                    techniques.append(
                        MitreTechnique(
                            technique_id="T1190",
                            name="Exploit Public-Facing Application",
                            tactic="Initial Access",
                            description="Adversaries may attempt to exploit missing security controls or headers in a web application.",
                            relevance_explanation=f"Web target lacks defense-in-depth security headers (Risk score: {extraction.web_audit.security_score}).",
                        )
                    )
            if "T1592" not in seen_ids and (
                extraction.web_audit.server_banner or extraction.web_audit.powered_by
            ):
                seen_ids.add("T1592")
                tech_label = extraction.web_audit.server_banner or extraction.web_audit.powered_by
                if lang == "es":
                    techniques.append(
                        MitreTechnique(
                            technique_id="T1592",
                            name="Recolección de Información del Host Víctima",
                            tactic="Reconocimiento",
                            description="Los atacantes pueden recopilar información del host como versiones de software a partir de cabeceras.",
                            relevance_explanation=f"El servidor divulga huella tecnológica en cabeceras: {tech_label}.",
                        )
                    )
                else:
                    techniques.append(
                        MitreTechnique(
                            technique_id="T1592",
                            name="Gather Victim Host Information",
                            tactic="Reconnaissance",
                            description="Adversaries may gather host information such as software versions from response headers.",
                            relevance_explanation=f"Server discloses technology fingerprint: {tech_label}.",
                        )
                    )

        return techniques

    def _derive_mitigations(
        self,
        extraction: ExtractionResult,
        severity: str,
        _citations: list[SourceCitation],
        language: str | None = None,
    ) -> list[Mitigation]:
        """Generate actionable remediation recommendations prioritized by severity."""
        lang = resolve_language(language, settings=self.settings)
        mitigations: list[Mitigation] = []
        prio = (
            "CRITICAL" if severity == "CRITICAL" else ("HIGH" if severity == "HIGH" else "MEDIUM")
        )

        if extraction.indicator.type == IndicatorType.CVE:
            cve_id = extraction.indicator.value
            if lang == "es":
                mitigations.append(
                    Mitigation(
                        title=f"Parcheo de Seguridad de Emergencia para {cve_id}",
                        description=f"Actualizar paquetes de software y dependencias afectadas para remediar {cve_id}.",
                        priority=prio,  # type: ignore[arg-type]
                        category="Parcheo",
                        actionable_steps=[
                            "Identificar todos los hosts y contenedores en producción que ejecutan la dependencia vulnerable.",
                            "Desplegar paquetes o librerías actualizadas por el fabricante en staging.",
                            "Aplicar despliegue de emergencia en producción siguiendo el protocolo de gestión de cambios.",
                        ],
                    )
                )
                mitigations.append(
                    Mitigation(
                        title="Parcheo Virtual con WAF y Filtrado de Salida en Perímetro",
                        description="Desplegar firmas de inspección perimetral y restringir protocolos salientes inesperados.",
                        priority="HIGH",
                        category="Hardening de Red",
                        actionable_steps=[
                            "Configurar reglas en WAF para bloquear payloads de exploits en cabeceras y cuerpos HTTP.",
                            "Bloquear tráfico saliente del servidor en puertos no estándar (ej. LDAP 389/636, RMI 1099).",
                        ],
                    )
                )
            else:
                mitigations.append(
                    Mitigation(
                        title=f"Emergency Security Patching for {cve_id}",
                        description=f"Upgrade affected software packages and dependencies to remediate {cve_id}.",
                        priority=prio,  # type: ignore[arg-type]
                        category="Patching",
                        actionable_steps=[
                            "Identify all production hosts and containers executing the vulnerable dependency.",
                            "Deploy vendor updated packages or library versions in staging.",
                            "Apply emergency production deployment following change management protocol.",
                        ],
                    )
                )
                mitigations.append(
                    Mitigation(
                        title="WAF Virtual Patching & Egress Boundary Filtering",
                        description="Deploy edge inspection signatures and restrict unexpected outbound protocols.",
                        priority="HIGH",
                        category="Network Hardening",
                        actionable_steps=[
                            "Configure WAF rules to block malicious exploit payloads in HTTP headers and request bodies.",
                            "Block outbound server egress on non-standard ports (e.g. LDAP 389/636, RMI 1099).",
                        ],
                    )
                )

        if extraction.virustotal and extraction.virustotal.is_flagged_malicious:
            target_val = extraction.indicator.value
            if lang == "es":
                mitigations.append(
                    Mitigation(
                        title=f"Bloqueo Perimetral y Sinkholing DNS para {target_val}",
                        description="Enrutar a nulo el indicador malicioso en firewalls de borde y redirigir DNS recursivo.",
                        priority="CRITICAL",
                        category="Detección y Contención",
                        actionable_steps=[
                            f"Añadir {target_val} a las listas de bloqueo de firewalls y proxies perimetrales.",
                            "Inyectar dominio en DNS Response Policy Zone (RPZ) resolviendo a 0.0.0.0.",
                            "Consultar logs en SIEM para conexiones históricas e identificar endpoints comprometidos.",
                        ],
                    )
                )
            else:
                mitigations.append(
                    Mitigation(
                        title=f"Perimeter Block & DNS Sinkholing for {target_val}",
                        description="Null-route malicious indicator at border firewalls and redirect recursive DNS.",
                        priority="CRITICAL",
                        category="Detection & Containment",
                        actionable_steps=[
                            f"Add {target_val} to edge firewall and proxy egress blocklists.",
                            "Inject domain into DNS Response Policy Zone (RPZ) resolving to 0.0.0.0.",
                            "Query SIEM logs for historical connections to identify potentially compromised endpoints.",
                        ],
                    )
                )

        if extraction.shodan and extraction.shodan.ports:
            ports_str = ", ".join(str(p) for p in extraction.shodan.ports[:5])
            if lang == "es":
                mitigations.append(
                    Mitigation(
                        title="Minimización de Superficie de Ataque y Restricción de Puertos",
                        description=f"Cerrar o filtrar con firewall los puertos expuestos observados en Shodan ({ports_str}).",
                        priority="HIGH" if prio == "CRITICAL" else "MEDIUM",
                        category="Hardening de Infraestructura",
                        actionable_steps=[
                            "Auditar grupos de seguridad públicos y aplicar reglas de ingreso estrictas default-deny.",
                            "Mover servicios administrativos (SSH, RDP, BD) detrás de VPN corporativa o hosts bastión.",
                            "Sanitizar banners de aplicaciones para prevenir fuga de versiones de software.",
                        ],
                    )
                )
            else:
                mitigations.append(
                    Mitigation(
                        title="Attack Surface Minimization & Port Restriction",
                        description=f"Close or firewall exposed ports observed in Shodan ({ports_str}).",
                        priority="HIGH" if prio == "CRITICAL" else "MEDIUM",
                        category="Infrastructure Hardening",
                        actionable_steps=[
                            "Audit public security groups and apply strict default-deny ingress rules.",
                            "Move administrative services (SSH, RDP, DB) behind corporate VPN or bastion jump hosts.",
                            "Sanitize application banners to prevent version leakage.",
                        ],
                    )
                )

        if extraction.web_audit:
            web = extraction.web_audit
            if lang == "es":
                mitigations.append(
                    Mitigation(
                        title="Implementar Cabeceras de Seguridad OWASP (CSP, X-Frame-Options, nosniff)",
                        description="Configurar cabeceras de respuesta HTTP defensivas para prevenir Cross-Site Scripting (XSS), Clickjacking y MIME-sniffing.",
                        priority="HIGH",
                        category="Hardening de Aplicación",
                        actionable_steps=[
                            "En FastAPI: Añadir middleware configurando Content-Security-Policy, X-Frame-Options: DENY y X-Content-Type-Options: nosniff.",
                            "En Express.js: Ejecutar 'npm install helmet' y registrar 'app.use(helmet())'.",
                            "En Next.js: Configurar cabeceras en next.config.js bajo 'async headers()'.",
                            "En Nginx: Añadir directivas 'add_header X-Frame-Options DENY always;' y 'add_header X-Content-Type-Options nosniff always;'.",
                        ],
                    )
                )
                if web.server_banner or web.powered_by:
                    tech_str = web.server_banner or web.powered_by
                    mitigations.append(
                        Mitigation(
                            title="Ocultar Huellas Tecnológicas (Server y X-Powered-By)",
                            description=f"Eliminar banners de frameworks ('{tech_str}') para dificultar el reconocimiento del adversario.",
                            priority="MEDIUM",
                            category="Cambio de Configuración",
                            actionable_steps=[
                                "En Express: Añadir 'app.disable(\"x-powered-by\")'.",
                                "En Uvicorn/FastAPI: Ejecutar con '--no-server-header' o suprimir la cabecera en middleware.",
                                "En Nginx: Añadir 'server_tokens off;'.",
                            ],
                        )
                    )
                if web.cookie_checks:
                    mitigations.append(
                        Mitigation(
                            title="Reforzar Atributos de Cookies de Sesión (HttpOnly, Secure, SameSite)",
                            description="Asegurar que las cookies estén protegidas contra robo vía JavaScript y peticiones no autorizadas de origen cruzado.",
                            priority="HIGH",
                            category="Seguridad de Autenticación",
                            actionable_steps=[
                                "Configurar 'HttpOnly: true' en todas las cookies de sesión y autenticación.",
                                "Configurar 'SameSite: Lax' o 'Strict' para neutralizar Cross-Site Request Forgery (CSRF).",
                                "Activar 'Secure: true' al servir sobre TLS/HTTPS.",
                            ],
                        )
                    )
            else:
                mitigations.append(
                    Mitigation(
                        title="Implement Missing OWASP Security Headers (CSP, X-Frame-Options, nosniff)",
                        description="Configure defensive HTTP response headers to prevent Cross-Site Scripting (XSS), Clickjacking, and MIME-sniffing.",
                        priority="HIGH",
                        category="Application Hardening",
                        actionable_steps=[
                            "In FastAPI: Add middleware setting Content-Security-Policy, X-Frame-Options: DENY, and X-Content-Type-Options: nosniff.",
                            "In Express.js: Run 'npm install helmet' and add 'app.use(helmet())'.",
                            "In Next.js: Configure headers in next.config.js under 'async headers()'.",
                            "In Nginx: Add directives 'add_header X-Frame-Options DENY always;' and 'add_header X-Content-Type-Options nosniff always;'.",
                        ],
                    )
                )
                if web.server_banner or web.powered_by:
                    mitigations.append(
                        Mitigation(
                            title="Mask Technology Fingerprints (Server & X-Powered-By)",
                            description=f"Remove framework banners ('{web.server_banner or web.powered_by}') to impede adversary reconnaissance.",
                            priority="MEDIUM",
                            category="Configuration Change",
                            actionable_steps=[
                                "In Express: Add 'app.disable(\"x-powered-by\")'.",
                                "In Uvicorn/FastAPI: Run with '--no-server-header' or strip the header in middleware.",
                                "In Nginx: Add 'server_tokens off;'.",
                            ],
                        )
                    )
                if web.cookie_checks:
                    mitigations.append(
                        Mitigation(
                            title="Harden Session Cookie Attributes (HttpOnly, Secure, SameSite)",
                            description="Ensure cookies are protected against JavaScript theft and unauthorized cross-site requests.",
                            priority="HIGH",
                            category="Authentication Security",
                            actionable_steps=[
                                "Set 'HttpOnly: true' on all session and authentication cookies.",
                                "Set 'SameSite: Lax' or 'Strict' to neutralize Cross-Site Request Forgery (CSRF).",
                                "Enable 'Secure: true' when serving over TLS/HTTPS.",
                            ],
                        )
                    )

        return mitigations

    def analyze(
        self,
        extraction: ExtractionResult,
        language: str | None = None,
    ) -> AnalysisResult:
        """Run complete contextual analysis over extraction result."""
        lang = resolve_language(language, settings=self.settings)

        # 1. RAG Retrieval
        query = self._build_rag_query(extraction)
        citations = self.retriever.retrieve(query)
        rag_context = self.retriever.retrieve_context(query)

        # 2. Risk Calculation
        score, severity, rationale, cves = self.calculate_risk(extraction, language=lang)

        # 3. MITRE ATT&CK Mapping
        mitre_techniques = self._derive_mitre_techniques(extraction, citations, language=lang)

        # 4. Actionable Mitigations
        mitigations = self._derive_mitigations(extraction, severity, citations, language=lang)

        return AnalysisResult(
            risk_score=score,
            severity_level=severity,
            risk_rationale=rationale,
            correlated_cves=cves,
            mitre_techniques=mitre_techniques,
            mitigations=mitigations,
            rag_context=rag_context,
            citations=citations,
        )
