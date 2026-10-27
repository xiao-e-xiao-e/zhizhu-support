"""本地嵌入服务：基于 fastembed (ONNX Runtime)，无需 PyTorch。

设计要点（对应缺陷修复 #2）：
    入库与检索共用同一个模型实例、同一套编码流程，向量落在同一语义空间。
    这是原 TF-IDF 实现最致命的问题——每次入库都重建词汇表，
    导致库里历史向量与新增向量根本不可比。
"""
from __future__ import annotations

import logging
import threading

from ..core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """线程安全的本地嵌入服务，模型懒加载 + 双重检查锁。"""

    def __init__(self, model_name: str, cache_dir: str) -> None:
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._model = None
        self._dimension: int | None = None
        self._lock = threading.Lock()

    def _ensure_model(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    logger.info("正在加载嵌入模型 %s ...", self._model_name)
                    self._model = TextEmbedding(
                        model_name=self._model_name,
                        cache_dir=self._cache_dir,
                    )
                    logger.info("嵌入模型加载完成")
        return self._model

    def warmup(self) -> int:
        """预热模型并返回向量维度。"""
        model = self._ensure_model()
        probe = next(iter(model.embed(["预热"])))
        self._dimension = len(probe)
        return self._dimension

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            self.warmup()
        return self._dimension or 0

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量编码文档。"""
        if not texts:
            return []
        model = self._ensure_model()
        return [vec.tolist() for vec in model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        """编码查询。

        注：BGE 系列官方建议给 query 加指令前缀
        （"为这个句子生成表示以用于检索相关文章："）。
        本项目不启用该前缀，让 query 与 document 走完全对称的编码路径——
        对称编码的相似度数值更稳定、阈值更好解释，
        而 BGE 指令前缀带来的是几个点的召回提升，对本地小库收益有限。
        """
        model = self._ensure_model()
        return next(iter(model.embed([text]))).tolist()


_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _service
    if _service is None:
        settings = get_settings()
        _service = EmbeddingService(
            model_name=settings.embedding_model,
            cache_dir=str(settings.embedding_cache_dir),
        )
    return _service
