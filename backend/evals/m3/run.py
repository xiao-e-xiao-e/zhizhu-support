"""真实模型回归：隔离数据库、原始文件及Chroma；可从JSONL断点继续。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


def normalize(value):
    return re.sub(r"\s+", "", value).lower()


def score(case, result):
    contexts, answer = result["contexts"], result["answer"]
    ranked = [r["source"] for r in contexts]
    expected = case["expected_sources"]
    hit = next((i + 1 for i, source in enumerate(ranked) if source in expected), 0)
    facts = case["facts"]
    coverage = (
        sum(any(normalize(word) in normalize(answer) for word in fact.split("|")) for fact in facts)
        / len(facts)
        if facts
        else None
    )
    citations = [int(n) for n in re.findall(r"\[资料(\d+)\]", answer)]
    refusal = any(
        p in answer
        for p in [
            "没有足够",
            "未提供",
            "未包含",
            "没有提供",
            "无法回答",
            "未找到",
            "没有找到",
            "没有相关",
            "无法提供",
            "未涉及",
            "没有记载",
            "资料不足",
        ]
    )
    return {
        "recall_at_5": float(bool(hit)) if expected else None,
        "mrr": 1 / hit if hit else 0 if expected else None,
        "fact_coverage": coverage,
        "all_facts_present": coverage == 1 if facts else None,
        "valid_citation": bool(citations) and all(1 <= n <= len(contexts) for n in citations),
        "refusal_detected": refusal,
        "expected_refusal_pass": refusal if case["unanswerable"] else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-real-model", action="store_true", help="明确启用付费远程模型调用")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3, choices=range(1, 5))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if not args.run_real_model:
        parser.error("需要 --run-real-model；该命令将调用服务端已配置的远程模型")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    dataset_path = Path(__file__).with_name("dataset.json")
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    scratch = BACKEND / "storage" / "evaluations" / str(uuid4())
    scratch.mkdir(parents=True)
    os.environ.update(
        DATABASE_URL=f"sqlite:///{(scratch / 'evaluation.db').as_posix()}",
        CHROMA_HOST="",
        CHROMA_DIR=str(scratch / "vectors"),
        DOCUMENT_STORAGE_DIR=str(scratch / "originals"),
        APP_ENV="test",
        WARMUP_ON_STARTUP="false",
    )
    from app.core.config import get_settings
    from app.core.database import session_factory
    from app.models import Product, ProductVersion, User
    from app.services import ingestion, knowledge, rag
    from app.services.embedding import get_embedding_service
    from manage import migrate

    settings = get_settings()
    migrate()
    with session_factory()() as db, db.begin():
        user = User(username="evaluation-system", password_hash="!disabled", role="admin")
        product = Product(name="Atlas", description="Synthetic evaluation only")
        db.add_all([user, product])
        db.flush()
        versions = {v: ProductVersion(product_id=product.id, name=v) for v in ["2.0", "3.0"]}
        db.add_all(versions.values())
    get_embedding_service().warmup()
    for doc in dataset["documents"]:
        uploaded = knowledge.enqueue(
            doc["source"], doc["content"].encode(), user.id, product.id, versions[doc["version"]].id
        )
        ingestion.run_once()
        history = knowledge.history(uploaded["document_id"])
        if history["revisions"][0]["state"] != "ready":
            raise RuntimeError("评估资料未成功入库")
        knowledge.change(
            uploaded["document_id"], "publish", user.id, history["revision"], uploaded["revision_id"]
        )
    jsonl = args.output / "results.jsonl"
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    meta_path = args.output / "metadata.json"
    metadata = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "dataset_sha256": digest,
        "system_prompt_sha256": hashlib.sha256(rag.SYSTEM_PROMPT.encode()).hexdigest(),
        "temperature": 0,
        "top_k": 5,
        "max_tokens": settings.max_tokens,
        "thinking": settings.deepseek_thinking,
        "workers": args.workers,
        "synthetic_documents": len(dataset["documents"]),
        "cases": len(dataset["cases"]),
        "scoring": "固定期望来源、关键事实词组及拒答词检测；不等价于人工语义正确率。引用仅验证编号有效，不验证蕴含。",
        "scratch_path": str(scratch),
        "query_rewrite_enabled": settings.query_rewrite_enabled,
        "rewrite_max_tokens": settings.rewrite_max_tokens,
        "rag_source_sha256": hashlib.sha256((BACKEND / "app/services/rag.py").read_bytes()).hexdigest(),
    }
    if meta_path.exists():
        prior = json.loads(meta_path.read_text(encoding="utf-8"))
        comparable = [
            "model",
            "embedding_model",
            "dataset_sha256",
            "system_prompt_sha256",
            "temperature",
            "top_k",
            "max_tokens",
            "thinking",
            "query_rewrite_enabled",
            "rewrite_max_tokens",
            "rag_source_sha256",
        ]
        if any(prior.get(key, metadata[key]) != metadata[key] for key in comparable):
            raise RuntimeError("输出目录的数据集、模型、提示词或参数不同，请换用新目录")
        metadata["started_at"] = prior["started_at"]
        metadata["resumed_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    previous = (
        [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        if jsonl.exists()
        else []
    )
    done = {r["id"] for r in previous}
    cases = dataset["cases"][: args.limit] if args.limit else dataset["cases"]

    def evaluate(case):
        start = time.perf_counter()
        try:
            scope = {"product_id": product.id, "version_id": versions[case["version"]].id}
            raw_hits = knowledge.search(case["question"], top_k=5, **scope)
            result = rag.ask(case["question"], temperature=0, history=case["history"], **scope)
            scores = score(case, result)
            scores["raw_recall_at_5"] = (
                float(any(h["source"] in case["expected_sources"] for h in raw_hits))
                if case["expected_sources"]
                else None
            )
            return {
                "id": case["id"],
                "category": case["category"],
                "split": case["split"],
                "version": case["version"],
                "question": case["question"],
                "expected_sources": case["expected_sources"],
                "expected_facts": case["facts"],
                "result": result,
                "scores": scores,
                "ok": True,
            }
        except Exception as exc:
            return {
                "id": case["id"],
                "category": case["category"],
                "ok": False,
                "error_type": type(exc).__name__,
                "latency_ms": round((time.perf_counter() - start) * 1000, 1),
            }

    rows = list(previous)
    with (
        ThreadPoolExecutor(max_workers=args.workers) as executor,
        jsonl.open("a", encoding="utf-8") as target,
    ):
        futures = [executor.submit(evaluate, c) for c in cases if c["id"] not in done]
        for future in as_completed(futures):
            row = future.result()
            target.write(json.dumps(row, ensure_ascii=False) + "\n")
            target.flush()
            rows.append(row)
            print(f"completed={len(rows)}/{len(cases)} id={row['id']} ok={row['ok']}", flush=True)
    report(rows, metadata, args.output)


def report(rows, metadata, output):
    good = [r for r in rows if r["ok"]]

    def average(key, subset=good):
        values = [r["scores"][key] for r in subset if r["scores"].get(key) is not None]
        return round(statistics.mean(values), 4) if values else None

    latencies = sorted(r["result"]["latency_ms"] for r in good)
    summary = {
        "completed": len(rows),
        "errors": len(rows) - len(good),
        **{
            key: average(key)
            for key in [
                "recall_at_5",
                "raw_recall_at_5",
                "mrr",
                "fact_coverage",
                "all_facts_present",
                "expected_refusal_pass",
            ]
        },
        "answerable_valid_citation_rate": average(
            "valid_citation", [r for r in good if r["expected_sources"]]
        ),
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        if latencies
        else None,
        "generation_tokens": sum(r["result"]["usage"]["total_tokens"] for r in good),
        "rewrite_tokens": sum(r["result"]["retrieval"]["tokens"] for r in good),
        "multi_turn_raw_recall": average(
            "raw_recall_at_5", [r for r in good if r["category"] == "multi_turn"]
        ),
        "multi_turn_rewritten_recall": average(
            "recall_at_5", [r for r in good if r["category"] == "multi_turn"]
        ),
        "rewrite_fallbacks": sum(r["result"]["retrieval"]["status"] == "fallback" for r in good),
    }
    summary["by_split"] = {
        split: {
            "cases": len(subset),
            "recall_at_5": average("recall_at_5", subset),
            "fact_coverage": average("fact_coverage", subset),
            "expected_refusal_pass": average("expected_refusal_pass", subset),
        }
        for split in ["development", "acceptance"]
        if (subset := [r for r in good if r["split"] == split])
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# M3 真实模型评估基线",
        "",
        f"模型：{metadata['model']}；嵌入：{metadata['embedding_model']}；开始时间：{metadata['started_at']}。",
        "",
        "合成 Atlas 支持政策，2.0 与 3.0 使用冲突数值；独立 SQLite、原始文件目录及 Chroma。全部资料经后台入库和发布。没有读取真实用户会话。",
        "",
        "| 指标 | 实测 |",
        "|---|---:|",
    ]
    lines += [f"| {key} | {value} |" for key, value in summary.items() if key != "by_split"]
    lines += [
        "",
        "开发集和验收标签分别统计（本轮均为同组合成资料，不是独立业务盲测）：",
        "",
        "| 标签 | 题数 | Recall@5 | 事实覆盖率 | 拒答检测 |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {split} | {metrics['cases']} | {metrics['recall_at_5']} | {metrics['fact_coverage']} | {metrics['expected_refusal_pass']} |"
        for split, metrics in summary["by_split"].items()
    ]
    lines += [
        "",
        "## 方法与限制",
        "",
        "Recall@5 按固定期望文件命中计算；MRR 按首次命中排名计算。关键事实覆盖率使用人工定义词组的字符串检测，拒答使用固定词组检测，引用仅校验资料编号。以上自动指标不能代表人工语义正确率，也不能保证没有幻觉。相同模型/参数仍可能有波动。",
        "",
        "全部数据为合成资料，尚需在真实业务资料与独立验收问题上开展人工复核。费用未按未知套餐估算；token 以供应商返回用量记录。耗时包含改写、检索及生成，不包含额外的原始检索对照。",
        "",
        "## 需要复核的用例",
        "",
    ]
    for row in rows:
        if (
            not row["ok"]
            or row["scores"].get("all_facts_present") is False
            or row["scores"].get("expected_refusal_pass") is False
            or row["scores"].get("recall_at_5") == 0
        ):
            lines.append(f"- {row['id']}：{row.get('scores', row.get('error_type'))}")
    lines += [
        "",
        "逐题实际回答、改写、片段、引用、耗时、用量见 results.jsonl；运行配置和数据集校验和见 metadata.json。",
        "",
    ]
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
