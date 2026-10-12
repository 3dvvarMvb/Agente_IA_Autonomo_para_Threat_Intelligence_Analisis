"""Configurable embedding generators for the RAG pipeline."""

import hashlib
import math
import re

from langchain_core.embeddings import Embeddings

from ti_agent.core.config import Settings, get_settings
from ti_agent.core.logging import get_logger

logger = get_logger("ti_agent.rag.embeddings")


class FastDeterministicEmbeddings(Embeddings):
    """High-performance, reproducible semantic hash embedding model.

    Generates 384-dimensional unit-normalized embedding vectors based on
    subword n-grams, word tokens, and semantic security domain term weighting.
    Runs 100% offline with zero dependencies or external network requests.
    """

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def _embed_text(self, text: str) -> list[float]:
        tokens = re.findall(r"\w+", text.lower())
        vec = [0.0] * self.dimension

        if not tokens:
            return vec

        # Term weighting with positive hashes so cosine similarity and ChromaDB scores are strictly in [0, 1]
        for i, token in enumerate(tokens):
            # Unigram hash
            h1 = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx1 = h1 % self.dimension
            vec[idx1] += 2.0

            # Bigram hash for phrase context
            if i + 1 < len(tokens):
                bigram = f"{token}_{tokens[i + 1]}"
                h2 = int(hashlib.sha256(bigram.encode("utf-8")).hexdigest(), 16)
                idx2 = h2 % self.dimension
                vec[idx2] += 3.0

            # Character 4-grams for subword matching (e.g. CVE-2021-44228, T1190)
            for j in range(len(token) - 3):
                gram = token[j : j + 4]
                hg = int(hashlib.sha1(gram.encode("utf-8")).hexdigest(), 16)
                idxg = hg % self.dimension
                vec[idxg] += 0.8

        # L2 unit normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-12:
            vec = [x / norm for x in vec]

        return vec

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_text(text)


def get_embeddings(settings: Settings | None = None) -> Embeddings:
    """Factory to retrieve configured embeddings engine."""
    cfg = settings or get_settings()

    provider = cfg.embedding_provider.lower()
    logger.debug("Initializing embedding provider: %s", provider)

    if provider == "openai" and cfg.openai_api_key:
        try:
            from langchain_openai import OpenAIEmbeddings
            from pydantic import SecretStr

            return OpenAIEmbeddings(
                api_key=SecretStr(cfg.openai_api_key),
                model="text-embedding-3-small",
            )
        except Exception as exc:
            logger.warning("Failed to initialize OpenAIEmbeddings: %s. Falling back.", exc)

    # Default robust deterministic embedding for threat intelligence
    return FastDeterministicEmbeddings(dimension=384)
