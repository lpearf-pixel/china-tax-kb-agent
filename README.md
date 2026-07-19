# 中国税务知识库 Agent

知识库基线：`KB-2026.07.17-V5-PILOT-XJ-HI`  
当前开发线：`V7.1 版本感知混合检索`

以 **Obsidian 为人工知识事实源**，采用条款级混合检索、安全规则 DSL、确定性规则引擎、Decimal 税额计算、案件状态机和人工审签，辅助查询、解释和比较中国税务方案。

> 全国增值税底座 + 新疆覆盖层 + 海南自由贸易港覆盖层 + 混合RAG + 规则引擎 + 计算引擎 + 有限 Agent

## 当前范围

- 税种：增值税；
- 主体：小规模纳税人、自然人、个体工商户及一般纳税人基础测算；
- 地域：新疆维吾尔自治区、海南自由贸易港和全国规则；
- 业务日期：优先覆盖 2026 年增值税新体系；
- 高风险事项：海南特殊政策、关联交易、不动产、重组、历史补税和稽查强制人工复核。

## V7.1 决策流程

```text
业务事实和资料
→ 事实图谱与事实版本
→ 税务议题树和查询拆解
→ 日期/地域/效力/A级证据门禁
→ BM25 + 本地哈希向量召回
→ RRF融合、关系扩展和版本选择
→ 支持/限制/排除/历史/地方/冲突证据包
→ 规则判断与排除条件
→ Decimal税额和现金流计算
→ 动态方案生成与透明评分
→ 人工审签
→ Obsidian报告和审计时间线
```

正式法规依据只能来自 `01-法规原文` 和 `02-条款结构`。概念卡、场景卡、案例和 LLM 输出不能替代正式法源。没有有效 A 级支持证据时，系统失败关闭并要求人工复核。

## 使用 Obsidian

1. 克隆或下载仓库；
2. 在 Obsidian 中选择“打开本地库”；
3. 选择仓库根目录；
4. 从 `00-首页/知识库首页.md` 开始。

## 启动本地工作台

```bash
python3 -m apps.tax_workbench.server --open
```

默认只监听：

```text
http://127.0.0.1:8765
```

工作台可以：

- 快速执行无状态分析；
- 建立本地持久案件；
- 展示税务议题树；
- 分开展示支持、限制、排除、历史、地方和冲突证据；
- 展示子查询、BM25/向量召回、关系扩展和最终评分；
- 展示规则命中、排除、缺失事实和冲突；
- 展示税额公式与现金流时间；
- 动态比较税负、现金流、确定性、资料完备度、复杂度和风险；
- 修改事实后只重跑受影响节点；
- 保存 Obsidian 审计报告和 `retrieval-vNNN.json`；
- 查看案件时间线并记录人工审签。

真实案件默认保存在 `cases/`，会话报告保存在 `16-交互工作台/会话记录/`，两者默认不提交 Git。

详细说明：

- [V7 决策核心指南](docs/V7-DECISION-CORE.md)
- [V7.1 检索增强指南](docs/V7-1-RETRIEVAL.md)

## 本地验证

建议 Python 3.10+：

```bash
python3 -m compileall -q apps 90-工具
python3 -m unittest discover -s 90-工具/tests -v
python3 -m unittest discover -s apps/tax_decision_core/tests -v
python3 -m unittest discover -s apps/tax_retrieval/tests -v
python3 -m unittest discover -s apps/tax_workbench/tests -v
python3 90-工具/taxkb_validate.py
python3 90-工具/taxkb_export.py --profile full
python3 90-工具/taxkb_eval.py
```

V7.1 的30题可执行检索语料：

```text
11-问题测试集/v7_1_retrieval_cases.jsonl
```

## 命令行法规查询

新疆：

```bash
cd 90-工具
python3 taxkb_query.py "新疆小规模纳税人季度销售额24万元" \
  --jurisdiction CN-XJ --valid-on 2026-07-17 --tax-type 增值税
```

海南：

```bash
cd 90-工具
python3 taxkb_query.py "海南企业提供软件咨询是否适用零关税" \
  --jurisdiction CN-HI --valid-on 2026-07-17
```

## 法规更新

```bash
cd 90-工具
python3 taxkb_update.py
```

变化只进入 `10-法规更新记录/待审核/`，不会自动覆盖正式知识。确认发布后，系统可以沿：

```text
provision_id → rule_id → case_id → scenario_id
```

识别受影响案件。已批准历史案件保留原规则集版本，只标记重新评估，不自动覆盖。

## 项目文档

- [V7.1 检索增强指南](docs/V7-1-RETRIEVAL.md)
- [V7 决策核心指南](docs/V7-DECISION-CORE.md)
- [项目路线图](docs/ROADMAP.md)
- [安全与使用边界](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)
- [V5 正式基线](12-决策记录/V5正式基线.md)
- [V7.1 设计文档](docs/superpowers/specs/2026-07-18-tax-retrieval-v7-1-design.md)
- [V7.1 实施计划](docs/superpowers/plans/2026-07-18-tax-retrieval-v7-1.md)

## 免责声明

法规卡主要保存关键条款摘录、结构化摘要和官方来源链接，不宣称是所有法规及附件的完整离线镜像。系统结果是法规检索、规则判断和方案比较草案，不替代主管税务机关、注册税务师或律师的正式意见。正式申报、合同安排和税务规划必须核验原文、业务日期、主体资格及地方执行口径。
