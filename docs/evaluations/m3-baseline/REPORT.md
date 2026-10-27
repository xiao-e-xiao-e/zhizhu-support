# M3 真实模型评估基线

模型：deepseek-v4-flash；嵌入：BAAI/bge-small-zh-v1.5；开始时间：2026-10-26T02:25:26.303027+00:00。

合成 Atlas 支持政策，2.0 与 3.0 使用冲突数值；独立 SQLite、原始文件目录及 Chroma。全部资料经后台入库和发布。没有读取真实用户会话。

| 指标 | 实测 |
|---|---:|
| completed | 60 |
| errors | 0 |
| recall_at_5 | 1.0 |
| raw_recall_at_5 | 1.0 |
| mrr | 0.9295 |
| fact_coverage | 1.0 |
| all_facts_present | 1 |
| expected_refusal_pass | 1 |
| answerable_valid_citation_rate | 1 |
| latency_p50_ms | 1761.1 |
| latency_p95_ms | 4299.1 |
| generation_tokens | 23815 |
| rewrite_tokens | 1482 |
| multi_turn_raw_recall | 1.0 |
| multi_turn_rewritten_recall | 1.0 |
| rewrite_fallbacks | 0 |

开发集和验收标签分别统计（本轮均为同组合成资料，不是独立业务盲测）：

| 标签 | 题数 | Recall@5 | 事实覆盖率 | 拒答检测 |
|---|---:|---:|---:|---:|
| development | 4 | 1.0 | 1.0 | None |
| acceptance | 56 | 1.0 | 1.0 | 1 |

## 方法与限制

Recall@5 按固定期望文件命中计算；MRR 按首次命中排名计算。关键事实覆盖率使用人工定义词组的字符串检测，拒答使用固定词组检测，引用仅校验资料编号。以上自动指标不能代表人工语义正确率，也不能保证没有幻觉。相同模型/参数仍可能有波动。

全部数据为合成资料，尚需在真实业务资料与独立验收问题上开展人工复核。费用未按未知套餐估算；token 以供应商返回用量记录。耗时包含改写、检索及生成，不包含额外的原始检索对照。

## 需要复核的用例


逐题实际回答、改写、片段、引用、耗时、用量见 results.jsonl；运行配置和数据集校验和见 metadata.json。
