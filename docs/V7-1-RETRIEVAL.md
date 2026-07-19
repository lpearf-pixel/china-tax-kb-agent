# V7.1 版本感知混合税务检索

V7.1 将 V7.0 的单次 BM25 检索升级为可审计的证据包检索，但不会让语义相似度绕过法规效力门禁。

## 处理流程

```text
业务事实和税务议题
→ 查询拆解
→ 日期、地域、税种、效力、A级证据硬过滤
→ BM25关键词召回
→ 本地哈希向量召回
→ Reciprocal Rank Fusion
→ 一跳法规关系扩展
→ 支持/限制/排除/历史/地方/冲突分类
→ 版本选择
→ 确定性重排序
→ EvidenceBundle + RetrievalTrace
```

## 查询角色

每次普通新疆或海南问题至少生成：

- `main`：业务主问题；
- `eligibility`：身份、起征点、优惠和登记资格；
- `limitation`：必须满足的事实和执行条件；
- `exclusion`：不适用、除外和禁止情形；
- `version`：生效、到期、修改、废止和替代；
- `local`：全国规则与目标地区覆盖层。

海南进口额外查询享惠主体、HS编码、进口征税目录、一线二线流向、用途、普通税制基线和人工复核。

## 证据分组

- `support`：可直接支持当前结论的有效A级依据；
- `limitation`：适用前提、必须核验事项和程序条件；
- `exclusion`：不适用、排除、例外和禁止情形；
- `historical`：已废止或已失效版本，只回答历史问题；
- `local`：目标地区有效A级文件；
- `conflict`：待复核、效力不明或冲突材料。

没有 `support` 时，旧接口返回空证据，V7 继续执行失败关闭和人工复核。

## 本地哈希向量

标准库环境使用固定512维 hashing vector：

- 中文单字、二元和三元片段；
- 英文、数字和百分比token；
- 税务领域同义规范化，例如“百分之一”和“1%征收率”；
- SHA256映射、带符号累加、L2归一化和余弦相似度。

它用于扩大召回，不用于判断法规是否有效，也不替代专业 embedding 模型。

## 可选 Embedding Provider

Provider 接口：

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

外部 provider 只接收税种、地域、查询角色和白名单关键词，不发送完整业务描述、合同、身份证号或发票信息。Provider失败时自动回退本地哈希向量，并在 `retrieval_trace.provider_errors` 记录原因。

## 检索审计

每次分析记录：

- QueryPlan及全部子查询；
- 门禁前后分块数；
- 每个子查询的BM25与向量候选数量；
- 使用的provider与回退原因；
- 关系扩展数量；
- 最终证据数量；
- 每条证据的评分构成和命中原因。

持久案件会随 `evidence-vNNN.json` 自动生成同版本的 `retrieval-vNNN.json`。

## 运行评测

```bash
python3 -m unittest discover -s apps/tax_retrieval/tests -v
```

30题语料位于：

```text
11-问题测试集/v7_1_retrieval_cases.jsonl
```

覆盖起征点、1%政策、不动产排除、放弃免税、一般纳税人登记、新疆覆盖、海南零关税门禁、历史废止文件、2028年政策到期和检索轨迹。

## 当前边界

- 新疆现有种子库尚缺可直接作为A级依据的地方增值税文件；系统仍生成local查询，但不会把B级转载冒充A级地方证据。
- 海南特殊政策只能提供资格和资料门禁，不替代海关商品归类或主管机关认定。
- V7.1不建设云端向量库，也不自动对全部中国税法建立图数据库。
