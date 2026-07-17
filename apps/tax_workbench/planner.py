from __future__ import annotations

from datetime import date
from pathlib import Path

from .models import EvidenceItem, PlanningResult, SchemeOption, TaxFacts
from .retrieval import EvidenceRetriever


KB_VERSION = "KB-2026.07.17-V5-PILOT-XJ-HI"
VERIFIED_AT = "2026-07-17"


class TaxPlanningService:
    def __init__(self, vault: Path):
        self.vault = Path(vault).resolve()
        self.retriever = EvidenceRetriever(self.vault)

    @staticmethod
    def _date_between(raw: str, start: str, end: str) -> bool:
        value = date.fromisoformat(raw)
        return date.fromisoformat(start) <= value <= date.fromisoformat(end)

    def _threshold_conclusion(self, facts: TaxFacts) -> tuple[str, bool]:
        if facts.vat_status != "小规模纳税人" or not self._date_between(facts.business_date, "2026-01-01", "2027-12-31"):
            return "尚不能直接适用2026—2027年小规模纳税人起征点结论。", False
        threshold = {"月": 100000, "季度": 300000, "单次": 1000}.get(facts.amount_period)
        if threshold is None or facts.amount is None:
            return "需要根据实际计税期间进一步判断起征点。", False
        period_name = {"月": "月10万元", "季度": "季度30万元", "单次": "每次（日）1000元"}[facts.amount_period]
        if facts.amount <= threshold:
            return (
                f"在已提供事实下，销售额未超过{period_name}起征点，初步具备进入增值税免税判断的条件；"
                "仍需合并同一计税期间全部应税交易，并确认是否放弃免税开具专用发票。",
                True,
            )
        return f"当前销售额超过{period_name}起征点，不能仅依起征点免税，需要继续判断适用征收率和其他优惠。", False

    def _regional_application(self, facts: TaxFacts) -> str:
        if facts.region == "CN-XJ":
            return "新疆事项采用全国增值税规则底座，并叠加新疆正式地方文件或执行口径；地方解读不得推翻上位法。"
        if facts.region == "CN-HI":
            special = facts.hainan_special_scene or facts.transaction_type == "进口货物" or facts.cross_border
            if special:
                return (
                    "该事项可能进入海南自贸港特殊政策门禁，必须核验业务日期、享惠主体、HS编码、商品目录、"
                    "一线/二线流向、用途和监管资料，不能仅因注册地在海南认定零关税。"
                )
            return "该事项属于海南普通境内服务或交易，先适用全国增值税规则，不因注册在海南而自动适用零关税。"
        return "适用全国税收法规，不叠加新疆或海南地域覆盖层。"

    def _risk_flags(self, facts: TaxFacts, missing: list[str]) -> tuple[list[str], bool]:
        risks: list[str] = []
        review = False
        if facts.related_party:
            risks.append("存在关联交易或关联主体分拆信号，需核对人员、资产、业务、合同、资金流和定价合理性。")
            review = True
        if "分拆" in facts.description:
            risks.append("不得通过人为分拆主体、合同、收入或发票规避起征点或一般纳税人登记。")
            review = True
        flags = [
            (facts.cross_border, "涉及跨境交易，应核验扣缴、进口环节税费、常设机构或海关规则。"),
            (facts.historical_tax, "涉及历史补税，应按业务发生时点适用当期法规并保留历史版本证据。"),
            (facts.real_estate or facts.transaction_type == "不动产", "涉及不动产，不能直接套用小规模3%减按1%政策。"),
            (facts.restructuring, "涉及企业重组，需联动企业所得税、增值税、契税、印花税等多税种复核。"),
            (facts.tax_audit, "涉及稽查、处罚或争议，必须由专业人员审阅完整证据。"),
        ]
        for active, message in flags:
            if active:
                risks.append(message)
                review = True
        hainan_gate = facts.region == "CN-HI" and (
            facts.hainan_special_scene or facts.transaction_type == "进口货物" or facts.cross_border
        )
        if hainan_gate:
            review = True
            if missing:
                risks.append("海南特殊政策关键资料缺失，当前不得确定可适用零关税或其他自贸港优惠。")
            else:
                risks.append("海南享惠主体、商品编码和流向属于高风险认定事项，仍需人工审签。")
        return risks, review

    def _schemes(self, facts: TaxFacts, threshold_ok: bool, missing: list[str]) -> list[SchemeOption]:
        within_temp_policy = self._date_between(facts.business_date, "2026-01-01", "2027-12-31")
        non_property = facts.transaction_type in {"服务", "货物", "无形资产", "其他"}
        one_percent = facts.vat_status == "小规模纳税人" and within_temp_policy and non_property

        hainan_gate = facts.region == "CN-HI" and (
            facts.hainan_special_scene or facts.transaction_type == "进口货物" or facts.cross_border
        )
        if hainan_gate:
            return [
                SchemeOption(
                    name="方案A｜普通税制合规基线",
                    summary="在海南特殊资格尚未确认前，按正常进口或境内税制建立保守预算，不提前把零关税计入报价。",
                    actions=["确认交易路径和报关主体", "按普通税制测算税费上限", "将优惠作为审批通过后的敏感性情景"],
                    benefits=["避免优惠落空导致补税和现金流缺口", "报价和合同更稳健"],
                    risks=["税负预算较高，但属于保守基线"],
                    required_documents=["进口合同", "商品说明", "付款与物流安排"],
                ),
                SchemeOption(
                    name="方案B｜海南特殊政策资格预审",
                    summary="补齐HS编码、享惠主体、商品目录和一线/二线流向后，再判断零关税或加工增值政策。",
                    actions=["完成商品归类", "核验享惠主体资格", "核对进口征税目录及贸易救济", "形成用途和后续处置闭环"],
                    benefits=["在合法条件满足时降低进口环节税负", "形成可供海关和税务核验的证据链"],
                    risks=["资格和编码认定不确定", "资料或实际流向不符可能被追税"],
                    required_documents=["HS编码归类资料", "享惠主体证明", "报关单", "物流和用途台账"] + missing,
                ),
                SchemeOption(
                    name="方案C｜交易与现金流分阶段安排",
                    summary="在真实业务不变的前提下，按审批、进口、生产或销售节点安排合同付款和税费预算。",
                    actions=["设置优惠获批前后两套现金流情景", "合同中明确税费承担和政策变化条款", "重大进口前完成书面专业复核"],
                    benefits=["降低政策认定时间差造成的现金流压力", "避免合同税费承担不清"],
                    risks=["不得虚构流向或改变报关事实", "合同安排不能替代政策资格"],
                    required_documents=["交易流程图", "合同草案", "现金流测算", "审签记录"],
                ),
            ]

        baseline_summary = (
            "以当前主体和真实交易为基线，核对同一计税期间全部销售额并依法申报。"
            + ("初步可按起征点免税方向处理。" if threshold_ok else "当前不能仅依起征点免税。")
        )
        invoice_summary = (
            "普通发票需求下优先保留起征点优惠并做好销售额台账。"
            if facts.invoice_need != "专用发票"
            else "评估客户专票需求与放弃免税的税负、报价和现金流影响，按实际选择开票。"
        )
        rate_summary = (
            "超过起征点或放弃免税时，符合条件的3%征收率交易可评估2026—2027年减按1%。"
            if one_percent else
            "根据交易性质和纳税人身份重新确定税率或征收率，不预设1%优惠。"
        )
        return [
            SchemeOption(
                name="方案A｜合规基线",
                summary=baseline_summary,
                actions=["核对全部应税交易销售额", "确认计税期间", "保存合同、发票、收款和申报记录"],
                benefits=["执行路径简单", "争议风险最低"],
                risks=["遗漏其他销售额会导致起征点判断错误"],
                required_documents=["销售台账", "合同", "发票清单", "申报表"],
                estimated_tax="达到起征点条件且未放弃免税时，初步增值税为0；最终以完整销售额和申报为准" if threshold_ok else "需按适用征收率和完整计税依据测算",
            ),
            SchemeOption(
                name="方案B｜发票与申报协同",
                summary=invoice_summary + rate_summary,
                actions=["向客户确认发票类型", "对比免税与开专票后的报价", "确保发票征收率与申报一致"],
                benefits=["兼顾客户需求和现金流", "避免发票与申报不一致"],
                risks=["放弃免税可能增加税负", "不得为取得专票收益虚构交易"],
                required_documents=["客户发票要求", "报价单", "开票记录", "申报测算"],
            ),
            SchemeOption(
                name="方案C｜纳税人身份与增长评估",
                summary="结合未来12个月销售额、进项结构和客户专票需求，评估继续小规模或依法登记一般纳税人的边界。",
                actions=["预测连续12个月/4季度销售额", "测算可抵扣进项", "比较小规模与一般纳税人综合成本"],
                benefits=["提前管理超过500万元登记风险", "为业务增长和报价留出空间"],
                risks=["不得人为分拆关联主体规避登记", "身份转换影响开票、进项和内部管理"],
                required_documents=["销售预测", "进项发票结构", "客户结构", "主体关联关系图"],
            ),
        ]

    def analyze(self, facts: TaxFacts) -> PlanningResult:
        errors = facts.validate()
        if errors:
            raise ValueError("; ".join(errors))
        missing = facts.missing_facts()
        evidence: list[EvidenceItem] = self.retriever.search(facts, top_k=8)
        initial, threshold_ok = self._threshold_conclusion(facts)
        regional = self._regional_application(facts)
        risks, review = self._risk_flags(facts, missing)
        if facts.region == "CN-HI" and (
            facts.hainan_special_scene or facts.transaction_type == "进口货物" or facts.cross_border
        ) and missing:
            initial = "海南自贸港特殊政策关键事实不足，目前不能确定零关税或其他优惠是否适用。"
        if not evidence:
            risks.append("未检索到足够的A级有效法规证据，当前结论只能作为事实采集草案。")
            review = True
        conditions = [
            f"地区：{facts.region}", f"纳税人类型：{facts.taxpayer_type}", f"增值税身份：{facts.vat_status}",
            f"业务时间：{facts.business_date}", f"交易类型：{facts.transaction_type}",
            f"金额及期间：{facts.amount} / {facts.amount_period}", f"发票需求：{facts.invoice_need}",
        ]
        return PlanningResult(
            initial_conclusion=initial,
            applicable_conditions=conditions,
            evidence=evidence,
            explanation=(
                "系统先用业务日期、地域和主体身份过滤法规，再检索A级条款。方案是基于当前事实的合法合规选择，"
                "不是通过改变真实交易或分拆收入制造税收结果。"
            ),
            regional_application=regional,
            schemes=self._schemes(facts, threshold_ok, missing),
            risks=risks,
            missing_facts=missing,
            human_review_required=review,
            kb_version=KB_VERSION,
            verified_at=VERIFIED_AT,
        )
