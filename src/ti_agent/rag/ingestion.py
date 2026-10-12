"""Knowledge base ingestion and vector index persistence pipeline."""

import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger
from ti_agent.rag.embeddings import get_embeddings

logger = get_logger("ti_agent.rag.ingestion")

TECHNIQUE_REGEX = re.compile(r"\b(T\d{4}(?:\.\d{3})?)\b")


def extract_document_metadata(file_path: Path, content: str) -> dict[str, str]:
    """Extract metadata (title, category, techniques) from a markdown document."""
    category = file_path.parent.name
    title = file_path.stem.replace("_", " ").title()

    # Try extracting H1 title
    lines = content.splitlines()
    for line in lines:
        if line.startswith("# "):
            title = line.replace("# ", "").strip()
            break

    # Look for technique IDs (e.g. T1190)
    techniques = TECHNIQUE_REGEX.findall(content)
    primary_technique = techniques[0] if techniques else "N/A"

    return {
        "source": str(file_path.name),
        "source_path": str(file_path),
        "category": category,
        "title": title,
        "technique_id": primary_technique,
    }


def load_knowledge_documents(docs_dir: Path) -> list[Document]:
    """Recursively load all markdown documents from knowledge base directory."""
    if not docs_dir.exists():
        logger.warning("Knowledge base directory does not exist: %s", docs_dir)
        return []

    documents: list[Document] = []
    for file_path in sorted(docs_dir.rglob("*.md")):
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                continue
            meta = extract_document_metadata(file_path, content)
            documents.append(Document(page_content=content, metadata=meta))
            logger.debug("Loaded document: %s (Category: %s)", file_path.name, meta["category"])
        except Exception as exc:
            logger.error("Failed to read document %s: %s", file_path, exc)

    logger.info("Loaded %d documents from %s", len(documents), docs_dir)
    return documents


def chunk_documents(
    documents: list[Document],
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[Document]:
    """Split documents into semantic overlapping chunks with preserved metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(documents)
    logger.info(
        "Split %d documents into %d chunks (chunk_size=%d, overlap=%d)",
        len(documents),
        len(chunks),
        chunk_size,
        chunk_overlap,
    )
    return chunks


def ingest_knowledge_base(
    docs_dir: Path | None = None,
    persist_dir: Path | None = None,
    settings: Settings | None = None,
) -> tuple[Chroma, int]:
    """Execute complete ingestion pipeline: load, chunk, embed, and persist to ChromaDB."""
    cfg = settings or get_settings()
    source_dir = docs_dir or Path("knowledge_base")
    target_dir = persist_dir or cfg.chroma_persist_dir

    target_dir.mkdir(parents=True, exist_ok=True)

    docs = load_knowledge_documents(source_dir)
    if not docs:
        raise ValueError(f"No documents found in knowledge base directory: {source_dir}")

    chunks = chunk_documents(docs)
    embeddings = get_embeddings(cfg)

    # Persist or update Chroma vectorstore
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(target_dir),
        collection_name="threat_intel_kb",
    )

    logger.info(
        "Successfully indexed %d chunks into ChromaDB at %s",
        len(chunks),
        target_dir,
    )
    return vectorstore, len(chunks)
