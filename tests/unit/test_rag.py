"""Unit and integration tests for the RAG ingestion, embeddings, and evaluation pipeline."""

import math
from pathlib import Path

import pytest

from ti_agent.core.config import Settings
from ti_agent.rag.embeddings import FastDeterministicEmbeddings
from ti_agent.rag.evaluation import (
    EVALUATION_BENCHMARK,
    evaluate_rag_retriever,
)
from ti_agent.rag.ingestion import (
    chunk_documents,
    ingest_knowledge_base,
    load_knowledge_documents,
)
from ti_agent.rag.retriever import KnowledgeRetriever


@pytest.fixture
def kb_dir() -> Path:
    """Return path to knowledge_base directory."""
    path = Path(__file__).resolve().parent.parent.parent / "knowledge_base"
    assert path.is_dir(), f"Expected knowledge_base directory at {path}"
    return path


def test_load_knowledge_documents(kb_dir: Path) -> None:
    docs = load_knowledge_documents(kb_dir)
    assert len(docs) >= 8, f"Expected at least 8 markdown docs, got {len(docs)}"

    categories = {d.metadata.get("category") for d in docs}
    assert "mitre_attack" in categories
    assert "hardening" in categories
    assert "playbooks" in categories

    # Verify metadata on sample doc
    log4j_doc = next(d for d in docs if "t1190" in d.metadata.get("source", "").lower())
    assert log4j_doc.metadata.get("technique_id") == "T1190"
    assert "T1190" in log4j_doc.metadata.get("title", "")


def test_chunk_documents(kb_dir: Path) -> None:
    docs = load_knowledge_documents(kb_dir)
    chunks = chunk_documents(docs, chunk_size=500, chunk_overlap=80)

    assert len(chunks) > len(docs)
    for chunk in chunks:
        assert len(chunk.page_content) > 0
        assert "source" in chunk.metadata
        assert "category" in chunk.metadata


def test_fast_deterministic_embeddings() -> None:
    embedder = FastDeterministicEmbeddings(dimension=384)

    text_a = "CVE-2021-44228 Apache Log4j JNDI remote code execution"
    text_b = "Log4Shell Java vulnerability patching and mitigation"
    text_c = "Chocolate chip cookie recipe with brown sugar and flour"

    vec_a = embedder.embed_query(text_a)
    vec_b = embedder.embed_query(text_b)
    vec_c = embedder.embed_query(text_c)

    assert len(vec_a) == 384

    # Verify L2 unit norm
    norm_a = math.sqrt(sum(x * x for x in vec_a))
    assert pytest.approx(norm_a, abs=1e-4) == 1.0

    # Dot product = cosine similarity for normalized vectors
    def cos_sim(v1: list[float], v2: list[float]) -> float:
        return sum(x * y for x, y in zip(v1, v2, strict=False))

    sim_ab = cos_sim(vec_a, vec_b)
    sim_ac = cos_sim(vec_a, vec_c)

    # Security related texts must have significantly higher similarity than culinary text
    assert sim_ab > sim_ac
    assert sim_ab > 0.15


def test_ingest_and_retrieve_chromadb(tmp_path: Path, kb_dir: Path) -> None:
    persist_dir = tmp_path / "chroma_test_db"
    settings = Settings(
        chroma_persist_dir=persist_dir,
        enable_cache=False,
    )

    vectorstore, chunk_count = ingest_knowledge_base(
        docs_dir=kb_dir,
        persist_dir=persist_dir,
        settings=settings,
    )
    assert chunk_count > 0
    assert persist_dir.exists()

    retriever = KnowledgeRetriever(vectorstore=vectorstore, settings=settings, top_k=3)
    citations = retriever.retrieve("mitigate Log4j2 JNDI vulnerability")

    assert len(citations) == 3
    for c in citations:
        assert len(c.source) > 0
        assert len(c.snippet) > 0

    # Test context rendering
    context_text = retriever.retrieve_context("Log4Shell T1190")
    assert "### [Citation" in context_text
    assert "Excerpt:" in context_text


def test_rag_evaluation_benchmark(tmp_path: Path, kb_dir: Path) -> None:
    persist_dir = tmp_path / "chroma_eval_db"
    settings = Settings(
        chroma_persist_dir=persist_dir,
        enable_cache=False,
    )

    vectorstore, _ = ingest_knowledge_base(
        docs_dir=kb_dir,
        persist_dir=persist_dir,
        settings=settings,
    )
    retriever = KnowledgeRetriever(vectorstore=vectorstore, settings=settings, top_k=4)

    report = evaluate_rag_retriever(retriever, benchmark=EVALUATION_BENCHMARK, top_k=4)

    assert report.total_questions == 12
    # Ensure high quality retrieval: Hit Rate >= 80% and MRR >= 0.60
    assert report.hit_rate >= 0.80, f"Expected hit rate >= 80%, got {report.hit_rate:.1%}"
    assert report.mrr >= 0.60, f"Expected MRR >= 0.60, got {report.mrr:.3f}"

    summary_text = report.summary()
    assert "================ RAG Pipeline Evaluation ================" in summary_text
    assert "Hit Rate:" in summary_text
