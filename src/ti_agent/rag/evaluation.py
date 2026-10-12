"""Evaluation suite for the RAG pipeline measuring Hit Rate and MRR."""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from ti_agent.core.logging import get_logger
from ti_agent.rag.retriever import KnowledgeRetriever

logger = get_logger("ti_agent.rag.evaluation")


@dataclass
class EvalTestCase:
    """Benchmark test case for RAG retrieval."""

    question: str
    expected_sources: list[str]
    expected_techniques: list[str]
    expected_keywords: list[str]


# Standard benchmark test suite containing 12 threat intelligence domain questions
EVALUATION_BENCHMARK: list[EvalTestCase] = [
    EvalTestCase(
        question="How to patch and mitigate CVE-2021-44228 Log4Shell in Java applications?",
        expected_sources=[
            "java_application_hardening.md",
            "t1190_exploit_public_facing_application.md",
        ],
        expected_techniques=["T1190"],
        expected_keywords=["log4j", "2.17.1", "formatmsgnolookups"],
    ),
    EvalTestCase(
        question="What MITRE ATT&CK technique corresponds to exploiting public-facing web applications?",
        expected_sources=["t1190_exploit_public_facing_application.md"],
        expected_techniques=["T1190"],
        expected_keywords=["t1190", "initial access", "public-facing"],
    ),
    EvalTestCase(
        question="What steps should be taken immediately to contain active C2 beaconing?",
        expected_sources=[
            "c2_incident_response_playbook.md",
            "t1071_application_layer_protocol.md",
        ],
        expected_techniques=["T1071"],
        expected_keywords=["isolation", "quarantine", "sinkhole"],
    ),
    EvalTestCase(
        question="Which network ports are abused during Log4j LDAP and RMI callback exploitation?",
        expected_sources=[
            "t1190_exploit_public_facing_application.md",
            "network_egress_and_dns_filtering.md",
        ],
        expected_techniques=["T1190"],
        expected_keywords=["389", "1099", "ldap"],
    ),
    EvalTestCase(
        question="What configuration options harden OpenSSH on Linux servers?",
        expected_sources=["linux_host_hardening.md"],
        expected_techniques=[],
        expected_keywords=["permitrootlogin", "passwordauthentication", "sshd"],
    ),
    EvalTestCase(
        question="What MITRE technique represents Command and Control communication over HTTP or DNS?",
        expected_sources=["t1071_application_layer_protocol.md"],
        expected_techniques=["T1071"],
        expected_keywords=["t1071", "command and control", "c2"],
    ),
    EvalTestCase(
        question="How does DNS sinkholing prevent malware communication?",
        expected_sources=[
            "network_egress_and_dns_filtering.md",
            "c2_incident_response_playbook.md",
        ],
        expected_techniques=["T1071"],
        expected_keywords=["sinkhole", "0.0.0.0", "rpz"],
    ),
    EvalTestCase(
        question="Which ATT&CK technique covers Unix Shell and PowerShell script execution?",
        expected_sources=["t1059_command_and_scripting_interpreter.md"],
        expected_techniques=["T1059"],
        expected_keywords=["t1059", "execution", "shell"],
    ),
    EvalTestCase(
        question="How does Shodan passive reconnaissance relate to network discovery?",
        expected_sources=["t1046_network_service_discovery.md"],
        expected_techniques=["T1046"],
        expected_keywords=["t1046", "shodan", "discovery"],
    ),
    EvalTestCase(
        question="What JVM flag disables JNDI message lookups in vulnerable Log4j versions?",
        expected_sources=[
            "java_application_hardening.md",
            "t1190_exploit_public_facing_application.md",
        ],
        expected_techniques=["T1190"],
        expected_keywords=["log4j2.formatmsgnolookups", "jndi"],
    ),
    EvalTestCase(
        question="What forensic acquisition steps are required in the C2 incident response playbook?",
        expected_sources=["c2_incident_response_playbook.md"],
        expected_techniques=[],
        expected_keywords=["memory", "dump", "forensic"],
    ),
    EvalTestCase(
        question="What are the immediate mitigation phases for a critical zero-day CVE with CVSS 10.0?",
        expected_sources=["critical_cve_remediation_playbook.md"],
        expected_techniques=[],
        expected_keywords=["waf", "virtual patch", "cvss"],
    ),
]


class TestCaseResult(BaseModel):
    """Evaluation metrics for a single question."""

    model_config = ConfigDict(frozen=True)

    question: str
    is_hit: bool
    reciprocal_rank: float
    retrieved_sources: list[str]
    retrieved_techniques: list[str]
    matched_by: str = ""


class RagEvaluationReport(BaseModel):
    """Aggregated RAG evaluation metrics report."""

    model_config = ConfigDict(frozen=True)

    total_questions: int
    hits: int
    hit_rate: float = Field(description="Fraction of questions with at least 1 relevant hit (0-1)")
    mrr: float = Field(description="Mean Reciprocal Rank (0-1)")
    results: list[TestCaseResult] = Field(default_factory=list)

    def summary(self) -> str:
        """Format a human-readable summary of RAG performance."""
        lines = [
            "================ RAG Pipeline Evaluation ================",
            f"Total Benchmark Questions: {self.total_questions}",
            f"Hits: {self.hits} / {self.total_questions}",
            f"Hit Rate: {self.hit_rate:.1%}",
            f"Mean Reciprocal Rank (MRR): {self.mrr:.3f}",
            "---------------------------------------------------------",
        ]
        for i, r in enumerate(self.results, start=1):
            status = "PASS" if r.is_hit else "FAIL"
            lines.append(
                f"[{status}] Q{i}: {r.question[:45]}... (RR: {r.reciprocal_rank:.2f}, match: {r.matched_by})"
            )
        lines.append("=========================================================")
        return "\n".join(lines)


def evaluate_rag_retriever(
    retriever: KnowledgeRetriever,
    benchmark: list[EvalTestCase] | None = None,
    top_k: int = 4,
) -> RagEvaluationReport:
    """Run benchmark evaluation on retriever and calculate Hit Rate and MRR."""
    cases = benchmark or EVALUATION_BENCHMARK
    results: list[TestCaseResult] = []

    for case in cases:
        citations = retriever.retrieve(case.question, top_k=top_k)
        retrieved_sources = [c.source for c in citations]
        retrieved_techniques = [c.technique_id for c in citations if c.technique_id != "N/A"]

        # Check relevance: matches expected source, expected technique, or expected keyword
        hit = False
        rr = 0.0
        match_reason = ""

        for rank, citation in enumerate(citations, start=1):
            source_match = any(
                exp.lower() in citation.source.lower() for exp in case.expected_sources
            )
            technique_match = any(
                exp.upper() == citation.technique_id.upper() for exp in case.expected_techniques
            )
            snippet_lower = citation.snippet.lower()
            keyword_match = any(kw.lower() in snippet_lower for kw in case.expected_keywords)

            if source_match or technique_match or keyword_match:
                hit = True
                rr = 1.0 / rank
                if source_match:
                    match_reason = f"source: {citation.source}"
                elif technique_match:
                    match_reason = f"technique: {citation.technique_id}"
                else:
                    match_reason = "keyword"
                break

        results.append(
            TestCaseResult(
                question=case.question,
                is_hit=hit,
                reciprocal_rank=rr,
                retrieved_sources=retrieved_sources,
                retrieved_techniques=retrieved_techniques,
                matched_by=match_reason,
            )
        )

    total = len(cases)
    hits = sum(1 for r in results if r.is_hit)
    hit_rate = hits / total if total > 0 else 0.0
    mrr = sum(r.reciprocal_rank for r in results) / total if total > 0 else 0.0

    return RagEvaluationReport(
        total_questions=total,
        hits=hits,
        hit_rate=hit_rate,
        mrr=mrr,
        results=results,
    )
