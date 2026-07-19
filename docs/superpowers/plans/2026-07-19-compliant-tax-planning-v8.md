# V8 合规税务筹划 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 V7.2.1 三税种确定性计算基础上，生成具有真实商业目的和经济实质的合法税务筹划方案，并自动淘汰逃税、虚假交易和滥用优惠路径。

**Architecture:** V8 新增筹划决策变量、商业目的、经济实质和反避税门禁层。候选方案必须先通过真实性与禁止模式检查，再调用现有分税种规则和计算器，最后比较税负、递延、现金流、成本和风险。

**Tech Stack:** Python 3 标准库、Decimal、JSON-compatible YAML、Obsidian Markdown、unittest、GitHub Actions。

## Global Constraints

- 正式名称使用“合规税务筹划”或“合法降负”，不以逃税或隐匿收入为目标。
- 禁止虚假合同、虚开发票、空壳迁移、人为分拆、两套账和个人账户收款等方案。
- 任何候选方案必须具有非税商业目的和可验证经济实质。
- 缺少 A 级法源、关键事实或证明资料时失败关闭。
- LLM 不得创造税率、优惠条件、交易事实或证明材料。
- 税负节省与纳税递延必须分开计算。
- 高风险、关联、跨境、重组和房地产方案强制人工审签。

---

### Task 1: 筹划领域模型和禁止模式

**Files:**
- Create: `apps/tax_decision_core/planning_domain.py`
- Create: `apps/tax_decision_core/planning_guard.py`
- Test: `apps/tax_decision_core/tests/test_planning_guard.py`

**Produces:**
- `PlanningObjective`
- `DecisionVariable`
- `BusinessPurposeAssessment`
- `SubstanceAssessment`
- `PlanningCandidate`
- `PlanningGuard.evaluate(candidate, facts)`

- [ ] 写失败测试，覆盖虚开发票、隐匿收入、空壳迁移、人为分拆、虚构劳务和关联资金空转。
- [ ] 实现禁止模式枚举和机器可读拒绝原因。
- [ ] 验证禁止方案不会进入分税种计算。
- [ ] 提交 `feat: add compliant planning guardrails`。

### Task 2: 商业目的和经济实质评估

**Files:**
- Create: `apps/tax_decision_core/business_purpose.py`
- Create: `apps/tax_decision_core/substance.py`
- Test: `apps/tax_decision_core/tests/test_business_purpose.py`
- Test: `apps/tax_decision_core/tests/test_substance.py`

- [ ] 定义人员、资产、场所、决策、风险承担、收入来源和成本承担事实。
- [ ] 输出 `sufficient / insufficient / uncertain`。
- [ ] 实质不足时停止方案排序并要求人工复核。
- [ ] 提交 `feat: assess business purpose and substance`。

### Task 3: 决策变量白名单

**Files:**
- Create: `planning/decision_variables.json`
- Create: `apps/tax_decision_core/decision_variables.py`
- Test: `apps/tax_decision_core/tests/test_decision_variables.py`

- [ ] 只允许主体形式、登记身份、价税条款、发票类型、付款交付时点、融资方式、资产或股权路径、真实报酬类型和优惠申请等变量。
- [ ] 禁止直接修改收入真实性、交易是否发生或证明文件内容。
- [ ] 为每个变量记录适用税种、所需事实和风险等级。
- [ ] 提交 `feat: add planning decision variable registry`。

### Task 4: 合规基线和候选生成器

**Files:**
- Create: `apps/tax_decision_core/planning_engine.py`
- Test: `apps/tax_decision_core/tests/test_planning_engine.py`

- [ ] 先生成不改变结构的合规基线。
- [ ] 从白名单变量生成有限候选，不使用自由文本任意改写交易。
- [ ] 候选数量设置上限并去重。
- [ ] 每个候选记录相对基线的事实差异。
- [ ] 提交 `feat: generate compliant planning candidates`。

### Task 5: 税务机会 DSL

**Files:**
- Create: `planning/opportunities/schema.md`
- Create: `planning/opportunities/CN/主体身份.yaml`
- Create: `planning/opportunities/CN/合同发票.yaml`
- Create: `planning/opportunities/CN/用工报酬.yaml`
- Create: `apps/tax_decision_core/opportunity_loader.py`
- Test: `apps/tax_decision_core/tests/test_opportunity_loader.py`

- [ ] 每个机会必须包含法源、资格条件、排除条件、商业目的、经济实质、所需资料和到期日。
- [ ] 机会文件不得包含可执行代码。
- [ ] 到期、废止或证据不足的机会不得生成方案。
- [ ] 提交 `feat: add tax planning opportunity DSL`。

### Task 6: 分税种方案计算和差异分析

**Files:**
- Create: `apps/tax_decision_core/planning_calculator.py`
- Modify: `apps/tax_decision_core/multitax.py`
- Test: `apps/tax_decision_core/tests/test_planning_calculator.py`

- [ ] 对基线和候选分别调用 VAT、CIT、PIT 及后续税种计算器。
- [ ] 输出永久税负差异、递延税款、现金流现值和实施成本。
- [ ] 退税候选不得跨税种直接抵减。
- [ ] 任一税种无法计算时综合方案升级人工复核。
- [ ] 提交 `feat: calculate planning scenario differences`。

### Task 7: 合规筹划评分器

**Files:**
- Create: `apps/tax_decision_core/planning_score.py`
- Test: `apps/tax_decision_core/tests/test_planning_score.py`

- [ ] 按法律确定性、经济实质、商业目的、税负、现金流、资料、成本和否定风险评分。
- [ ] 禁止方案直接淘汰，不参与排序。
- [ ] 税额最低但实质不足的方案不得排第一。
- [ ] 提交 `feat: rank compliant planning scenarios`。

### Task 8: 第一批主体和交易方案库

**Files:**
- Create: `planning/scenarios/主体与纳税身份.md`
- Create: `planning/scenarios/合同与发票.md`
- Create: `planning/scenarios/用工与报酬.md`
- Create: `11-问题测试集/v8_planning_cases.jsonl`
- Test: `apps/tax_workbench/tests/test_v8_planning_corpus.py`

覆盖：

- 小规模与一般纳税人登记选择；
- 公司、个体工商户、个人独资和合伙企业真实边界；
- 禁止人为分拆；
- 含税与不含税报价；
- 普票与专票需求；
- 预收、分期和履约时点；
- 工资、奖金、劳务、经营所得和分红真实分类；
- 禁止虚构劳动或外包关系。

### Task 9: 投融资、资产和区域规划

**Files:**
- Create: `planning/scenarios/投融资.md`
- Create: `planning/scenarios/资产股权与重组.md`
- Create: `planning/scenarios/区域与产业优惠.md`
- Test: `apps/tax_workbench/tests/test_v8_high_risk_planning.py`

- [ ] 股权与债权融资比较。
- [ ] 资产购买与股权购买比较。
- [ ] 分红、增资、减资和股权转让。
- [ ] 海南、新疆和产业优惠资格预审。
- [ ] 关联、跨境、房地产和重组全部强制人工审签。

### Task 10: 工作台和 Obsidian 筹划报告

**Files:**
- Modify: `apps/tax_workbench/models.py`
- Modify: `apps/tax_workbench/planner.py`
- Modify: `apps/tax_workbench/markdown.py`
- Modify: `apps/tax_workbench/static/index.html`
- Test: `apps/tax_workbench/tests/test_v8_planning_workbench.py`

- [ ] 浏览器展示合规基线和候选方案差异。
- [ ] 分开显示税负节省与递延价值。
- [ ] 展示商业目的、经济实质、禁止模式、证据和实施资料。
- [ ] 支持用户选择候选后进入人工审签。
- [ ] Obsidian 保存完整方案版本和审签记录。

### Task 11: 法规变化和持续合规

**Files:**
- Create: `apps/tax_decision_core/planning_impact.py`
- Modify: `90-工具/taxkb_impact.py`
- Test: `apps/tax_decision_core/tests/test_planning_impact.py`

- [ ] 建立 `provision_id → opportunity_id → scenario_id → case_id` 影响链。
- [ ] 优惠到期、条件变化或文件废止时标记方案重新评估。
- [ ] 已执行方案保留原版本，不自动覆盖历史记录。
- [ ] 提交 `feat: propagate law changes to planning scenarios`。

### Task 12: 发布门禁

**Files:**
- Modify: `.github/workflows/verify.yml`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Create: `docs/V8-COMPLIANT-PLANNING.md`
- Create: `10-法规更新记录/发布记录/V8合规税务筹划开发候选.md`

- [ ] 建立至少 40 个合规与禁止方案回归用例。
- [ ] 运行 V5—V8 全部测试、Vault、索引和原检索基线。
- [ ] 新增禁止方案零容忍指标。
- [ ] GitHub Actions 全绿后保持 Draft，按堆叠顺序集成。
