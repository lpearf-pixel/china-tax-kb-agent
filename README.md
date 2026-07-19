# 中国税务知识库 Agent

知识库基线：`KB-2026.07.17-V5-PILOT-XJ-HI`  
当前开发线：`V7.2 增值税 + 企业所得税多税种联动`

以 **Obsidian 为人工知识事实源**，采用版本感知混合检索、安全规则 DSL、分税种确定性计算、案件状态机和人工审签，辅助查询、解释和比较中国税务方案。

> 全国规则底座 + 新疆覆盖层 + 海南自贸港覆盖层 + 混合 RAG + 分税种规则引擎 + Decimal 计算 + 有限 Agent

## 当前范围

- 增值税：小规模纳税人、自然人、个体工商户及一般纳税人基础测算；
- 企业所得税：居民公司制企业一般计算与 2023—2027 小型微利企业优惠；
- 地域：全国、新疆和海南；
- 综合输出：增值税、企业所得税税种分项与综合税负；
- 高风险事项：非居民、跨境、关联、重组、房地产、海南特殊政策、历史补税和稽查强制人工复核。

个人所得税、印花税、契税、土地增值税及企业所得税专项优惠尚未进入确定性计算。

## V7.2 决策流程

```text
业务事实和所选税种
→ 事实图谱与事实版本
→ 分税种议题树和查询拆解
→ 日期/地域/效力/A级证据门禁
→ BM25 + 本地哈希向量召回
→ 证据角色分类和版本选择
→ 增值税规则与计算
→ 企业所得税规则与计算
→ 税种分项和综合税负
→ 动态方案评分
→ 人工审签
→ Obsidian 报告和案件审计
```

正式法规依据只能来自 `01-法规原文` 和 `02-条款结构`。没有目标日期有效的 A 级支持证据或规则集时，系统失败关闭。

## 启动本地工作台

```bash
python3 -m apps.tax_workbench.server --open
```

默认只监听：

```text
http://127.0.0.1:8765
```

工作台支持：

- 选择增值税、企业所得税或两者；
- 填写会计利润、纳税调整、亏损、预缴和小型微利企业指标；
- 查看分税种法规证据、规则轨迹和计算公式；
- 查看每个方案的税种分项及综合税负；
- 建立本地持久案件、修订事实、局部重算和人工审签；
- 保存 Obsidian 决策报告和检索审计版本。

真实案件保存在 `cases/`，会话报告保存在 `16-交互工作台/会话记录/`，默认不提交 Git。

## 企业所得税基础公式

```text
应纳税所得额
= 会计利润
+ 纳税调增
- 纳税调减
- 可弥补亏损
```

一般居民企业：

```text
应纳所得税额 = max(应纳税所得额, 0) × 25%
```

2023—2027 年符合条件的小型微利企业：

```text
应纳所得税额 = max(应纳税所得额, 0) × 25% × 20%
```

负数应补退税额只作为退税或多缴候选，不跨税种抵减。

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

回归语料：

```text
11-问题测试集/v7_1_retrieval_cases.jsonl
11-问题测试集/v7_2_cit_cases.jsonl
```

## 法规更新

```bash
cd 90-工具
python3 taxkb_update.py
```

变化只进入 `10-法规更新记录/待审核/`。确认发布后，系统沿：

```text
provision_id → rule_id → case_id → scenario_id
```

识别受影响案件，保留原事实、规则和计算版本。

## 项目文档

- [V7.2 多税种指南](docs/V7-2-MULTITAX.md)
- [V7.1 检索增强指南](docs/V7-1-RETRIEVAL.md)
- [V7 决策核心指南](docs/V7-DECISION-CORE.md)
- [项目路线图](docs/ROADMAP.md)
- [安全与使用边界](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)
- [V7.2 设计文档](docs/superpowers/specs/2026-07-19-tax-multitax-v7-2-design.md)
- [V7.2 实施计划](docs/superpowers/plans/2026-07-19-tax-multitax-v7-2.md)

## 免责声明

本项目保存关键法规摘录、结构化元数据和官方来源链接，不是全部税法全文镜像。系统结果是法规检索、规则判断、计算和方案比较草案，不替代主管税务机关、注册税务师、会计师或律师的正式意见。正式申报和交易安排必须核验原文、业务日期、会计资料、主体资格和地方执行口径。
