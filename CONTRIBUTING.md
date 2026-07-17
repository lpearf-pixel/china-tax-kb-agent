# 贡献指南

## 贡献原则

1. 正式法规事实优先使用 A 级官方来源；
2. 文件效力与条款效力分别维护；
3. 新疆问题同时检索全国规则与新疆覆盖规则；
4. 海南普通境内业务与自贸港特殊政策必须分别判断；
5. 新法规先进入 `10-法规更新记录/待审核/`，不得直接覆盖现行知识；
6. 不提交未脱敏的企业或个人税务资料。

## 提交前验证

```bash
cd 90-工具
python3 -m unittest discover -s tests -v
python3 taxkb_validate.py --report /tmp/taxkb-validation.md
python3 taxkb_export.py --profile full --output /tmp/taxkb-chunks.jsonl
python3 taxkb_eval.py --chunks /tmp/taxkb-chunks.jsonl --report /tmp/taxkb-eval.md
```

所有检查通过后，再提交法规卡、条款卡、关系卡及对应测试问题。
