"""会话持久化：JSON 文件 + 原子写入。

相比原实现（直接 write_text 覆盖）：
- 写临时文件再 os.replace，避免写一半进程退出导致 JSON 损坏
- 加进程内锁，避免并发请求互相覆盖
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..core.config import get_settings

logger = logging.getLogger(__name__)

_lock = threading.RLock()


def _path() -> Path:
    return get_settings().sessions_file


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_all() -> dict[str, dict]:
    path = _path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("会话文件读取失败，按空处理: %s", exc)
        return {}

    # 兼容旧格式 {"名称": [消息...]}
    normalized: dict[str, dict] = {}
    for name, value in raw.items():
        if isinstance(value, list):
            normalized[name] = {
                "created_at": "",
                "updated_at": "",
                "messages": value,
            }
        elif isinstance(value, dict):
            normalized[name] = {
                "created_at": value.get("created_at", ""),
                "updated_at": value.get("updated_at", ""),
                "messages": value.get("messages", []),
            }
    return normalized


def _write_all(data: dict[str, dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, path)


def list_sessions() -> list[dict]:
    with _lock:
        data = load_all()
    rows = [
        {
            "name": name,
            "message_count": len(payload.get("messages", [])),
            "created_at": payload.get("created_at", ""),
            "updated_at": payload.get("updated_at", ""),
        }
        for name, payload in data.items()
    ]
    return sorted(rows, key=lambda r: r["updated_at"] or "", reverse=True)


def get_session(name: str) -> dict | None:
    with _lock:
        data = load_all()
    payload = data.get(name)
    if payload is None:
        return None
    return {"name": name, **payload}


def save_session(name: str, messages: list[dict]) -> dict:
    with _lock:
        data = load_all()
        existing = data.get(name, {})
        payload = {
            "created_at": existing.get("created_at") or _now(),
            "updated_at": _now(),
            "messages": messages,
        }
        data[name] = payload
        _write_all(data)
    return {"name": name, **payload}


def append_messages(name: str, messages: list[dict]) -> dict:
    """追加消息到已有会话（不存在则创建）。"""
    with _lock:
        data = load_all()
        existing = data.get(name, {})
        merged = list(existing.get("messages", [])) + list(messages)
        payload = {
            "created_at": existing.get("created_at") or _now(),
            "updated_at": _now(),
            "messages": merged,
        }
        data[name] = payload
        _write_all(data)
    return {"name": name, **payload}


def delete_session(name: str) -> bool:
    with _lock:
        data = load_all()
        if name not in data:
            return False
        data.pop(name)
        _write_all(data)
    return True


def export_markdown(name: str) -> str | None:
    session = get_session(name)
    if session is None:
        return None

    lines = [
        f"# {name}",
        "",
        f"导出时间：{_now()}",
        "",
    ]
    for message in session["messages"]:
        role = "👤 用户" if message.get("role") == "user" else "🤖 助手"
        lines.append(f"## {role}")
        lines.append("")
        lines.append(message.get("content", ""))
        lines.append("")
        sources = message.get("sources") or []
        if sources:
            lines.append(f"> 参考来源：{', '.join(sources)}")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)
