from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class FilingDocument:
    document_id: str
    issuer: str
    source: str
    text: str


class FilingParser:
    def parse(self, document_id: str, issuer: str, source: str, text: str) -> FilingDocument:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            raise ValueError("filing text is empty")
        return FilingDocument(document_id, issuer, source, cleaned)


class FinancialRAG:
    """Small deterministic lexical retrieval layer; embeddings can be injected later."""

    def __init__(self, documents: Iterable[FilingDocument] = ()):
        self.documents = list(documents)

    def add(self, document: FilingDocument) -> None:
        self.documents.append(document)

    def search(self, query: str, top_k: int = 5) -> list[FilingDocument]:
        terms = {x.lower() for x in query.split() if x.strip()}
        if not terms:
            return []
        scored = []
        for doc in self.documents:
            words = set(doc.text.lower().split())
            score = sum(term in words for term in terms)
            if score:
                scored.append((score, doc))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in scored[:top_k]]
