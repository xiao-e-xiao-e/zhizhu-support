"""向量存储模块：管理 ChromaDB 集合与嵌入模型。

嵌入方案（按 USE_LOCAL_EMBEDDING 配置选择）：
  1. 本地 TF-IDF（默认）：使用 sklearn，纯本地运行，零下载，即时可用
  2. 远程 API：通过 OpenAI 兼容接口调用远程嵌入服务
"""
from __future__ import annotations

import os
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

_embed_fn = None
_api_client = None


def _use_local() -> bool:
    val = os.getenv("USE_LOCAL_EMBEDDING", "true").lower()
    return val in ("true", "1", "yes")


_FIXED_DIM = 512


def _get_local_embed_fn():
    """使用 sklearn TF-IDF 作为本地嵌入模型。"""
    global _embed_fn
    if _embed_fn is None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        _embed_fn = TfidfVectorizer(
            max_features=_FIXED_DIM,
            analyzer="char_wb",
            ngram_range=(2, 4),
        )
    return _embed_fn


def _pad_vectors(vectors: list[list[float]], target_dim: int) -> list[list[float]]:
    """将向量填充到目标维度。"""
    result: list[list[float]] = []
    for v in vectors:
        if len(v) < target_dim:
            result.append(v + [0.0] * (target_dim - len(v)))
        else:
            result.append(v[:target_dim])
    return result


def _get_api_client():
    global _api_client
    if _api_client is None:
        from openai import OpenAI
        api_key = os.getenv("API_KEY", "")
        base_url = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            raise RuntimeError("请在 .env 中设置 API_KEY")
        _api_client = OpenAI(api_key=api_key, base_url=base_url)
    return _api_client


def _get_chroma_path() -> str:
    return str(Path(__file__).parent.parent / "chroma_db")


def get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(
        path=_get_chroma_path(),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection("knowledge_base")


def embed_texts(texts: list[str]) -> list[list[float]]:
    """将文本列表转换为向量嵌入（固定维度）。"""
    if _use_local():
        vectorizer = _get_local_embed_fn()
        matrix = vectorizer.fit_transform(texts)
        vectors = matrix.toarray().tolist()
        return _pad_vectors(vectors, _FIXED_DIM)
    else:
        client = _get_api_client()
        model_name = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        resp = client.embeddings.create(input=texts, model=model_name)
        return [item.embedding for item in resp.data]


def add_documents(filename: str, chunks: list[str], embeddings: list[list[float]] | None = None) -> int:
    if not chunks:
        return 0

    if embeddings is None:
        embeddings = embed_texts(chunks)

    collection = get_collection()
    ids = [f"{filename}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]

    existing = collection.get(ids=ids)
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    return len(chunks)


def search(query: str, top_k: int = 5, similarity_threshold: float = 0.0) -> list[dict]:
    collection = get_collection()
    all_data = collection.get(include=["documents", "metadatas"])
    if not all_data["ids"]:
        return []

    if _use_local():
        # TF-IDF 本地模式：将 query 与全库文档一起 fit，确保词汇表一致，然后手动计算相似度
        import numpy as np

        all_texts = all_data["documents"]
        vectorizer = _get_local_embed_fn()
        combined_matrix = vectorizer.fit_transform([query] + all_texts)
        combined_vecs = _pad_vectors(combined_matrix.toarray().tolist(), _FIXED_DIM)
        query_vec = np.array(combined_vecs[0])
        doc_vecs = np.array(combined_vecs[1:])

        # 余弦相似度
        q_norm = np.linalg.norm(query_vec) + 1e-8
        d_norms = np.linalg.norm(doc_vecs, axis=1) + 1e-8
        similarities = np.dot(doc_vecs, query_vec) / (d_norms * q_norm)

        # 排序取 top_k
        indices = np.argsort(similarities)[::-1][:top_k]

        items: list[dict] = []
        for idx in indices:
            sim = float(similarities[idx])
            if sim < similarity_threshold:
                continue
            items.append({
                "content": all_data["documents"][idx],
                "source": all_data["metadatas"][idx].get("source", ""),
                "similarity": sim,
                "distance": 1.0 - sim,
            })
        return items
    else:
        # 远程 API 模式：使用 ChromaDB 内置查询
        query_embedding = embed_texts([query])[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        items: list[dict] = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i] if results["distances"] else 1.0
                similarity = 1.0 - distance
                if similarity < similarity_threshold:
                    continue
                items.append({
                    "content": results["documents"][0][i],
                    "source": results["metadatas"][0][i].get("source", ""),
                    "distance": distance,
                    "similarity": similarity,
                })
        return items


def get_collection_stats() -> dict:
    collection = get_collection()
    return {
        "total_chunks": collection.count(),
        "sources": len({m["source"] for m in collection.get(include=["metadatas"])["metadatas"]}),
    }


def delete_document(filename: str) -> None:
    collection = get_collection()
    results = collection.get(where={"source": filename})
    if results["ids"]:
        collection.delete(ids=results["ids"])
