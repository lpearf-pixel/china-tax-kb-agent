# V7.2 多税种联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持增值税行为兼容的前提下，增加企业所得税法源、规则、议题、计算和增值税联动方案。

**Architecture:** 企业所得税作为独立税种模块接入现有事实图谱、规则 DSL 和计算结果模型。多税种聚合层只汇总各税种计算结果和风险，不改写税种内部公式；旧请求默认仅分析增值税。

**Tech Stack:** Python 3 标准库、Decimal、JSON-compatible YAML、Obsidian Markdown、unittest、GitHub Actions。

## Global Constraints

- 正式结论只使用目标日期有效的 A 级法规和条款。
- 所有金额使用 `Decimal`，税额按 `ROUND_HALF_UP` 保留到分。
- 未声明 `requested_tax_types` 时默认为 `增值税`。
- 个人独资企业、合伙企业和非居民企业不由本阶段输出确定性企业所得税税额。
- 2023—2027 小型微利优惠不得延伸到 2028 年。
- 跨境、关联、重组、清算、房地产及专项优惠强制人工复核。
- 真实案件继续只保存在本地 `cases/`，不提交 Git。

---

### Task 1: 企业所得税 A 级法源和条款卡

**Files:**
- Create: `01-法规原文/国家/企业所得税/中华人民共和国企业所得税法.md`
- Create: `01-法规原文/国家/企业所得税/中华人民共和国企业所得税法实施条例_2024修订.md`
- Create: `01-法规原文/国家/企业所得税/小型微利企业优惠延续_2023年第12号.md`
- Create: `01-法规原文/国家/企业所得税/小型微利企业优惠征管_2023年第6号.md`
- Create: `02-条款结构/企业所得税/企业所得税法_第一至四条_纳税人与税率.md`
- Create: `02-条款结构/企业所得税/企业所得税法_第五条_应纳税所得额.md`
- Create: `02-条款结构/企业所得税/2023年第12号_小型微利企业优惠.md`
- Create: `02-条款结构/企业所得税/2023年第6号_小型微利企业征管.md`
- Test: `90-工具/tests/test_cit_vault_content.py`

**Interfaces:**
- Produces document IDs: `DOC-CN-CIT-LAW-2018`, `DOC-CN-CIT-REG-2024`, `DOC-CN-CIT-MOF-STA-2023-12`, `DOC-CN-CIT-STA-2023-6`.
- Produces provision IDs: `PROV-CIT-LAW-001-004`, `PROV-CIT-LAW-005`, `PROV-CIT-SME-2023-12`, `PROV-CIT-SME-ADMIN-2023-6`.

- [ ] **Step 1:** 写失败测试，断言四张法规卡和四张条款卡存在、元数据完整、文号和有效期正确。
- [ ] **Step 2:** 运行 `python3 -m unittest 90-工具.tests.test_cit_vault_content -v`，确认因文件缺失失败。
- [ ] **Step 3:** 创建法规卡和条款卡，明确一般 25% 税率、应纳税所得额、小型微利条件和 2027-12-31 到期日。
- [ ] **Step 4:** 运行专项测试和 `python3 90-工具/taxkb_validate.py`，预期 0 错误、0 警告。
- [ ] **Step 5:** 提交 `content: add enterprise income tax legal baseline`。

### Task 2: 请求模型与 V6→V7.2 事实适配

**Files:**
- Modify: `apps/tax_workbench/models.py`
- Modify: `apps/tax_decision_core/v6_adapter.py`
- Modify: `apps/tax_decision_core/fact_graph.py`
- Test: `apps/tax_decision_core/tests/test_cit_fact_adapter.py`

**Interfaces:**
- Produces `TaxFacts.requested_tax_types: list[str]`.
- Produces fact IDs: `cit.entity_form`, `cit.resident_status`, `cit.accounting_profit`, `cit.adjustment_increase`, `cit.adjustment_decrease`, `cit.loss_carryforward`, `cit.tax_credit`, `cit.prepaid_tax`, `cit.employee_count_avg`, `cit.asset_total_avg`, `cit.restricted_industry`, `cit.has_unincorporated_branches`.

- [ ] **Step 1:** 写失败测试，覆盖旧请求默认仅增值税、多税种请求 Decimal 归一化和事实图谱映射。
- [ ] **Step 2:** 运行专项测试，确认缺少字段和映射失败。
- [ ] **Step 3:** 最小实现新字段、校验、序列化和适配器映射。
- [ ] **Step 4:** 扩展局部重算依赖：企业所得税事实修改重跑 `issues/rules/calculation/scenarios`，业务日期修改仍重跑证据。
- [ ] **Step 5:** 运行 V7 与工作台回归。
- [ ] **Step 6:** 提交 `feat: add enterprise income tax facts`。

### Task 3: 企业所得税议题树

**Files:**
- Create: `apps/tax_decision_core/cit_issues.py`
- Test: `apps/tax_decision_core/tests/test_cit_issues.py`

**Interfaces:**
- Produces `CitIssueEngine.identify(case: CaseRecord, facts: FactGraph) -> list[TaxIssue]`.

- [ ] **Step 1:** 写失败测试，覆盖公司制居民企业、个人独资/合伙排除、小型微利资格和非居民人工复核。
- [ ] **Step 2:** 运行测试，确认模块不存在。
- [ ] **Step 3:** 实现七类企业所得税议题及缺失事实列表。
- [ ] **Step 4:** 运行测试，预期全部通过。
- [ ] **Step 5:** 提交 `feat: add enterprise income tax issue tree`。

### Task 4: 企业所得税规则 DSL

**Files:**
- Create: `rules/CN/企业所得税/CIT-RESIDENT-GENERAL-RATE-25.yaml`
- Create: `rules/CN/企业所得税/CIT-SMALL-LOW-PROFIT-ELIGIBILITY-2023-2027.yaml`
- Create: `rules/CN/企业所得税/CIT-SMALL-LOW-PROFIT-TAXABLE-RATIO-2023-2027.yaml`
- Create: `rules/CN/企业所得税/CIT-SMALL-LOW-PROFIT-RATE-2023-2027.yaml`
- Create: `rules/CN/企业所得税/CIT-SOLE-PROP-PARTNERSHIP-EXCLUSION.yaml`
- Create: `rules/CN/企业所得税/CIT-NONRESIDENT-MANUAL-REVIEW.yaml`
- Test: `apps/tax_decision_core/tests/test_cit_rules.py`

**Interfaces:**
- Rule outcomes: `cit_tax_rate`, `cit_small_low_profit_eligible`, `cit_taxable_income_ratio`, `cit_taxpayer_excluded`, `cit_manual_review_required`.

- [ ] **Step 1:** 写失败测试，覆盖 25% 一般税率、5% 等效小型微利、超限不适用、2028 到期、个人独资/合伙排除和非居民复核。
- [ ] **Step 2:** 运行测试，确认规则未加载。
- [ ] **Step 3:** 创建六条规则并回链 A 级条款 ID。
- [ ] **Step 4:** 运行规则专项测试和既有规则安全测试。
- [ ] **Step 5:** 提交 `feat: add enterprise income tax rules`。

### Task 5: 企业所得税 Decimal 计算器

**Files:**
- Create: `apps/tax_decision_core/cit_calculator.py`
- Test: `apps/tax_decision_core/tests/test_cit_calculator.py`

**Interfaces:**
- `CitCalculationContext`：案件事实、规则结果和缴税日期。
- `CitCalculator.calculate(context) -> CalculationResult`.

- [ ] **Step 1:** 写失败测试：一般企业 100 万元税额 25 万元；小型微利税额 5 万元；亏损税额 0；税额抵免和预缴形成应补退候选；缺少利润时 unable_to_calculate。
- [ ] **Step 2:** 运行测试，确认模块不存在。
- [ ] **Step 3:** 实现公式、舍入、现金流事件和缺失事实。
- [ ] **Step 4:** 运行专项测试，预期全部通过。
- [ ] **Step 5:** 提交 `feat: add enterprise income tax calculator`。

### Task 6: 多税种方案聚合

**Files:**
- Modify: `apps/tax_decision_core/domain.py`
- Create: `apps/tax_decision_core/multitax.py`
- Modify: `apps/tax_decision_core/scenarios.py`
- Test: `apps/tax_decision_core/tests/test_multitax_aggregation.py`

**Interfaces:**
- Adds `Scenario.tax_breakdown: dict[str, Decimal]`.
- Produces `MultiTaxScenarioAggregator.combine(base_scenarios, shared_calculations) -> list[Scenario]`.

- [ ] **Step 1:** 写失败测试，覆盖增值税 + 企业所得税分项、合计、退税候选不跨税种抵减和风险传播。
- [ ] **Step 2:** 运行测试，确认字段和聚合器不存在。
- [ ] **Step 3:** 实现兼容序列化和聚合逻辑。
- [ ] **Step 4:** 运行场景评分与旧序列化回归。
- [ ] **Step 5:** 提交 `feat: aggregate multi-tax scenarios`。

### Task 7: 工作台、API 和 Obsidian 报告

**Files:**
- Modify: `apps/tax_workbench/planner.py`
- Modify: `apps/tax_workbench/models.py`
- Modify: `apps/tax_workbench/markdown.py`
- Modify: `apps/tax_workbench/static/index.html`
- Test: `apps/tax_workbench/tests/test_multitax_workbench.py`

**Interfaces:**
- `PlanningResult` 新增税种计算分组和方案税种分项。
- 旧 `/api/analyze` 请求继续默认仅增值税。

- [ ] **Step 1:** 写失败测试，覆盖旧请求兼容、企业所得税单税种、增值税 + 企业所得税、2028 优惠失效和报告分项。
- [ ] **Step 2:** 运行测试，确认未接入企业所得税。
- [ ] **Step 3:** 接入 `CitIssueEngine`、企业所得税规则、`CitCalculator` 和多税种聚合器。
- [ ] **Step 4:** 增加浏览器字段和税种分项展示。
- [ ] **Step 5:** 更新 Markdown 报告并保存企业所得税计算审计。
- [ ] **Step 6:** 运行工作台和 HTTP 生命周期测试。
- [ ] **Step 7:** 提交 `feat: expose multi-tax planning workbench`。

### Task 8: 回归语料、CI 和开发候选

**Files:**
- Create: `11-问题测试集/v7_2_cit_cases.jsonl`
- Create: `apps/tax_workbench/tests/test_v7_2_cit_corpus.py`
- Modify: `.github/workflows/verify.yml`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Create: `docs/V7-2-MULTITAX.md`
- Create: `10-法规更新记录/发布记录/2026-07-19_V7.2多税种开发候选.md`

- [ ] **Step 1:** 建立至少 20 个企业所得税与多税种回归场景。
- [ ] **Step 2:** 将企业所得税和多税种测试加入 CI。
- [ ] **Step 3:** 更新使用文档、路线图和已知边界。
- [ ] **Step 4:** 运行 compileall、TaxKB、V7、V7.1、V7.2、工作台、Vault、索引和原 17 题基线。
- [ ] **Step 5:** 创建基于 `agent/tax-retrieval-v7.1` 的堆叠 Draft PR。
- [ ] **Step 6:** 远程 CI 全绿后更新开发候选记录；不直接合并 main。
