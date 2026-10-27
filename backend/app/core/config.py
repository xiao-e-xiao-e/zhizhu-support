"""应用配置：统一从项目根目录的 .env 读取，支持环境变量覆盖。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
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

    # 本地开发使用 SQLite，生产通过环境变量切换到 PostgreSQL。
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'storage' / 'app.db').as_posix()}"
    app_env: str = "development"
    cookie_secure: bool = False
    session_hours: int = 12
    warmup_on_startup: bool = True
    max_upload_mb: int = 20
    document_storage_dir: Path = BACKEND_DIR / "storage" / "documents"
    chroma_host: str | None = None
    chroma_port: int = Field(8000, ge=1, le=65535)
    job_lease_seconds: int = 120
    job_poll_seconds: float = Field(2.0, ge=0.2, le=60)
    query_rewrite_enabled: bool = True
    rewrite_max_tokens: int = Field(160, ge=64, le=512)
    deepseek_thinking: bool = False
    agent_max_steps: int = Field(6, ge=1, le=12)
    agent_max_rounds: int = Field(4, ge=1, le=6)
    agent_timeout_seconds: int = Field(60, ge=10, le=120)
    agent_call_timeout_seconds: int = Field(15, ge=1, le=30)
    agent_token_budget: int = Field(16000, ge=2000, le=32000)
    demo_mode: bool = False

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.app_env not in {"development", "test", "production"}:
            raise ValueError("APP_ENV 必须是 development、test 或 production")
        if not 1 <= self.session_hours <= 168:
            raise ValueError("SESSION_HOURS 必须在 1 至 168 之间")
        if not 1 <= self.max_upload_mb <= 100:
            raise ValueError("MAX_UPLOAD_MB 必须在 1 至 100 之间")
        if not 15 <= self.job_lease_seconds <= 3600:
            raise ValueError("JOB_LEASE_SECONDS 必须在 15 至 3600 之间")
        if self.app_env == "production":
            if self.demo_mode:
                raise ValueError("生产环境不能启用 DEMO_MODE，请关闭公开演示账号")
            if not self.cookie_secure:
                raise ValueError("生产环境必须启用 COOKIE_SECURE")
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("生产环境必须使用 PostgreSQL psycopg 数据库")
            if "*" in self.cors_origin_list:
                raise ValueError("生产环境不允许通配符来源")
            if not self.cors_origin_list or any(not origin.startswith("https://") for origin in self.cors_origin_list):
                raise ValueError("生产环境必须配置 HTTPS 来源")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_ready(self) -> bool:
        return bool(self.api_key and self.api_key != "your_api_key_here")


@lru_cache
def get_settings() -> Settings:
    return Settings()
