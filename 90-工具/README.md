# V5 本地工具

所有工具只依赖 Python 3 标准库，建议 Python 3.10+。

## 一键验证

```bash
cd 90-工具
python3 -m unittest discover -s tests -v
python3 taxkb_validate.py
python3 taxkb_export.py --profile full
python3 taxkb_eval.py
```

## 按地区和日期查询

新疆：

```bash
python3 taxkb_query.py "新疆小规模纳税人季度销售额24万元" \
  --jurisdiction CN-XJ --valid-on 2026-07-17 --tax-type 增值税
```

海南普通业务：

```bash
python3 taxkb_query.py "海南企业提供软件咨询是否适用零关税" \
  --jurisdiction CN-HI --valid-on 2026-07-17
```

只检索可作为直接法规依据的 A 级材料：

```bash
python3 taxkb_query.py "小规模纳税人季度30万元起征点" \
  --valid-on 2026-07-17 --evidence-tier A
```

查询历史废止材料时显式加入状态：

```bash
python3 taxkb_query.py "2023年第1号公告" \
  --valid-on 2025-06-01 --include-status effective,repealed
```

## 法规更新

```bash
python3 taxkb_update.py
```

工具同时监控官方入口和法规卡中的具体 `source_url`。变化只写入 `10-法规更新记录/待审核/`，不会自动覆盖正式知识。

## 变更影响追踪

```bash
python3 taxkb_impact.py \
  "01-法规原文/国家/增值税/增值税优惠政策衔接_2026年第10号.md"
```

## macOS 每周更新

```bash
./macos/setup_weekly_launchd.sh
```

默认每周一 09:00 执行：来源检查、Vault 校验、完整索引重建和回归评测。
