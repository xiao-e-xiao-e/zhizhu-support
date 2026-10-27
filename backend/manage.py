"""管理命令。密码交互输入，不接受命令行明文参数。"""

from __future__ import annotations

import argparse
import getpass
import json

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from app.core.auth import password_hasher
from app.core.config import BACKEND_DIR
from app.core.database import session_factory
from app.models import User
from app.routers.auth import CreateUserRequest
from app.schemas import SessionSaveRequest
from app.services import sessions


def migrate():
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


def main():
    parser = argparse.ArgumentParser(description="平台管理命令")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("migrate", help="升级数据库结构")
    sub.add_parser("unify-assistant-history", help="将原助手记录关联到统一对话历史，跳过已关联记录")
    sub.add_parser("adopt-legacy", help="登记旧向量资料，不修改原始内容")
    demo = sub.add_parser("seed-demo", help="显式初始化本地演示账号及虚构资料，保留已存在的编辑")
    demo.add_argument("--with-assistant", action="store_true", help="另执行两次真实只读助手任务，产生远程模型用量")
    business = sub.add_parser("prepare-business", help="将登记过的初始资源转换为普通业务账号、资料及真实问答")
    business.add_argument("--credentials-file", default="/app/storage/business-accounts.json")
    create = sub.add_parser("create-admin", help="创建管理员，交互输入密码")
    create.add_argument("--username", required=True)
    legacy = sub.add_parser("import-sessions", help="将旧 JSON 会话导入指定用户，跳过同名会话")
    legacy.add_argument("--username", required=True)
    legacy.add_argument("--file", required=True)
    args = parser.parse_args()
    if args.action == "migrate":
        migrate()
        print("数据库已升级")
        return
    if args.action == "create-admin":
        password = getpass.getpass("管理员密码（至少 12 位）：")
        if password != getpass.getpass("再次输入密码："):
            parser.error("两次密码不一致")
        payload = CreateUserRequest(username=args.username, password=password, role="admin")
        with session_factory()() as db, db.begin():
            if db.scalar(select(User).where(User.username == payload.username.lower())):
                parser.error("用户名已存在，不会覆盖原账号")
            db.add(
                User(
                    username=payload.username.lower(),
                    password_hash=password_hasher.hash(password),
                    role="admin",
                )
            )
        print("管理员已创建")
        return
    if args.action == "unify-assistant-history":
        from app.services.assistant_chat import adopt_history
        print(f"已关联 {adopt_history()} 条助手历史记录")
        return
    if args.action == "adopt-legacy":
        from app.services.knowledge import adopt_legacy
        print(f"已登记 {adopt_legacy()} 份旧资料")
        return
    if args.action == "prepare-business":
        from app.services.business_workspace import prepare
        print(json.dumps(prepare(args.credentials_file), ensure_ascii=False), flush=True)
        return
    if args.action == "seed-demo":
        from app.services.demo import seed_demo
        print("正在初始化演示资料并等待后台入库，不会覆盖已有业务账号或资料……", flush=True)
        result = seed_demo(with_assistant=args.with_assistant)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    with session_factory()() as db:
        user = db.scalar(select(User).where(User.username == args.username.lower()))
        if not user:
            parser.error("目标用户不存在")
    with open(args.file, encoding="utf-8") as source:
        raw = json.load(source)
    # 全量验证后再导入，避免格式错误时产生部分写入。
    validated = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not 1 <= len(name) <= 120:
            parser.error("旧会话名长度必须为 1 至 120")
        messages = value if isinstance(value, list) else value.get("messages", [])
        validated[name] = SessionSaveRequest(messages=messages)
    imported = 0
    for name, payload in validated.items():
        if sessions.get_session(user.id, name) is None:
            sessions.save_session(user.id, name, [m.model_dump() for m in payload.messages])
            imported += 1
    print(f"已导入 {imported} 个会话；同名会话跳过，原 JSON 文件保留")


if __name__ == "__main__":
    main()
