import json
import os
import threading
import numpy as np
from fastembed import TextEmbedding

os.makedirs("data", exist_ok=True)

CHUNKS_FILE = "data/chunks.json"
VECTORS_FILE = "data/vectors.npy"

lock = threading.Lock()
embedding_model = None
chunks = []
vectors = np.zeros((0, 384))

if os.path.exists(CHUNKS_FILE) and os.path.exists(VECTORS_FILE):
    chunks = json.load(open(CHUNKS_FILE, encoding="utf-8"))
    vectors = np.load(VECTORS_FILE)


def embed(texts):
    global embedding_model
    if embedding_model is None:
        embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return np.array(list(embedding_model.embed(texts)))


def split_text(text, size=120, overlap=20):
    words = text.split()
    result = []
    start = 0
    while start < len(words):
        result.append(" ".join(words[start:start + size]))
        start = start + size - overlap
    return result


def add_text(text, source):
    global vectors
    with lock:
        known = set(c["text"] for c in chunks)
        pieces = [p for p in split_text(text) if len(p) > 40 and p not in known]
        if not pieces:
            return
        new_vectors = embed(pieces)
        for p in pieces:
            chunks.append({"text": p, "source": source})
        vectors = np.vstack([vectors, new_vectors])
        json.dump(chunks, open(CHUNKS_FILE, "w", encoding="utf-8"))
        np.save(VECTORS_FILE, vectors)


def search(query, k=6):
    if len(chunks) == 0:
        return []
    q = embed([query])[0]
    scores = vectors @ q / (np.linalg.norm(vectors, axis=1) * np.linalg.norm(q) + 1e-9)
    best = np.argsort(scores)[::-1][:k]
    return [chunks[i] for i in best if scores[i] > 0.4]
