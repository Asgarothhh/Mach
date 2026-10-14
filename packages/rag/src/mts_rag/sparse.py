"""Client-side BM25-hash sparse encoder (id sparse_bm25h_v2: stemmed/concept terms)."""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from mts_contracts.knowledge import ChunkMetadata

from mts_rag.lexical import document_terms, index_terms

SPARSE_VECTOR_NAME = "sparse_bm25h_v2"
_K1 = 1.2
_B = 0.75


def chunk_terms(chunk: ChunkMetadata) -> frozenset[str]:
    return document_terms(" ".join((chunk.title, *chunk.section_path, chunk.text)))


def chunk_token_list(chunk: ChunkMetadata) -> list[str]:
    return index_terms(" ".join((chunk.title, *chunk.section_path, chunk.text)))


def document_text(chunk: ChunkMetadata) -> str:
    return "\n".join([chunk.title, " / ".join(chunk.section_path), chunk.text])


def token_id(token: str) -> int:
    """Stable uint32 id: int.from_bytes(blake2b(tok, digest_size=4))."""
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest())


@dataclass(frozen=True, slots=True)
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass(frozen=True, slots=True)
class Bm25Stats:
    n: int
    df: dict[int, int]
    avgdl: float


class Bm25HashSparseEncoder:
    """BM25 weights with IDF baked into document vectors; query terms have value 1.0."""

    encoder_id: str = SPARSE_VECTOR_NAME
    k1: float = _K1
    b: float = _B

    def fit(self, documents: Sequence[Sequence[str]]) -> Bm25Stats:
        n = len(documents)
        df: Counter[int] = Counter()
        total_len = 0
        for tokens in documents:
            total_len += len(tokens)
            seen = {token_id(tok) for tok in tokens}
            for tid in seen:
                df[tid] += 1
        avgdl = (total_len / n) if n else 0.0
        return Bm25Stats(n=n, df=dict(df), avgdl=avgdl)

    def encode_document(self, tokens: Sequence[str], stats: Bm25Stats) -> SparseVector:
        tf = Counter(token_id(tok) for tok in tokens)
        dl = len(tokens)
        indices: list[int] = []
        values: list[float] = []
        for tid, freq in sorted(tf.items()):
            df = stats.df.get(tid, 0)
            idf = math.log(1.0 + (stats.n - df + 0.5) / (df + 0.5))
            if stats.avgdl > 0.0:
                denom = freq + self.k1 * (1.0 - self.b + self.b * dl / stats.avgdl)
            else:
                denom = freq + self.k1
            weight = idf * (freq * (self.k1 + 1.0)) / denom
            if weight > 0.0:
                indices.append(tid)
                values.append(weight)
        return SparseVector(indices=indices, values=values)

    def encode_query(self, tokens: Sequence[str]) -> SparseVector:
        ids = sorted({token_id(tok) for tok in tokens})
        return SparseVector(indices=ids, values=[1.0] * len(ids))
