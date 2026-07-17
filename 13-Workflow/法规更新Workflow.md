---
title: 法规更新 Workflow
verified_at: "2026-07-17"
kb_version: KB-2026.07.17-V5-PILOT-XJ-HI
type: workflow
workflow_id: WF-TAX-UPDATE
---

# 法规更新 Workflow


## 发现

定期检查官方门户和每张法规卡的 `source_url` 指纹。

## 待审核

新文件或页面变化进入 `10-法规更新记录/待审核/`，生成差异、效力和影响清单，不自动改正式库。

## 影响传播

法规卡 → 条款卡 → 概念卡 → 场景卡 → 案例和回答模板。

## 发布

人工确认 → 更新条款状态和关系 → 重建索引 → 运行回归测试 → 写发布记录 → 生成新版本号。

## 回滚

保留历史文件与旧版本 Manifest，支持按业务发生日期回查。
