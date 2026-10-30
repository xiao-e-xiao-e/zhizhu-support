"""独立后台入库进程，SIGTERM 后完成当前任务再退出。"""

import logging
import signal
import threading
from uuid import uuid4

from app.core.config import get_settings
from app.services.ingestion import heartbeat, run_once


def main():
    settings = get_settings()
    if not settings.chroma_host:
        raise SystemExit("独立 worker 必须设置 CHROMA_HOST，与 API 连接同一 Chroma 服务")
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    worker_id = str(uuid4())

    def pulse():
        while not stop.is_set():
            try:
                heartbeat(worker_id)
            except Exception:
                logging.exception("worker 心跳失败")
            stop.wait(15)

    threading.Thread(target=pulse, daemon=True).start()
    while not stop.is_set():
        try:
            worked = run_once()
        except Exception:
            logging.exception("队列处理失败")
            worked = False
        if not worked:
            stop.wait(settings.job_poll_seconds)


if __name__ == "__main__":
    main()
