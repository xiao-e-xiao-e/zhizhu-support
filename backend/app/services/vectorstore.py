"""向量存储层：ChromaDB 持久化集合 + 余弦距离空间。

对应缺陷修复 #2 与 #3：
    #2 原实现在检索时把全库文档拉出来重新拟合 TF-IDF，ChromaDB 的
       ANN 索引从未被使用，向量库退化成「带元数据的文档存储器」。
       现在统一走 collection.query()，HNSW 索引真正生效，检索复杂度
       从 O(N) 全量扫描降为近似最近邻查询。
    #3 原实现用 1 - distance 当相似度，但集合默认是 L2 空间，
       L2 距离无上界，换算出的「相似度」可以为负、且与余弦无关。
       现在显式声明 hnsw:space=cosine，1 - distance 就是余弦相似度。
"""
from __future__ import annotations

import logging
import threading

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..core.config import get_settings
from .embedding import get_embedding_service

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None
_lock = threading.Lock()


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                settings = get_settings()
                settings.chroma_dir.mkdir(parents=True, exist_ok=True)
                _client = chromadb.PersistentClient(
                    path=str(settings.chroma_dir),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
    return _client


_ENSURED = False


def get_collection() -> chromadb.Collection:
    """获取集合，并确保它使用余弦距离空间。

    坑：`get_or_create_collection` 对已存在的集合会忽略新传入的 metadata，
    所以老库（旧版用默认 L2 空间建的）不会被自动升级，
    `1 - distance` 的换算会继续错下去且毫无提示。这里显式校验：

    - 空间已是 cosine          → 直接用
    - 空间不是 cosine 但集合为空 → 删除重建（无数据损失）
    - 空间不是 cosine 且非空     → 直接报错，绝不静默删数据
    """
    global _ENSURED

    settings = get_settings()
    client = get_client()
    collection = client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    if _ENSURED:
        return collection

    space = (collection.metadata or {}).get("hnsw:space", "l2")
    if space == "cosine":
        _ENSURED = True
        return collection

    count = collection.count()
    if count > 0:
        raise RuntimeError(
            f"集合 {collection.name} 当前是 {space} 距离空间，与代码要求的 cosine 不一致，"
            f"且其中已有 {count} 条数据。请手动迁移，或修改 COLLECTION_NAME 换一个新集合。"
        )

    logger.warning(
        "集合 %s 使用 %s 距离空间且为空，重建为 cosine", collection.name, space
    )
    client.delete_collection(collection.name)
    collection = client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    _ENSURED = True
    return collection


def describe_collection() -> dict:
    """诊断用：返回集合的距离空间与规模。"""
    collection = get_collection()
    metadata = collection.metadata or {}
    return {
        "name": collection.name,
        "count": collection.count(),
        "space": metadata.get("hnsw:space", "l2"),
        "metadata": metadata,
    }


def add_documents(filename: str, chunks: list[str]) -> int:
    """把一批 chunk 编码后写入集合。同名文件按 source 幂等覆盖。"""
    if not chunks:
        return 0

    collection = get_collection()
    embeddings = get_embedding_service().embed_documents(chunks)

    # 幂等：先按 source 清掉旧版本。原实现只按固定 id 清，
    # 当同一文件重新上传且分块数变多时会残留旧 chunk。
    existing = collection.get(where={"source": filename})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])

    collection.add(
        ids=[f"{filename}::chunk::{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=chunks,
        metadatas=[{"source": filename, "chunk_index": i} for i in range(len(chunks))],
    )
    return len(chunks)


def search(
    query: str,
    top_k: int = 5,
    similarity_threshold: float = 0.0,
) -> list[dict]:
    """语义检索。返回按相似度降序排列的片段。"""
    collection = get_collection()
    total = collection.count()
    if total == 0:
        return []

    query_vector = get_embedding_service().embed_query(query)

    result = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, total),
        include=["documents", "metadatas", "distances"],
    )

    ids = result["ids"][0] if result["ids"] else []
    documents = result["documents"][0] if result["documents"] else []
    metadatas = result["metadatas"][0] if result["metadatas"] else []
    distances = result["distances"][0] if result["distances"] else []

    items: list[dict] = []
    for i, chunk_id in enumerate(ids):
        distance = float(distances[i])
        # cosine 空间下 distance = 1 - cos(θ)，故 1 - distance 即余弦相似度
        similarity = 1.0 - distance
        if similarity < similarity_threshold:
            continue
        meta = metadatas[i] or {}
        items.append(
            {
                "id": chunk_id,
                "content": documents[i],
                "source": meta.get("source", ""),
                "chunk_index": meta.get("chunk_index", i),
                "similarity": round(similarity, 4),
                "distance": round(distance, 4),
            }
        )
    return items


def list_documents() -> list[dict]:
    """列出已入库文件及其分块数。"""
    collection = get_collection()
    data = collection.get(include=["metadatas"])
    counter: dict[str, int] = {}
    for meta in data["metadatas"] or []:
        source = (meta or {}).get("source", "")
        if source:
            counter[source] = counter.get(source, 0) + 1
    return [
        {"source": name, "chunks": count}
        for name, count in sorted(counter.items())
    ]


def get_document_chunks(filename: str) -> list[dict]:
    """取某个文件的全部分块，按 chunk_index 排序。"""
    collection = get_collection()
    data = collection.get(
        where={"source": filename},
        include=["documents", "metadatas"],
    )
    rows = []
    for i, doc in enumerate(data["documents"] or []):
        meta = (data["metadatas"] or [])[i] or {}
        rows.append(
            {
                "chunk_index": meta.get("chunk_index", i),
                "content": doc,
            }
        )
    return sorted(rows, key=lambda r: r["chunk_index"])


def delete_document(filename: str) -> int:
    """删除某文件的全部分块，返回删除数量。"""
    collection = get_collection()
    existing = collection.get(where={"source": filename})
    ids = existing["ids"] or []
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def get_stats() -> dict:
    collection = get_collection()
    meta = collection.metadata or {}
    return {
        "total_chunks": collection.count(),
        "sources": len(list_documents()),
        "space": meta.get("hnsw:space", "l2"),
        "embedding_model": get_embedding_service().model_name,
    }
