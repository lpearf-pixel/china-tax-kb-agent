# V7 税务决策核心

V7 将 V6 的固定方案工作台升级为可审计、可版本化、可局部重算的税务决策系统。

## 架构

```text
业务事实
→ 事实图谱和版本
→ 税务议题树
→ A级法规检索
→ 安全规则 DSL
→ 确定性规则引擎
→ Decimal 税额和现金流计算
→ 动态情景生成与透明评分
→ 人工审签
→ Obsidian 报告与案件审计
```

## 当前范围

- 税种：增值税；
- 主体：小规模纳税人、一般纳税人基础场景、自然人和个体工商户；
- 地域：全国、新疆、海南；
- 海南进口、HS编码、享惠主体、关联交易、不动产、重组、历史补税和稽查强制人工复核。

## 启动

```bash
python3 -m apps.tax_workbench.server --open
```

默认地址：`http://127.0.0.1:8765`。

## 交互方式

### 无状态分析

`POST /api/analyze`

用于快速试算，不创建案件，不返回可刷新案件编号。

### 建立持久案件

`POST /api/cases`

或在页面点击“建立案件并保存”。案件运行数据写入本地 `cases/<case_id>/`，默认被 Git 忽略。

### 读取案件

`GET /api/cases/{case_id}`

返回事实版本、议题、证据、规则判断、计算和方案。

### 修改事实

`PATCH /api/cases/{case_id}/facts/{fact_id}`

请求示例：

```json
{
  "value": true,
  "actor": "owner"
}
```

系统返回受影响节点和需要重跑的范围。例如修改专票需求只重跑规则、计算和方案；修改业务日期会重新检索证据。

### 重跑案件

`POST /api/cases/{case_id}/analyze`

按最新事实版本重新生成规则、计算和方案版本。

### 人工审签

`POST /api/cases/{case_id}/review`

```json
{
  "approved": true,
  "actor": "reviewer",
  "note": "已核验合同和申报资料"
}
```

### 审计轨迹

`GET /api/cases/{case_id}/audit`

显示案件创建、事实修改、局部重算、分析版本和审签事件。

## 规则 DSL

规则存放在 `rules/vat/`。第一阶段使用 JSON-compatible YAML，只允许白名单条件和结果结构，禁止执行任意代码。

每条规则必须包含：

- 有效期；
- 地域；
- 优先级和排他组；
- 必要事实；
- 输出；
- `document_id / provision_id` 法源。

规则加载时会检查法源 ID 是否存在于 Obsidian Vault。

## 计算和方案

所有金额使用 `Decimal`，统一按 `ROUND_HALF_UP` 到分。每个计算结果保存：

- 输入；
- 公式；
- 税额；
- 应纳或留抵；
- 规则 ID；
- 交易、申报和缴税时间事件。

方案排序展示七个维度：税负、现金流、法规确定性、资料完备度、复杂度、争议风险和发票需求满足程度。

## 法规变化

法规变化通过以下链路传播：

```text
provision_id → rule_id → case_id → scenario_id
```

受影响案件被标记为 `affected_by_law_change`，但不会覆盖旧规则集版本或已批准方案。历史业务继续使用当时有效规则。

## 数据安全

- `cases/` 和真实会话默认不进入 Git；
- 原始合同、发票、流水不自动复制到仓库；
- 工作台默认仅监听本机；
- LLM 不能改变确定性规则结果和税额；
- 高风险事项必须人工审签。
