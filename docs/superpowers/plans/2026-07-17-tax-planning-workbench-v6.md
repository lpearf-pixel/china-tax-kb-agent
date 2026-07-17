# 税务规划交互工作台 V6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在现有 Obsidian 税务知识库之上增加一个本地浏览器交互工作台，结构化收集税务事实，检索有效法规，生成可追溯的税务方案草案，并将高风险事项强制转人工审签。

**Architecture:** `apps/tax_workbench` 提供纯 Python 标准库的领域服务和 HTTP 服务器；前端是单页静态界面。领域服务复用 `90-工具/taxkb_core.py` 的条款分块、地域/时间过滤和 BM25 检索能力，输出结构化方案结果与 Markdown 归档，不直接修改正式法规知识层。

**Tech Stack:** Python 3.10+ 标准库、`http.server`、JSON、HTML/CSS/JavaScript、Obsidian Markdown、现有 TaxKB BM25 检索。

## Global Constraints

- 正式法规依据只能来自 A 级法规原文或条款结构层。
- 新疆查询保留全国 + 新疆；海南查询保留全国 + 海南。
- 业务日期、地域、主体和纳税人身份缺失时，不得输出确定税务结论。
- 海南普通境内业务不得自动适用自贸港零关税。
- 海南享惠主体、HS 编码、加工增值和岛内居民资格问题必须人工复核。
- 方案只能提供合法合规的结构、申报、发票和现金流选择，不得建议虚假合同、虚开发票或人为分拆。
- 默认不依赖外部 LLM；第一阶段方案生成必须在离线环境可复现。

---

### Task 1: 定义事实输入与分析结果模型

**Files:**
- Create: `apps/tax_workbench/__init__.py`
- Create: `apps/tax_workbench/models.py`
- Test: `apps/tax_workbench/tests/test_models.py`

**Interfaces:**
- Produces: `TaxFacts.from_dict(data) -> TaxFacts`
- Produces: `TaxFacts.validate() -> list[str]`
- Produces: `PlanningResult.to_dict() -> dict`

- [x] 写失败测试：必填事实、金额、日期、地域、海南特殊字段校验。
- [x] 运行测试确认失败。
- [x] 实现最小数据模型。
- [x] 运行测试确认通过。

### Task 2: 建立证据检索服务

**Files:**
- Create: `apps/tax_workbench/retrieval.py`
- Test: `apps/tax_workbench/tests/test_retrieval.py`

**Interfaces:**
- Consumes: `TaxFacts`
- Produces: `EvidenceRetriever.search(facts, top_k=8) -> list[EvidenceItem]`

- [x] 写失败测试：新疆保留 CN+CN-XJ、海南保留 CN+CN-HI、A 级证据优先、日期过滤。
- [x] 运行测试确认失败。
- [x] 复用 `taxkb_core` 实现索引构建和检索。
- [x] 运行测试确认通过。

### Task 3: 建立税务方案生成与风险门禁

**Files:**
- Create: `apps/tax_workbench/planner.py`
- Test: `apps/tax_workbench/tests/test_planner.py`

**Interfaces:**
- Consumes: `TaxFacts`, `list[EvidenceItem]`
- Produces: `TaxPlanningService.analyze(facts) -> PlanningResult`

- [x] 写失败测试：季度 24 万元小规模、3%减按1%、海南普通咨询、海南进口设备缺 HS 编码、分拆销售额风险。
- [x] 运行测试确认失败。
- [x] 实现合规基线、发票申报协同、身份评估三个方案模板。
- [x] 实现海南特殊门禁和人工审签标记。
- [x] 运行测试确认通过。

### Task 4: 输出 Markdown 并归档到 Obsidian

**Files:**
- Create: `apps/tax_workbench/markdown.py`
- Create: `16-交互工作台/README.md`
- Create: `16-交互工作台/会话记录模板.md`
- Test: `apps/tax_workbench/tests/test_markdown.py`

**Interfaces:**
- Produces: `render_markdown(result) -> str`
- Produces: `save_session(vault, facts, result) -> Path`

- [x] 写失败测试：输出包含结论、前提、法规依据、方案、风险、版本和核验日期。
- [x] 运行测试确认失败。
- [x] 实现 Markdown 渲染和唯一会话文件名。
- [x] 运行测试确认通过。

### Task 5: 增加本地浏览器交互界面

**Files:**
- Create: `apps/tax_workbench/server.py`
- Create: `apps/tax_workbench/static/index.html`
- Create: `apps/tax_workbench/README.md`
- Test: `apps/tax_workbench/tests/test_server.py`

**Interfaces:**
- `GET /health`
- `GET /api/schema`
- `POST /api/analyze`
- `POST /api/save`

- [x] 写失败测试：健康检查、无效 JSON、缺失事实、成功分析和保存。
- [x] 运行测试确认失败。
- [x] 实现 `ThreadingHTTPServer` 路由。
- [x] 实现事实表单、方案卡片、法规引用和风险提示 UI。
- [x] 运行测试确认通过。

### Task 6: 集成验证与文档

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/verify.yml`
- Create: `12-决策记录/架构决策记录_ADR-003_税务规划交互工作台.md`
- Create: `docs/ROADMAP.md` updates

- [x] 更新 README 启动命令与安全边界。
- [x] CI 增加 workbench 测试。
- [x] 运行全部 TaxKB 和 workbench 单元测试。
- [x] 运行 Vault 校验、索引导出和检索回归。
- [x] 提交开发分支并创建 Draft PR。
