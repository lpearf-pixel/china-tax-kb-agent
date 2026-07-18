# 中国税务知识库 Agent V7.0 税务决策核心实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 V6 的固定方案工作台升级为可审计、可版本化、可局部重算的增值税决策核心，覆盖全国规则及新疆、海南覆盖层。

**Architecture:** 新增独立的 `apps/tax_decision_core` 包，按事实图谱、议题树、规则 DSL、规则引擎、增值税计算、情景排序、案件状态机和法规影响传播拆分。V6 通过适配器调用 V7，不直接删除原工作台；规则和法规依据外置并进入 Git，案件运行数据默认保存在本地且被 Git 忽略。

**Tech Stack:** Python 3.10+ 标准库、`Decimal`、JSON 案件存储、受限 YAML 子集规则文件（第一阶段使用 JSON-compatible YAML，加载器禁止任意代码）、Obsidian Markdown、现有 TaxKB BM25/元数据过滤器。

## Global Constraints

- Obsidian 继续是人工维护的知识事实源，法规结论必须回链到 A 级法规原文或条款卡。
- 第一阶段只实现增值税、小规模纳税人、一般纳税人基础测算、全国、新疆和海南。
- 海南进口、HS 编码、享惠主体、加工增值、关联交易、历史补税、不动产、重组和稽查必须进入人工复核。
- 所有金额使用 `Decimal`，核心计算不得使用二进制浮点数。
- 规则 DSL 不得执行任意 Python、表达式求值或动态导入。
- 法规变化不得覆盖已批准历史案件；只标记受影响并生成重算建议。
- `cases/`、上传资料和生成会话默认不进入 Git。
- 新功能按 TDD 执行：先写失败测试，确认失败原因，再写最小实现并跑完整回归。

---

## 文件结构

```text
apps/tax_decision_core/
  __init__.py
  domain.py
  fact_graph.py
  issues.py
  rule_schema.py
  rule_loader.py
  rule_engine.py
  vat_calculator.py
  scenarios.py
  workflow.py
  impact.py
  storage.py
  v6_adapter.py
  tests/

rules/vat/national/
rules/vat/xinjiang/
rules/vat/hainan/
cases/.gitkeep
99-模板/V7案件报告模板.md
```

---

### Task 1: 建立领域模型和案件存储边界

**Files:**
- Create: `apps/tax_decision_core/__init__.py`
- Create: `apps/tax_decision_core/domain.py`
- Create: `apps/tax_decision_core/storage.py`
- Create: `apps/tax_decision_core/tests/test_domain.py`
- Create: `apps/tax_decision_core/tests/test_storage.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Fact`, `FactVersion`, `FactGraph`, `TaxIssue`, `RuleEvaluation`, `CalculationResult`, `Scenario`, `CaseRecord`, `CaseState`.
- Produces: `CaseStorage.create(case)`, `load(case_id)`, `write_version(case_id, kind, version, payload)`, `append_event(case_id, event)`.

- [ ] **Step 1:** 写领域模型失败测试，验证 Decimal、事实状态、案件状态和序列化恢复。
- [ ] **Step 2:** 运行 `python3 -m unittest apps.tax_decision_core.tests.test_domain -v`，预期因模块不存在失败。
- [ ] **Step 3:** 使用 `dataclass(slots=True)` 实现不可变领域模型和显式 `to_dict/from_dict`。
- [ ] **Step 4:** 写存储失败测试，验证 `case.json`、版本文件和 `timeline.jsonl`，且旧版本不可覆盖。
- [ ] **Step 5:** 使用临时文件 + `Path.replace()` 实现原子写入，并拒绝非法 case_id。
- [ ] **Step 6:** `.gitignore` 加入 `cases/*`，仅保留 `.gitkeep`。
- [ ] **Step 7:** 运行 Task 1 全部测试并提交 `feat: add V7 domain models and case storage`。

### Task 2: 实现事实图谱和事实版本影响集

**Files:**
- Create: `apps/tax_decision_core/fact_graph.py`
- Create: `apps/tax_decision_core/tests/test_fact_graph.py`

**Interfaces:**
- `FactGraphService.create_case(payload: dict) -> CaseRecord`
- `confirm_fact(case, fact_id, value, actor) -> FactVersion`
- `revise_fact(case, fact_id, value, actor) -> ImpactSet`
- `get_value(graph, path) -> object | MissingFact`

- [ ] 写多主体、交易、合同、发票流、资金流和货物流失败测试。
- [ ] 验证修改发票需求只影响优惠、计算和情景；修改业务日期影响证据、规则、计算和情景。
- [ ] 实现节点与关系类型白名单、事实版本、valid_time/system_time 和 `ImpactSet`。
- [ ] 运行测试并提交 `feat: add versioned tax fact graph`。

### Task 3: 建立受限规则 DSL、加载器和种子规则

**Files:**
- Create: `apps/tax_decision_core/rule_schema.py`
- Create: `apps/tax_decision_core/rule_loader.py`
- Create: `apps/tax_decision_core/tests/test_rule_schema.py`
- Create: `rules/vat/national/*.yaml`
- Create: `rules/vat/xinjiang/README.md`
- Create: `rules/vat/hainan/*.yaml`

**Interfaces:**
- `RuleDefinition.from_mapping(data) -> RuleDefinition`
- `RuleLoader.load(valid_on, jurisdiction, tax_type) -> list[RuleDefinition]`

- [ ] 测试缺少必填字段、非法操作符和 `python/eval/exec/import/expression/callable` 禁止键。
- [ ] 第一阶段规则文件使用 JSON-compatible YAML，由标准库 `json` 解析。
- [ ] 建立全国月/季/按次起征点、1%、不动产排除、500万元登记规则。
- [ ] 建立海南普通业务回落和特殊业务人工复核规则；新疆声明全国底座。
- [ ] 校验每条 `legal_basis` 在 Vault 存在并提交 `feat: externalize VAT rules into safe DSL`。

### Task 4: 实现规则引擎、缺失事实和冲突检测

**Files:**
- Create: `apps/tax_decision_core/rule_engine.py`
- Create: `apps/tax_decision_core/tests/test_rule_engine.py`

**Interfaces:**
- `RuleEngine.evaluate(rule, facts, valid_on) -> RuleEvaluation`
- `RuleEngine.evaluate_all(rules, facts, valid_on) -> EvaluationBundle`

- [ ] 测试季度24万元命中起征点。
- [ ] 测试缺少同期间全部销售额返回 `insufficient_facts`。
- [ ] 测试不动产排除规则优先于1%规则。
- [ ] 测试同优先级互斥 outcome 返回 `conflict`。
- [ ] 实现 `all/any/not`、比较操作符、全国+地区叠加和完整条件审计轨迹。
- [ ] 运行测试并提交 `feat: add deterministic VAT rule engine`。

### Task 5: 实现增值税计算与现金流时间轴

**Files:**
- Create: `apps/tax_decision_core/vat_calculator.py`
- Create: `apps/tax_decision_core/tests/test_vat_calculator.py`
- Create: `apps/tax_decision_core/config/rounding.json`

**Interfaces:**
- `VatCalculator.calculate(context) -> CalculationResult`

- [ ] 测试含税101万元按1%拆分不含税销售额和税额。
- [ ] 测试起征点候选且未放弃免税时税额为0。
- [ ] 测试放弃免税开专票后重新计算。
- [ ] 测试一般纳税人销项减进项基础计算和留抵/应纳状态。
- [ ] 使用 `Decimal` 和 `ROUND_HALF_UP` 到分，输出公式、规则引用、确定性状态和税款时间事件。
- [ ] 运行测试并提交 `feat: add auditable VAT calculator`。

### Task 6: 实现税务议题树和合法情景生成

**Files:**
- Create: `apps/tax_decision_core/issues.py`
- Create: `apps/tax_decision_core/scenarios.py`
- Create: `apps/tax_decision_core/tests/test_issues.py`
- Create: `apps/tax_decision_core/tests/test_scenarios.py`

**Interfaces:**
- `IssueEngine.identify(case) -> list[TaxIssue]`
- `ScenarioEngine.generate(case, issues, evaluations, calculations) -> list[Scenario]`
- `ScenarioEngine.rank(scenarios, objective) -> list[ScenarioScore]`

- [ ] 新疆普通咨询识别应税、身份、起征点、1%和开票议题。
- [ ] 海南进口识别普通税制基线、主体、HS编码、目录、流向和审签父子议题。
- [ ] 决策变量只允许发票选择、报价方式、收款开票节奏和未来自愿登记；不得改变真实交易事实。
- [ ] 方案评分展示税负、现金流、确定性、资料完备度、复杂度、争议风险和发票满足度。
- [ ] 运行测试并提交 `feat: generate evidence-backed tax scenarios`。

### Task 7: 实现案件状态机、checkpoint 和局部重算

**Files:**
- Create: `apps/tax_decision_core/workflow.py`
- Create: `apps/tax_decision_core/tests/test_workflow.py`

- [ ] 缺少业务日期不能进入 `evidence_ready`。
- [ ] 规则冲突必须进入 `human_review_pending`。
- [ ] 修改发票需求只重跑规则、计算和情景。
- [ ] 实现状态迁移表、节点输入摘要哈希、checkpoint 复用和 timeline 事件。
- [ ] 运行测试并提交 `feat: add stateful case workflow and replay`。

### Task 8: 实现法规变更影响传播

**Files:**
- Create: `apps/tax_decision_core/impact.py`
- Create: `apps/tax_decision_core/tests/test_impact.py`
- Modify: `90-工具/taxkb_impact.py`

- [ ] 起征点条款有效期变化应影响规则及引用案件。
- [ ] 已批准旧案件保留原规则版本，不自动覆盖。
- [ ] 实现 `provision_id → rule_id → case_id → scenario_id` 索引和机器可读 JSON 报告。
- [ ] 运行测试并提交 `feat: propagate law changes to historical cases`。

### Task 9: 兼容 V6 工作台并升级本地接口

**Files:**
- Create: `apps/tax_decision_core/v6_adapter.py`
- Create: `apps/tax_decision_core/tests/test_v6_adapter.py`
- Modify: `apps/tax_workbench/planner.py`
- Modify: `apps/tax_workbench/server.py`
- Modify: `apps/tax_workbench/static/index.html`
- Create: `99-模板/V7案件报告模板.md`

- [ ] V6 `TaxFacts` 转单主体 V7 图谱。
- [ ] V7 结果转换为现有 JSON/Markdown，同时新增 `case_id/issues/rule_trace/calculations/scenario_scores`。
- [ ] 增加案件读取、事实修改、重跑、审签和审计接口，仍只监听 `127.0.0.1`。
- [ ] 页面展示规则命中、计算公式、评分构成和案件时间线。
- [ ] 运行 V6/V7 测试并提交 `feat: connect V6 workbench to V7 decision core`。

### Task 10: 完整回归、文档和发布候选

**Files:**
- Modify: `.github/workflows/verify.yml`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Create: `docs/V7-DECISION-CORE.md`
- Create: `11-问题测试集/v7_decision_cases.jsonl`

- [ ] 建立至少20个决策回归：日期、地区、起征点、1%、不动产排除、专票、500万元、海南门禁、冲突和法规变化。
- [ ] 运行：

```bash
python3 -m unittest discover -s 90-工具/tests -v
python3 -m unittest discover -s apps/tax_workbench/tests -v
python3 -m unittest discover -s apps/tax_decision_core/tests -v
python3 90-工具/taxkb_validate.py --report /tmp/taxkb-validation.md
python3 90-工具/taxkb_export.py --profile full --output /tmp/taxkb-chunks.jsonl
python3 90-工具/taxkb_eval.py --chunks /tmp/taxkb-chunks.jsonl --report /tmp/taxkb-eval.md
```

- [ ] 端到端验证新疆季度24万元、海南普通咨询、海南进口资料不足、关联分拆和事实修改局部重算。
- [ ] 更新文档和 Draft PR，不直接合并 `main`。

## 验收标准

- 起征点和1%政策来自版本化规则文件，不再硬编码在 V6 planner。
- 修改金额、日期、发票需求或主体身份后，只重跑受影响节点。
- 每个计算值可追溯到事实版本、规则版本、法规条款和公式。
- 全国规则与新疆/海南覆盖不串区；海南普通业务不触发零关税。
- 冲突、资料不足和高风险事项不生成确定执行结论。
- 法规变化可标记受影响案件，但不覆盖历史批准方案。
- V5 TaxKB、V6 Workbench 和 V7 Decision Core 全部回归通过。
