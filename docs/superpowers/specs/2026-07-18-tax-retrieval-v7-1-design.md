# 中国税务知识库 Agent V7.1 检索增强设计

## 1. 状态与范围

- 状态：已批准并进入实施
- 基础分支：`agent/tax-decision-core-v7`
- 目标分支：`agent/tax-retrieval-v7.1`
- 第一阶段税种：增值税
- 第一阶段地域：全国、新疆、海南
- 兼容目标：V6 `/api/analyze`、V7 案件存储和现有 `EvidenceItem`

V7.1 解决 V7.0 的检索瓶颈：单次 BM25 查询无法稳定区分支持、限制、排除和历史证据，也无法对语义相近但词面不同的条款进行召回。

## 2. 目标

1. 将一个业务问题拆成主问题、适用条件、限制排除、时间版本和地方覆盖等子查询；
2. 在硬性时间、地域、税种、效力和证据等级过滤之后执行混合召回；
3. 标准库环境下始终提供 BM25 + 本地哈希向量检索；
4. 允许后续注入外部 embedding provider，但不得成为正确性的单点依赖；
5. 将证据划分为 `support / limitation / exclusion / historical / local / conflict`；
6. 对候选条款执行融合、关系扩展、去重和确定性重排序；
7. 正式结论只使用目标日期有效的 A 级支持证据，同时展示限制和排除证据；
8. 保存完整检索轨迹，用于案件审计和法规变化后重放。

## 3. 非目标

- 不在 V7.1 接入云端向量数据库；
- 不把整套法规全面 GraphRAG 化；
- 不允许向量相似度绕过日期、地域、效力和证据等级门禁；
- 不允许 LLM 自行决定哪些法规有效；
- 不追求跨全部税种的通用法律搜索；
- 不删除现有 BM25 评测和旧 API。

## 4. 总体架构

```text
TaxFacts / TaxIssue / 用户问题
        ↓
QueryPlanner
  ├─ main
  ├─ eligibility
  ├─ limitation
  ├─ exclusion
  ├─ version
  └─ local
        ↓
MetadataGate
  时间 / 地域 / 税种 / 效力 / A级证据
        ↓
HybridRetriever
  ├─ BM25
  ├─ HashingVectorIndex
  └─ 可选 EmbeddingProvider
        ↓
Reciprocal Rank Fusion
        ↓
RelationExpander
  法规卡 / 条款卡 / 关系卡 / source_note / wikilink
        ↓
EvidenceClassifier
        ↓
DeterministicReranker
        ↓
VersionResolver + Deduplicator
        ↓
EvidenceBundle + RetrievalTrace
```

## 5. 核心数据模型

### 5.1 QueryPlan

```python
@dataclass(slots=True)
class QuerySpec:
    query_id: str
    role: str
    text: str
    required_terms: tuple[str, ...] = ()
    optional_terms: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ("effective", "partially_effective")

@dataclass(slots=True)
class QueryPlan:
    jurisdiction: str
    valid_on: str
    tax_type: str | None
    queries: list[QuerySpec]
    historical_requested: bool = False
```

`role` 只允许：`main / eligibility / limitation / exclusion / version / local`。

### 5.2 RetrievalCandidate

每个候选保留：

- 文档路径与 chunk_id；
- 标题、条款号、document_id、provision_id；
- BM25 排名与分数；
- 向量排名与分数；
- RRF 分数；
- 关系扩展分数；
- 最终重排分数；
- 证据角色；
- 有效期、状态、地域和证据等级；
- 命中的子查询与命中原因。

### 5.3 EvidenceBundle

```python
@dataclass(slots=True)
class EvidenceBundle:
    support: list[EvidenceItem]
    limitation: list[EvidenceItem]
    exclusion: list[EvidenceItem]
    historical: list[EvidenceItem]
    local: list[EvidenceItem]
    conflict: list[EvidenceItem]
    trace: RetrievalTrace
```

旧 `search()` 返回 `support + local + limitation + exclusion` 的去重扁平列表；新代码优先调用 `search_bundle()`。

## 6. 查询拆解

`QueryPlanner` 使用事实和议题树生成确定性子查询。

### 普通小规模服务

- main：主体、交易、金额期间、地区；
- eligibility：小规模、起征点、1%征收率；
- limitation：同期间全部销售额、放弃免税、专票；
- exclusion：不动产、土地使用权、一般纳税人登记；
- version：业务日期、有效期、延期、废止；
- local：新疆或海南覆盖关系。

### 海南进口

额外加入：

- 享惠主体；
- HS编码与进口征税目录；
- 一线、二线和岛内流向；
- 用途与后续处置；
- 普通税制保守基线；
- 强制人工复核。

查询拆解是确定性规则，不调用 LLM。后续可以允许 LLM提出候选查询，但必须通过白名单角色和长度校验。

## 7. 混合召回

### 7.1 BM25

继续复用 `taxkb_core.bm25_rank`，每个子查询独立召回，保留原始排名。

### 7.2 本地哈希向量

标准库实现 `HashingVectorizer`：

- 中文连续字符生成单字、二元和三元 token；
- 英文和数字保留词 token；
- 使用 SHA256 将 token 映射到固定 512 维；
- 使用带符号 hashing 减少碰撞偏差；
- L2 归一化并计算余弦相似度；
- 不写入真实文本或远程服务。

该向量用于召回同义和近义表达，不能替代法律效力过滤。

### 7.3 可选 Provider

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

provider 失败时记录 trace 并回退本地哈希向量，不影响请求完成。

### 7.4 融合

使用 RRF：

```text
score = Σ 1 / (k + rank)
k = 60
```

分别融合各子查询的 BM25 和向量排名。不得直接相加不同量纲的原始分数。

## 8. 证据分类

分类优先级：

1. 元数据状态和关系类型；
2. 文件目录和 note type；
3. 标题与条款文本关键词；
4. 查询角色。

规则：

- `historical`：repealed、expired、已废止、历史版本；
- `conflict`：uncertain、pending_review、冲突关系；
- `exclusion`：不适用、不得、除外、排除、废止替代；
- `limitation`：应当、必须、仅限、条件、需要核验、起征点合并；
- `local`：目标地区非 CN 的覆盖文件；
- 其他为 `support`。

一条证据只能有一个主角色，但 trace 保留所有分类信号。

## 9. 关系扩展

关系扩展只在首轮高分候选周围一跳执行：

- 同 document_id 的条款卡；
- source_note 指向的法规卡；
- 关系卡中 linked 的旧新文件；
- 同 provision_id / related_provisions；
- Obsidian wikilink 直接邻居。

扩展候选必须重新经过元数据门禁。关系分仅作为轻量加分，不能让低证据等级内容超过有效 A 级条款。

## 10. 确定性重排序

最终分数由可解释特征组成：

- RRF：0—40；
- 标题/条款号精确命中：0—15；
- 查询角色覆盖：0—10；
- 目标地域匹配：0—8；
- A级证据：0—8；
- 条款级内容优先于概念和案例：0—8；
- 关系邻居：0—5；
- 过长片段惩罚：0—4；
- 版本和状态惩罚：按规则扣分。

所有特征写入 `score_breakdown`。

## 11. 版本感知

- 正式证据先按 `valid_on` 过滤；
- 同 document_id/provision_id 多版本时选择目标日期有效且 `valid_from` 最新的版本；
- 当前问题不展示废止版本作为支持证据；
- 历史、废止或“当时适用”问题单独运行 historical 查询；
- 历史证据必须标注其有效区间，不得混入当前结论。

## 12. 与 V7 决策核心集成

`TaxPlanningService`：

1. 先生成议题树；
2. 调用 `search_bundle(facts, issues)`；
3. 旧 `evidence` 字段继续返回扁平 A 级正式证据；
4. 新增 `evidence_groups` 和 `retrieval_trace`；
5. 没有 support 证据时继续失败关闭；
6. exclusion/limitation 命中时写入风险和人工复核判断；
7. 持久案件保存 `retrieval-vNNN.json`。

## 13. 安全与隐私

- 默认本地运行；
- 不向外部 provider 发送合同、发票、身份证号或完整案件描述；
- 启用外部 provider 时只发送脱敏后的检索短句；
- provider 名称、模型、hash 和调用时间进入 trace；
- provider 失败不改变硬门禁；
- 任何 B/C/D 级材料不得成为直接法律结论依据。

## 14. 评测

新增四类评测：

1. Recall：正确条款是否进入 top-k；
2. Role：支持、限制、排除、历史分类是否正确；
3. Version：目标日期是否选择正确版本；
4. Precision：top-5 中无关整篇、案例和过期文件比例。

验收指标：

- 现有17题 Hit@5 维持100%；
- V7决策语料全部通过；
- 新增检索用例至少30题；
- 支持/限制/排除角色准确率 ≥ 90%；
- 版本选择测试100%；
- 无A级支持证据时100%失败关闭；
- 旧 `EvidenceRetriever.search()` 行为兼容。

## 15. 发布边界

V7.1 作为基于 V7.0 的堆叠 Draft PR。V7.0 未合并前，V7.1 不直接面向 `main` 合并。GitHub Actions Runner 的既有零步骤失败继续作为外部门禁记录。