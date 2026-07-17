# 中国税务知识库 Agent V5 试点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 建成以 Obsidian 为唯一人工事实源、覆盖全国增值税底座以及新疆和海南地域覆盖层的可检索、可更新、可审签 V5 试点知识库。

**Architecture:** 使用知识内容五层（法规原文、条款结构、概念解释、业务场景、规划决策）与系统控制五层（来源更新、事实输入、检索规则、Workflow Agent、审计评测）正交组织。检索采用条款级 BM25 基线与地区、日期、税种、证据等级硬过滤；法规更新进入待审核区，发布后运行影响传播与回归测试。

**Tech Stack:** Obsidian Markdown、YAML Frontmatter、Python 3 标准库、本地 JSONL 条款索引、BM25 回归检索、macOS launchd 可选定时任务。

## Global Constraints

- Obsidian 是唯一人工维护的知识事实源。
- 正式答案只能把 A 级法规原文或条款结构作为直接法规依据。
- 查询新疆或海南时必须同时保留全国规则与对应地域覆盖规则。
- 文件效力和条款效力分别管理，支持部分有效、尚未生效、到期、废止和待复核。
- 法规更新不得自动覆盖正式库，必须进入待审核区并生成影响报告。
- 第一阶段试点锁定增值税、小规模纳税人、新疆适用性和海南适用性。
- 海南普通国内增值税问题不得因主体位于海南而自动套用自贸港零关税政策。
- 大额、历史补税、稽查、跨境、重组、关联交易、房地产及海南自贸港资格问题必须进入人工复核。

---

### Task 1: 建立 V5 目录与正式设计记录

**Files:**
- Create: `00-首页/知识库首页.md`
- Create: `12-决策记录/V5正式基线.md`
- Create: `12-决策记录/架构决策记录_ADR-001.md`
- Create: `README.md`

- [x] **Step 1:** 建立正式目录，明确双五层架构和两地试点边界。
- [x] **Step 2:** 写入 V5 基线、风险边界和知识库版本信息。
- [x] **Step 3:** 校验所有首页链接可解析。

### Task 2: 建立统一法规、条款与关系元数据模型

**Files:**
- Create: `99-模板/法规原文模板.md`
- Create: `99-模板/条款卡模板.md`
- Create: `99-模板/概念卡模板.md`
- Create: `99-模板/场景卡模板.md`
- Create: `99-模板/关系卡模板.md`
- Create: `07-政策效力与关系/效力状态模型.md`
- Create: `07-政策效力与关系/证据等级模型.md`

- [x] **Step 1:** 定义文件级、条款级和关系级元数据。
- [x] **Step 2:** 定义 effective、partially_effective、not_yet_effective、expired、repealed、pending_review、uncertain。
- [x] **Step 3:** 定义 A/B/C/D 证据等级和回答引用门禁。

### Task 3: 建立全国增值税与小规模纳税人试点法源

**Files:**
- Create: `01-法规原文/国家/增值税/中华人民共和国增值税法.md`
- Create: `01-法规原文/国家/增值税/中华人民共和国增值税法实施条例.md`
- Create: `01-法规原文/国家/增值税/增值税一般纳税人登记管理有关事项_2026年第2号.md`
- Create: `01-法规原文/国家/增值税/增值税征税具体范围_2026年第9号.md`
- Create: `01-法规原文/国家/增值税/增值税优惠政策衔接_2026年第10号.md`
- Create: `01-法规原文/国家/增值税/起征点标准等征管事项_2026年第4号.md`
- Create: `01-法规原文/国家/增值税/调整增值税纳税申报_2026年第6号.md`
- Create: `99-归档/已废止/增值税小规模纳税人减免征管_2023年第1号.md`
- Create: `99-归档/已废止/增值税一般纳税人登记管理办法_税务总局令43号.md`

- [x] **Step 1:** 写入官方来源、文号、生效时间、状态和替代关系。
- [x] **Step 2:** 把 2026 年新体系与已废止旧文件明确连接。
- [x] **Step 3:** 所有直接结论必须能回链到官方原文页。

### Task 4: 建立条款结构、概念和纳税人类型

**Files:**
- Create: `02-条款结构/增值税/增值税法_第三条_纳税人与应税交易.md`
- Create: `02-条款结构/增值税/增值税法_第八至九条_计税方法与小规模标准.md`
- Create: `02-条款结构/增值税/增值税法_第十条_税率.md`
- Create: `02-条款结构/增值税/增值税法_第二十七条_放弃优惠.md`
- Create: `02-条款结构/增值税/2026年第10号_起征点条款.md`
- Create: `02-条款结构/增值税/2026年第4号_小规模征管条款.md`
- Create: `02-条款结构/增值税/2026年第2号_一般纳税人登记条款.md`
- Create: `03-概念解释/小规模纳税人.md`
- Create: `03-概念解释/增值税起征点.md`
- Create: `03-概念解释/一般计税与简易计税.md`
- Create: `05-纳税人类型/自然人.md`
- Create: `05-纳税人类型/个体工商户.md`
- Create: `05-纳税人类型/企业小规模纳税人.md`

- [x] **Step 1:** 以条、款、项为最小法律证据单位。
- [x] **Step 2:** 概念解释卡必须链接条款卡，不得自行成为法律依据。
- [x] **Step 3:** 区分自然人、个体工商户和企业小规模纳税人的征管差异。

### Task 5: 建立新疆与海南覆盖层

**Files:**
- Create: `01-法规原文/新疆/README.md`
- Create: `01-法规原文/海南/README.md`
- Create: `04-税种知识/增值税/新疆适用地图.md`
- Create: `04-税种知识/增值税/海南适用地图.md`
- Create: `07-政策效力与关系/新疆覆盖关系/全国增值税规则在新疆的适用.md`
- Create: `07-政策效力与关系/海南覆盖关系/全国增值税规则在海南的适用.md`
- Create: `07-政策效力与关系/海南覆盖关系/海南自贸港特殊政策门禁.md`
- Migrate: v4 新疆和海南经核验政策卡至新目录。

- [x] **Step 1:** 地域查询保留 CN + CN-XJ 或 CN + CN-HI。
- [x] **Step 2:** 新疆地方解读不得推翻全国上位法。
- [x] **Step 3:** 海南自贸港零关税、加工增值和所得税优惠只在匹配场景与资格时触发。

### Task 6: 建立 Workflow、Agent 提示词和人工审签

**Files:**
- Create: `13-Workflow/税务问答十四节点Workflow.md`
- Create: `13-Workflow/法规更新Workflow.md`
- Create: `14-Agent提示词/系统总提示词.md`
- Create: `14-Agent提示词/地域与时间路由Agent.md`
- Create: `14-Agent提示词/证据核验Agent.md`
- Create: `14-Agent提示词/风险审查Agent.md`
- Create: `15-人工审签/强制人工复核清单.md`
- Create: `15-人工审签/审签记录模板.md`

- [x] **Step 1:** 固定时间、地域、主体、税种和事实完整性检查。
- [x] **Step 2:** 证据不足、效力不明或地方冲突时禁止确定性回答。
- [x] **Step 3:** 新疆和海南高风险事项分别设置地域复核点。

### Task 7: 更新本地工具支持 V5 目录和状态过滤

**Files:**
- Copy/Modify: `90-工具/taxkb_core.py`
- Copy/Modify: `90-工具/taxkb_export.py`
- Copy/Modify: `90-工具/taxkb_query.py`
- Copy/Modify: `90-工具/taxkb_validate.py`
- Copy/Modify: `90-工具/taxkb_update.py`
- Copy/Modify: `90-工具/taxkb_impact.py`
- Test: `90-工具/tests/test_taxkb_tools.py`

**Interfaces:**
- `select_note_for_profile(rel: str, profile: str) -> bool`
- `filter_docs(docs, jurisdiction=None, valid_on=None, tax_type=None, evidence_tiers=None, statuses=None)`
- `discover_note_sources(vault: Path) -> list[dict]`

- [x] **Step 1:** 先写 V5 目录、状态、证据等级和海南门禁相关失败测试。
- [x] **Step 2:** 运行测试确认因旧目录假设而失败。
- [x] **Step 3:** 最小修改工具以通过测试。
- [x] **Step 4:** 运行全部单元测试。

### Task 8: 建立试点测试集与发布校验

**Files:**
- Create: `11-问题测试集/eval_cases.jsonl`
- Create: `11-问题测试集/评测说明.md`
- Create: `11-问题测试集/最近评测报告.md`
- Create: `10-法规更新记录/待审核/README.md`
- Create: `10-法规更新记录/更新SOP.md`
- Create: `10-法规更新记录/发布记录/2026-07-17_V5试点发布.md`
- Create: `MANIFEST.json`

- [x] **Step 1:** 建立国家、新疆、海南、时间、效力、拒答和人工复核测试。
- [x] **Step 2:** 导出条款级索引并运行 BM25 回归。
- [x] **Step 3:** 运行 Vault 元数据与 Wikilink 校验。
- [x] **Step 4:** 生成 Manifest、ZIP 并执行完整性校验。
