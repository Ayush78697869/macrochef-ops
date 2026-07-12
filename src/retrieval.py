"""Vector retrieval over the nutrition corpus + grounded, cited answering.
CLI test:  python -m src.retrieval "How much added sugar per day is recommended?"
"""
import sys

import chromadb

from src.llm import extra_opts, get_client, strip_think

DB_PATH = "chroma_db"
COLLECTION = "nutrition_docs"


def get_collection():
    return chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION)


def retrieve(query: str, k: int = 5) -> list[dict]:
    res = get_collection().query(
        query_texts=[query], n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    return [
        {"text": d, "source": m["source"], "page": m["page"], "distance": dist}
        for d, m, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]


SYSTEM = """You answer nutrition questions using ONLY the provided context.
Cite every claim with the bracketed markers from the context, e.g. [dga_2020-2025.pdf p.31].
If the context does not contain the answer, say exactly: "I don't have that in my sources."
Be concise (under 150 words)."""


def answer_with_citations(question: str, k: int = 5) -> str:
    ctx = retrieve(question, k)
    context = "\n\n".join(f"[{c['source']} p.{c['page']}]\n{c['text']}" for c in ctx)
    client, model = get_client()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
        **extra_opts(),
    )
    return strip_think(resp.choices[0].message.content)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How much added sugar per day is recommended?"
    print(answer_with_citations(q))