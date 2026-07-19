# V7.2 增值税 + 企业所得税多税种联动

V7.2 第一批在 V7.1 版本感知检索基础上增加企业所得税基础闭环，并将企业所得税税额叠加到现有增值税方案。

## 当前支持范围

- 增值税：沿用 V7.0/V7.1 的全国、新疆和海南规则；
- 企业所得税：居民公司制企业一般计算；
- 一般企业所得税税率 25%；
- 2023-01-01 至 2027-12-31 小型微利企业优惠；
- 会计利润、纳税调增、纳税调减、亏损弥补、税额抵免和预缴税额；
- 增值税与企业所得税税种分项和综合税负；
- 个人独资企业、合伙企业、非居民企业和高风险事项失败关闭或人工复核。

## 启动

```bash
python3 -m apps.tax_workbench.server --open
```

默认地址：

```text
http://127.0.0.1:8765
```

## API 请求示例

### 企业所得税单税种

```json
{
  "requested_tax_types": ["企业所得税"],
  "business_date": "2026-07-19",
  "region": "CN",
  "taxpayer_type": "企业",
  "vat_status": "一般纳税人",
  "transaction_type": "服务",
  "amount": "1000000",
  "amount_period": "年度",
  "invoice_need": "普通发票",
  "objective": "企业所得税测算",
  "description": "居民公司年度企业所得税测算",
  "entity_form": "公司制企业",
  "cit_resident_status": "居民企业",
  "cit_accounting_profit": "1000000",
  "cit_adjustment_increase": "0",
  "cit_adjustment_decrease": "0",
  "cit_loss_carryforward": "0",
  "cit_tax_credit": "0",
  "cit_prepaid_tax": "0",
  "cit_employee_count_avg": "20",
  "cit_asset_total_avg": "10000000",
  "cit_restricted_industry": false
}
```

### 增值税 + 企业所得税

将税种改为：

```json
"requested_tax_types": ["增值税", "企业所得税"]
```

并同时提供增值税销售额、身份、税率相关事实和企业所得税事实。

## 企业所得税公式

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

应补退税候选：

```text
应补退税额 = 应纳所得税额 - 税额抵免 - 已预缴税额
```

负数只作为退税或多缴候选展示，不直接冲减增值税或其他税种。

## 小型微利企业门禁

必须同时满足：

- 非国家限制和禁止行业；
- 年度应纳税所得额不超过 300 万元；
- 从业人数不超过 300 人；
- 资产总额不超过 5000 万元；
- 优惠适用日期不晚于 2027-12-31。

存在非法人分支机构时，人数、资产和应纳税所得额应采用总分机构合计口径。

## 不自动计算的事项

以下事项只输出资料清单和人工复核：

- 非居民企业；
- 跨境所得、境外税收抵免和源泉扣缴；
- 关联交易特别纳税调整；
- 企业重组、清算和房地产复杂事项；
- 高新技术企业、研发费用加计扣除等专项优惠；
- 个人独资企业和合伙企业的个人所得税。

## 税种分项

每个综合方案返回：

```json
{
  "tax_breakdown": {
    "增值税": "4000.00",
    "企业所得税": "50000.00"
  },
  "estimated_tax": "54000.00"
}
```

退税候选保存于案件场景的 `cashflow_summary.refund_candidates`，不会与其他税种相互抵减。

## 测试

```bash
python3 -m unittest discover -s 90-工具/tests -v
python3 -m unittest discover -s apps/tax_decision_core/tests -v
python3 -m unittest discover -s apps/tax_retrieval/tests -v
python3 -m unittest discover -s apps/tax_workbench/tests -v
```

V7.2 语料：

```text
11-问题测试集/v7_2_cit_cases.jsonl
```

覆盖一般税率、小型微利边界、政策到期、纳税调整、亏损、预缴、主体排除、非居民、分支机构以及增值税和企业所得税综合方案。
