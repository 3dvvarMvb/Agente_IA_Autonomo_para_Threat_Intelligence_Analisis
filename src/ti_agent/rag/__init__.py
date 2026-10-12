"""RAG (Retrieval-Augmented Generation) pipeline for threat intelligence context."""

from ti_agent.rag.embeddings import FastDeterministicEmbeddings, get_embeddings
from ti_agent.rag.evaluation import (
    EVALUATION_BENCHMARK,
    RagEvaluationReport,
    evaluate_rag_retriever,
)
from ti_agent.rag.ingestion import (
    chunk_documents,
    ingest_knowledge_base,
    load_knowledge_documents,
)
from ti_agent.rag.retriever import KnowledgeRetriever, SourceCitation

__all__ = [
    "get_embeddings",
    "FastDeterministicEmbeddings",
    "load_knowledge_documents",
    "chunk_documents",
    "ingest_knowledge_base",
    "KnowledgeRetriever",
    "SourceCitation",
    "EVALUATION_BENCHMARK",
    "RagEvaluationReport",
    "evaluate_rag_retriever",
]
