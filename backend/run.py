"""开发启动脚本。

用法：
    cd backend
    .venv/Scripts/python.exe run.py
"""
from __future__ import annotations

import uvicorn

from app.core.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
