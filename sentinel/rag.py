"""Local RAG over response protocols (stand-in for Vertex AI Search).

Loads the markdown SOPs, splits them into sections, and serves the most relevant
passage for a query via TF-IDF cosine similarity. Each result carries a citation
so recommendations can ground themselves in the city's own protocols.
"""
from __future__ import annotations

import glob
import os
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag", "protocols")


class ProtocolIndex:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self._vec = TfidfVectorizer(stop_words="english")
        self._mat = self._vec.fit_transform([c["text"] for c in chunks]) if chunks else None

    def search(self, query: str, k: int = 3) -> list[dict]:
        if not self.chunks:
            return []
        sims = cosine_similarity(self._vec.transform([query]), self._mat)[0]
        order = sims.argsort()[::-1][:k]
        return [{**self.chunks[i], "score": round(float(sims[i]), 3)}
                for i in order if sims[i] > 0]


def load_index(docs_dir: str | None = None) -> ProtocolIndex:
    docs_dir = docs_dir or DEFAULT_DIR
    chunks: list[dict] = []
    for path in sorted(glob.glob(os.path.join(docs_dir, "*.md"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"^#\s+(.+)", text, re.M)
        doc_title = m.group(1).strip() if m else stem
        body_text = re.sub(r"^#\s+.+$\n?", "", text, count=1, flags=re.M)  # drop the H1 line
        for i, part in enumerate(re.split(r"^##\s+", body_text, flags=re.M)):
            part = part.strip()
            if not part:
                continue
            if i == 0:
                heading, body = "Overview", part
            else:
                lines = part.splitlines()
                heading = lines[0].strip()
                body = " ".join(ln.strip() for ln in lines[1:]).strip()
            if len(body) < 10:
                continue
            chunks.append(dict(
                doc=stem, title=doc_title, heading=heading,
                text=f"{heading} {body}", snippet=body[:240],
                citation=f"{doc_title} §{heading}"))
    return ProtocolIndex(chunks)
