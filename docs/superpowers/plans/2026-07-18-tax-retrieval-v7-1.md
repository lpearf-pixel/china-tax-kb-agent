# 中国税务知识库 Agent V7.1 检索增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不削弱时间、地域、效力和A级证据门禁的前提下，将 V7.0 的单次 BM25 检索升级为查询拆解、混合召回、证据角色分组、关系扩展、确定性重排序和版本感知检索。

**Architecture:** 新增独立的 `apps/tax_retrieval` 包，向 V7 决策核心提供 `EvidenceBundle`。检索先执行硬元数据门禁，再分别运行 BM25 与标准库哈希向量召回，使用 RRF 融合并经过一跳关系扩展、证据分类、版本选择和确定性重排序。V6 旧 `EvidenceRetriever.search()` 通过适配器保持兼容。

**Tech Stack:** Python 3.10+ 标准库、现有 TaxKB 分块/BM25/元数据过滤、SHA256 哈希向量、余弦相似度、JSONL 索引、Obsidian Markdown。

## Global Constraints

- 正式结论只能使用目标日期有效的 A 级法规原文或条款卡。
- 向量相似度不得绕过时间、地域、税种、效力和证据等级过滤。
- 标准库环境必须完整可运行，不依赖云端模型或向量数据库。
- 外部 embedding provider 失败时自动回退本地哈希向量并记录 trace。
- 支持、限制、排除、历史、地方和冲突证据必须分别展示。
- 历史或废止文件不得作为当前业务支持证据。
- 现有 V6/V7 API 和 `EvidenceRetriever.search()` 必须兼容。
- 所有新增功能按 TDD 执行并保留可解释评分轨迹。

---

## 文件结构

```text
apps/tax_retrieval/
  __init__.py
  models.py
  query_planner.py
  vector_index.py
  fusion.py
  classifier.py
  relation_graph.py
  versioning.py
  reranker.py
  engine.py
  tests/

apps/tax_workbench/retrieval.py
apps/tax_workbench/models.py
apps/tax_workbench/planner.py
apps/tax_workbench/markdown.py
apps/tax_workbench/static/index.html
11-问题测试集/v7_1_retrieval_cases.jsonl
docs/V7-1-RETRIEVAL.md
```

### Task 1: 建立检索领域模型和查询计划

**Files:**
- Create: `apps/tax_retrieval/__init__.py`
- Create: `apps/tax_retrieval/models.py`
- Create: `apps/tax_retrieval/query_planner.py`
- Create: `apps/tax_retrieval/tests/test_query_planner.py`

**Interfaces:**
- Produces: `QuerySpec`, `QueryPlan`, `RetrievalCandidate`, `RetrievalTrace`, `EvidenceBundle`.
- Produces: `QueryPlanner.plan(facts: TaxFacts, issues: list[TaxIssue] | None = None) -> QueryPlan`.

- [ ] 写失败测试：新疆普通咨询必须生成 main、eligibility、limitation、exclusion、version、local 六类查询。
- [ ] 写失败测试：海南进口查询必须包含享惠主体、HS编码、一线二线、普通税制基线和人工复核词。
- [ ] 运行 `python3 -m unittest apps.tax_retrieval.tests.test_query_planner -v`，预期因模块不存在失败。
- [ ] 使用 dataclass 实现不可变查询模型；角色使用固定白名单。
- [ ] 实现确定性 QueryPlanner，并限制每个查询文本不超过500字符。
- [ ] 运行测试并提交 `feat: add deterministic tax query planner`。

### Task 2: 实现标准库哈希向量索引

**Files:**
- Create: `apps/tax_retrieval/vector_index.py`
- Create: `apps/tax_retrieval/tests/test_vector_index.py`

**Interfaces:**
- `HashingVectorizer(dimensions: int = 512).transform(text: str) -> list[float]`
- `HashingVectorIndex(docs).search(query: str, top_k: int) -> list[tuple[dict, float]]`
- `EmbeddingProvider` Protocol.

- [ ] 测试相同文本余弦为1，空文本不报错。
- [ ] 测试“减按百分之一”和“1%征收率”在向量召回中高于无关契税文本。
- [ ] 使用中文单字、二元、三元 token 和英文词 token。
- [ ] 使用 SHA256 映射固定维度与符号，L2归一化。
- [ ] provider 抛错时记录错误并回退本地索引。
- [ ] 运行测试并提交 `feat: add local hashing vector retrieval`。

### Task 3: 实现多查询召回和 RRF 融合

**Files:**
- Create: `apps/tax_retrieval/fusion.py`
- Create: `apps/tax_retrieval/engine.py`
- Create: `apps/tax_retrieval/tests/test_fusion.py`

**Interfaces:**
- `rrf_fuse(rankings, k=60) -> dict[str, float]`
- `HybridRetrievalEngine.recall(plan, docs, per_query_k=20) -> list[RetrievalCandidate]`.

- [ ] 测试一个候选同时被 BM25 与向量命中时排名高于单路命中。
- [ ] 测试多个子查询命中原因全部保留。
- [ ] 先通过 `filter_docs` 执行硬门禁，再运行召回。
- [ ] 每个子查询独立执行 BM25 和向量检索。
- [ ] 使用 RRF，不直接相加原始分数。
- [ ] 运行测试并提交 `feat: add hybrid multi-query retrieval`。

### Task 4: 实现证据角色分类和关系扩展

**Files:**
- Create: `apps/tax_retrieval/classifier.py`
- Create: `apps/tax_retrieval/relation_graph.py`
- Create: `apps/tax_retrieval/tests/test_classifier.py`
- Create: `apps/tax_retrieval/tests/test_relation_graph.py`

**Interfaces:**
- `EvidenceClassifier.classify(candidate, target_jurisdiction) -> tuple[str, list[str]]`
- `RelationGraph.build(vault, docs) -> RelationGraph`
- `RelationGraph.neighbors(candidate, max_hops=1) -> list[str]`.

- [ ] 测试“除销售出租不动产外”分类为 exclusion。
- [ ] 测试“必须核验同期间全部销售额”分类为 limitation。
- [ ] 测试 repealed 文件分类为 historical。
- [ ] 测试 CN-HI 文件在海南查询中分类为 local。
- [ ] 从 document_id、provision_id、source_note、related_provisions 和 Wikilink 建一跳图。
- [ ] 扩展候选重新通过硬门禁并记录 relation_reason。
- [ ] 运行测试并提交 `feat: classify and expand legal evidence`。

### Task 5: 实现版本选择、去重和确定性重排序

**Files:**
- Create: `apps/tax_retrieval/versioning.py`
- Create: `apps/tax_retrieval/reranker.py`
- Create: `apps/tax_retrieval/tests/test_versioning.py`
- Create: `apps/tax_retrieval/tests/test_reranker.py`

**Interfaces:**
- `VersionResolver.resolve(candidates, valid_on, historical_requested) -> list[RetrievalCandidate]`
- `DeterministicReranker.rank(candidates, plan, top_k) -> list[RetrievalCandidate]`.

- [ ] 测试同 provision_id 的两个版本只选择目标日期有效且最新生效版本。
- [ ] 测试废止版本不进入当前 support。
- [ ] 测试条款卡优先于概念卡和案例卡。
- [ ] 实现 RRF、精确命中、角色覆盖、地域、A级、条款层、关系和长度特征。
- [ ] 输出完整 `score_breakdown`。
- [ ] 路径级和 provision_id 级双重去重。
- [ ] 运行测试并提交 `feat: add version-aware legal reranking`。

### Task 6: 集成 EvidenceBundle 与 V7 决策核心

**Files:**
- Modify: `apps/tax_retrieval/engine.py`
- Modify: `apps/tax_workbench/retrieval.py`
- Modify: `apps/tax_workbench/models.py`
- Modify: `apps/tax_workbench/planner.py`
- Create: `apps/tax_workbench/tests/test_retrieval_v7_1.py`

**Interfaces:**
- `HybridRetrievalEngine.search_bundle(facts, issues=None, top_k=8) -> EvidenceBundle`
- `EvidenceRetriever.search_bundle(...) -> EvidenceBundle`
- `EvidenceRetriever.search(...) -> list[EvidenceItem]` remains compatible.

- [ ] 旧 `search()` 返回至少一条有效A级证据并保持字段兼容。
- [ ] 新 bundle 分别返回支持、限制、排除和地方证据。
- [ ] `PlanningResult` 新增 `evidence_groups` 与 `retrieval_trace` 默认字段。
- [ ] 没有 support 时保持失败关闭和人工复核。
- [ ] limitation/exclusion 写入风险，但不自动替代规则引擎结论。
- [ ] 持久案件保存 `retrieval-vNNN.json`。
- [ ] 运行 V6/V7兼容测试并提交 `feat: connect hybrid evidence bundles to V7`。

### Task 7: 升级报告、页面和检索评测

**Files:**
- Modify: `apps/tax_workbench/markdown.py`
- Modify: `apps/tax_workbench/static/index.html`
- Create: `11-问题测试集/v7_1_retrieval_cases.jsonl`
- Create: `apps/tax_retrieval/tests/test_retrieval_corpus.py`
- Create: `docs/V7-1-RETRIEVAL.md`

- [ ] 报告分别展示支持、限制、排除、历史、地方和冲突证据。
- [ ] 页面展示子查询、召回来源、最终分数和评分构成。
- [ ] 建立至少30个检索回归用例。
- [ ] 测试角色准确率、版本选择、top-k召回和失败关闭。
- [ ] 文档说明本地哈希向量的能力边界和可选 provider。
- [ ] 运行测试并提交 `docs: document V7.1 retrieval and evaluation`。

### Task 8: 完整回归与堆叠 Draft PR

**Files:**
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Create: `10-法规更新记录/发布记录/2026-07-18_V7.1检索增强开发候选.md`

- [ ] 执行：

```bash
python3 -m compileall apps/tax_retrieval apps/tax_decision_core apps/tax_workbench
python3 -m unittest discover -s 90-工具/tests -v
python3 -m unittest discover -s apps/tax_decision_core/tests -v
python3 -m unittest discover -s apps/tax_retrieval/tests -v
python3 -m unittest discover -s apps/tax_workbench/tests -v
python3 90-工具/taxkb_validate.py --report /tmp/taxkb-validation.md
python3 90-工具/taxkb_export.py --profile full --output /tmp/taxkb-chunks.jsonl
python3 90-工具/taxkb_eval.py --chunks /tmp/taxkb-chunks.jsonl --report /tmp/taxkb-eval.md
```

- [ ] 验证现有17题 Hit@5 仍为100%。
- [ ] 验证30个V7.1检索用例全部通过。
- [ ] 创建基于 `agent/tax-decision-core-v7` 的堆叠 Draft PR。
- [ ] 记录 GitHub Actions Runner 零步骤失败门禁，不绕过、不合并。
