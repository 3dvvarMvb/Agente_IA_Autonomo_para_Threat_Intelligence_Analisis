"""Retriever engine providing top-k relevant chunks with source citations."""

from pathlib import Path

from langchain_chroma import Chroma
from pydantic import BaseModel, ConfigDict, Field

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.rag.embeddings import get_embeddings
from ti_agent.rag.ingestion import ingest_knowledge_base

logger = get_logger("ti_agent.rag.retriever")


class SourceCitation(BaseModel):
    """Retrieved knowledge citation linking evidence to a source document."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(description="Source file name")
    title: str = Field(description="Document title")
    category: str = Field(description="Category (mitre_attack, hardening, playbooks)")
    technique_id: str = Field(default="N/A", description="Associated MITRE technique ID")
    snippet: str = Field(description="Extracted relevant text excerpt")
    score: float = Field(default=0.0, description="Relevance similarity score")


class KnowledgeRetriever:
    """Retriever component for querying the persisted threat intelligence vectorstore."""

    def __init__(
        self,
        vectorstore: Chroma | None = None,
        settings: Settings | None = None,
        top_k: int | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.top_k = top_k or self.settings.rag_top_k
        self._vectorstore = vectorstore

    def _get_vectorstore(self) -> Chroma:
        """Lazily initialize or load the Chroma vectorstore."""
        if self._vectorstore is not None:
            return self._vectorstore

        persist_dir = self.settings.chroma_persist_dir
        embeddings = get_embeddings(self.settings)

        # If persist directory exists and has collections, load it
        if persist_dir.exists() and any(persist_dir.iterdir()):
            logger.debug("Loading existing Chroma vectorstore from %s", persist_dir)
            self._vectorstore = Chroma(
                persist_directory=str(persist_dir),
                embedding_function=embeddings,
                collection_name="threat_intel_kb",
            )
        else:
            logger.info(
                "Chroma vectorstore not found at %s. Running auto-ingestion...", persist_dir
            )
            kb_dir = Path("knowledge_base")
            if not kb_dir.exists():
                # Try finding relative to package
                kb_dir = Path(__file__).resolve().parent.parent.parent.parent / "knowledge_base"
            self._vectorstore, _ = ingest_knowledge_base(
                docs_dir=kb_dir,
                persist_dir=persist_dir,
                settings=self.settings,
            )

        return self._vectorstore

    def retrieve(self, query: str, top_k: int | None = None) -> list[SourceCitation]:
        """Query the vectorstore and return structured citations."""
        k = top_k or self.top_k
        store = self._get_vectorstore()

        try:
            results_with_distances = store.similarity_search_with_score(query, k=k)
            # Distance d in L2: score = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
            results_with_scores = [
                (doc, max(0.0, min(1.0, 1.0 - (dist / 2.0))))
                for doc, dist in results_with_distances
            ]
        except Exception as exc:
            logger.warning("Score retrieval failed (%s), falling back to similarity search", exc)
            docs = store.similarity_search(query, k=k)
            results_with_scores = [(doc, 1.0) for doc in docs]

        citations: list[SourceCitation] = []
        for doc, score in results_with_scores:
            meta = doc.metadata or {}
            citations.append(
                SourceCitation(
                    source=str(meta.get("source", "unknown.md")),
                    title=str(meta.get("title", "Untitled")),
                    category=str(meta.get("category", "general")),
                    technique_id=str(meta.get("technique_id", "N/A")),
                    snippet=doc.page_content.strip(),
                    score=float(score) if score is not None else 0.0,
                )
            )

        logger.debug("Retrieved %d citations for query: '%s'", len(citations), query[:50])
        return citations

    def retrieve_context(self, query: str, top_k: int | None = None) -> str:
        """Format retrieved chunks into clean text context with source citations."""
        citations = self.retrieve(query, top_k=top_k)
        if not citations:
            return "No relevant internal threat intelligence found in knowledge base."

        formatted_blocks = []
        for i, c in enumerate(citations, start=1):
            block = (
                f"### [Citation {i}] {c.title} ({c.source})\n"
                f"- Category: {c.category} | Technique: {c.technique_id} | Score: {c.score:.2f}\n"
                f"- Excerpt:\n{c.snippet}\n"
            )
            formatted_blocks.append(block)

        return "\n".join(formatted_blocks)
