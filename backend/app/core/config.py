"""应用配置：统一从项目根目录的 .env 读取，支持环境变量覆盖。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- LLM ----
    api_key: str = ""
    api_base_url: str = "https://api.deepseek.com"
    chat_model: str = "deepseek-v4-flash"
    max_tokens: int = 1024

    # ---- 嵌入模型 ----
    # BAAI/bge-small-zh-v1.5：512 维中文语义向量，约 95MB，首次使用自动下载
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_cache_dir: Path = BACKEND_DIR / ".model_cache"

    # ---- RAG 默认参数（前端可逐次覆盖）----
    chunk_size: int = 500
    chunk_overlap: int = 100
    top_k: int = 5
    temperature: float = 0.3
    similarity_threshold: float = 0.0

    # ---- 存储路径 ----
    chroma_dir: Path = PROJECT_ROOT / "chroma_db"
    data_dir: Path = PROJECT_ROOT / "data"
    sessions_file: Path = PROJECT_ROOT / "chat_history.json"

    # ---- 服务 ----
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )

    collection_name: str = "knowledge_base"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_ready(self) -> bool:
        return bool(self.api_key and self.api_key != "your_api_key_here")


@lru_cache
def get_settings() -> Settings:
    return Settings()
