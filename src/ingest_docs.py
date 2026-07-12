"""PDFs in data/raw/docs -> cleaned page text -> overlapping chunks -> ChromaDB.
Run:  python -m src.ingest_docs              (default: 1800-char chunks, 300 overlap)
      python -m src.ingest_docs 1000 200     (chunk-size experiments for Day 4)
"""
import sys
from pathlib import Path

import chromadb
from pypdf import PdfReader

DOCS_DIR = Path("data/raw/docs")
DB_PATH = "chroma_db"
COLLECTION = "nutrition_docs"


def clean_page_text(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not ln.isdigit()]  # drop bare page numbers
    return " ".join(lines)


def chunk_pages(pages, chunk_chars=1800, overlap=300):
    """pages: list of (page_number, raw_text).
    Chunk WITHIN each page so every chunk has an exact page for citations."""
    chunks = []
    for page_num, raw in pages:
        text = clean_page_text(raw)
        if len(text) < 200:  # skip covers, dividers, near-empty pages
            continue
        start = 0
        while start < len(text):
            end = min(start + chunk_chars, len(text))
            chunks.append({"text": text[start:end], "page": page_num})
            if end == len(text):
                break
            start = end - overlap
    return chunks


def main(chunk_chars=1800, overlap=300):
    client = chromadb.PersistentClient(path=DB_PATH)
    try:
        client.delete_collection(COLLECTION)  # rebuild from scratch each run
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    total = 0
    for pdf in sorted(DOCS_DIR.glob("*.pdf")):
        reader = PdfReader(str(pdf))
        pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
        chunks = chunk_pages(pages, chunk_chars, overlap)
        for i in range(0, len(chunks), 64):
            batch = chunks[i:i + 64]
            coll.add(
                ids=[f"{pdf.stem}-{i + j}" for j in range(len(batch))],
                documents=[c["text"] for c in batch],
                metadatas=[{"source": pdf.name, "page": c["page"]} for c in batch],
            )
        total += len(chunks)
        print(f"{pdf.name}: {len(chunks)} chunks")
    print(f"Total: {total} chunks (chunk_chars={chunk_chars}, overlap={overlap})")


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]]
    main(*args)