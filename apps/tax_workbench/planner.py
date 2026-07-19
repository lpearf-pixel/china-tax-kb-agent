from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.tax_decision_core.cit_calculator import CitCalculationContext, CitCalculator
from apps.tax_decision_core.cit_issues import CitIssueEngine
from apps.tax_decision_core.domain import CalculationResult, CaseState, RuleEvaluationStatus
from apps.tax_decision_core.fact_graph import FactGraphService
from apps.tax_decision_core.issues import IssueEngine
from apps.tax_decision_core.multitax import MultiTaxScenarioAggregator
from apps.tax_decision_core.rule_engine import EvaluationBundle, RuleEngine
from apps.tax_decision_core.rule_loader import RuleLoader
from apps.tax_decision_core.scenarios import PlanningObjective, ScenarioEngine
from apps.tax_decision_core.storage import CaseStorage
from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_decision_core.vat_calculator import CalculationContext, VatCalculator
from apps.tax_decision_core.workflow import CaseWorkflow

from .models import PlanningResult, TaxFacts
from .multitax_models import MultiTaxSchemeOption, TaxAmount
from .retrieval import EvidenceRetriever

KB_VERSION = "KB-2026.07.17-V5-PILOT-XJ-HI"
VERIFIED_AT = "2026-07-19"


class TaxPlanningService:
    def __init__(self, vault: Path, *, retriever=None, rule_loader=None, case_root: Path | None = None):
        self.vault = Path(vault).resolve()
        self.retriever = retriever or EvidenceRetriever(self.vault)
        self.rule_loader = rule_loader or RuleLoader(self.vault / "rules", vault=self.vault)
        self.adapter = V6Adapter()
        self.vat_issue_engine = IssueEngine()
        self.cit_issue_engine = CitIssueEngine()
        self.rule_engine = RuleEngine()
        self.vat_calculator = VatCalculator()
        self.cit_calculator = CitCalculator()
        self.scenario_engine = ScenarioEngine()
        self.multitax_aggregator = MultiTaxScenarioAggregator()
        self.storage = CaseStorage(case_root or self.vault / "cases")
        self.fact_service = FactGraphService(self.storage)
        self.workflow = CaseWorkflow(self.storage)

    def _evidence(self, facts: TaxFacts):
        return list(self.retriever.search(facts, top_k=10))

    @staticmethod
    def _selected(bundle: EvaluationBundle, group: str):
        return bundle.selected.get(group)

    @staticmethod
    def _evaluation(bundle: EvaluationBundle, rule_id: str):
        return next((item for item in bundle.evaluations if item.rule_id == rule_id), None)

    def _vat_calculations(self, facts: TaxFacts, bundle: EvaluationBundle) -> list[CalculationResult]:
        if not bundle.evaluations:
            return [CalculationResult(
                "calc-rule-set-missing", "unable_to_calculate", "增值税",
                inputs={"scenario_name": "目标日期规则集待更新", "decision_variables": {}},
                missing_fact_ids=["rules.valid_on_rule_set"],
                formula="目标业务日期没有加载到可用增值税规则，停止确定性计算。",
            )]
        threshold = self._selected(bundle, "vat_threshold")
        threshold_ok = bool(
            threshold and threshold.status == RuleEvaluationStatus.APPLICABLE
            and threshold.outcome == "threshold_exempt_candidate" and threshold.value is True
        )
        rate_eval = self._selected(bundle, "vat_levy_rate")
        hainan = facts.region == "CN-HI" and (
            facts.hainan_special_scene or facts.transaction_type == "进口货物" or facts.cross_border
        )
        if hainan or (rate_eval and rate_eval.outcome == "levy_rate_excluded"):
            return [CalculationResult(
                "calc-baseline", "unable_to_calculate", "增值税",
                inputs={"scenario_name": "普通税制保守基线", "decision_variables": {}},
                missing_fact_ids=facts.missing_facts() or ["applicable_levy_rate"],
                formula="特殊或排除场景缺少可确定的增值税税率。",
            )]
        rate = (
            Decimal(str(rate_eval.value))
            if rate_eval and rate_eval.outcome == "levy_rate"
            else Decimal(str(facts.extra.get("original_levy_rate", "0.03")))
            if facts.vat_status == "小规模纳税人" else None
        )
        due = date.fromisoformat(facts.business_date) + timedelta(days=30)
        applicable = [
            item.rule_id for item in bundle.evaluations
            if item.status == RuleEvaluationStatus.APPLICABLE
        ]
        baseline = self.vat_calculator.calculate(CalculationContext(
            "calc-baseline", facts.vat_status, facts.amount, facts.amount_tax_inclusive,
            rate, threshold_ok, False, "普通发票", payment_due_date=due, rule_ids=applicable,
        ))
        baseline.inputs.update({
            "scenario_name": "合规基线",
            "decision_variables": {"invoice_type": "普通发票", "waive_exemption": False},
        })
        invoice = self.vat_calculator.calculate(CalculationContext(
            "calc-invoice", facts.vat_status, facts.amount, facts.amount_tax_inclusive,
            rate, threshold_ok, True, "专用发票", payment_due_date=due, rule_ids=applicable,
        ))
        invoice.inputs.update({
            "scenario_name": "发票与申报协同",
            "decision_variables": {"invoice_type": "专用发票", "waive_exemption": True},
        })
        growth = CalculationResult(
            "calc-growth", "conditional_determinate", "增值税",
            taxable_amount=baseline.taxable_amount,
            tax_amount=baseline.tax_amount,
            payable_or_credit=baseline.payable_or_credit,
            formula="基于当前身份的增长敏感性基线；登记一般纳税人后需补充进项和适用税率",
            inputs={
                "scenario_name": "纳税人身份与增长评估",
                "decision_variables": {"voluntary_general_taxpayer": True},
            },
            rule_ids=applicable,
        )
        return [baseline, invoice, growth]

    def _cit_calculation(self, facts: TaxFacts, bundle: EvaluationBundle) -> CalculationResult:
        excluded = self._evaluation(bundle, "CIT-SOLE-PROP-PARTNERSHIP-EXCLUSION")
        if excluded and excluded.status == RuleEvaluationStatus.APPLICABLE and excluded.value is True:
            return CalculationResult(
                "cit-not-applicable", "not_applicable", "企业所得税",
                taxable_amount=Decimal("0"), tax_amount=Decimal("0"), payable_or_credit=Decimal("0"),
                formula="当前实体形式不适用企业所得税法，后续由个人所得税模块处理。",
                rule_ids=[excluded.rule_id],
            )
        nonresident = self._evaluation(bundle, "CIT-NONRESIDENT-MANUAL-REVIEW")
        if nonresident and nonresident.status == RuleEvaluationStatus.MANUAL_REVIEW_REQUIRED:
            return CalculationResult(
                "cit-nonresident-review", "unable_to_calculate", "企业所得税",
                formula="非居民企业所得税需核验所得来源、机构场所和扣缴规则。",
                missing_fact_ids=["cit.nonresident_scope"], rule_ids=[nonresident.rule_id],
            )
        if not bundle.evaluations:
            return CalculationResult(
                "cit-rule-set-missing", "unable_to_calculate", "企业所得税",
                formula="目标日期没有加载到有效企业所得税规则。",
                missing_fact_ids=["rules.valid_on_cit_rule_set"],
            )
        general = self._evaluation(bundle, "CIT-RESIDENT-GENERAL-RATE-25")
        eligible = self._evaluation(bundle, "CIT-SMALL-LOW-PROFIT-ELIGIBILITY-2023-2027")
        ratio_eval = self._evaluation(bundle, "CIT-SMALL-LOW-PROFIT-TAXABLE-RATIO-2023-2027")
        small_rate = self._evaluation(bundle, "CIT-SMALL-LOW-PROFIT-RATE-2023-2027")
        small = bool(
            eligible and eligible.status == RuleEvaluationStatus.APPLICABLE and eligible.value is True
            and ratio_eval and ratio_eval.status == RuleEvaluationStatus.APPLICABLE
            and small_rate and small_rate.status == RuleEvaluationStatus.APPLICABLE
        )
        rate = Decimal(str(small_rate.value)) if small else (
            Decimal(str(general.value))
            if general and general.status == RuleEvaluationStatus.APPLICABLE else None
        )
        ratio = Decimal(str(ratio_eval.value)) if small else Decimal("1")
        applicable = [
            item.rule_id for item in bundle.evaluations
            if item.status == RuleEvaluationStatus.APPLICABLE
        ]
        business_year = date.fromisoformat(facts.business_date).year
        return self.cit_calculator.calculate(CitCalculationContext(
            calculation_id="cit-baseline",
            accounting_profit=facts.cit_accounting_profit,
            adjustment_increase=facts.cit_adjustment_increase,
            adjustment_decrease=facts.cit_adjustment_decrease,
            loss_carryforward=facts.cit_loss_carryforward,
            tax_rate=rate,
            taxable_income_ratio=ratio,
            tax_credit=facts.cit_tax_credit,
            prepaid_tax=facts.cit_prepaid_tax,
            payment_due_date=date(business_year + 1, 5, 31),
            rule_ids=applicable,
        ))

    @staticmethod
    def _merge_bundles(*bundles: EvaluationBundle) -> EvaluationBundle:
        combined = EvaluationBundle()
        for bundle in bundles:
            combined.evaluations.extend(bundle.evaluations)
            combined.selected.update(bundle.selected)
            combined.conflicts.extend(bundle.conflicts)
        return combined

    def _run(self, facts: TaxFacts, case_id: str | None = None):
        errors = facts.validate()
        if errors:
            raise ValueError("; ".join(errors))
        case, graph = self.adapter.to_v7(facts, case_id)
        valid_on = date.fromisoformat(facts.business_date)

        vat_bundle = EvaluationBundle()
        vat_issues = []
        vat_calculations: list[CalculationResult] = []
        vat_scenarios = []
        if "增值税" in facts.requested_tax_types:
            vat_rules = self.rule_loader.load(valid_on, facts.region, "增值税")
            vat_bundle = self.rule_engine.evaluate_all(vat_rules, graph, valid_on)
            vat_issues = self.vat_issue_engine.identify(case, graph)
            vat_calculations = self._vat_calculations(facts, vat_bundle)
            vat_scenarios = self.scenario_engine.generate(
                case, vat_issues, vat_bundle.evaluations + vat_bundle.conflicts, vat_calculations
            )

        cit_bundle = EvaluationBundle()
        cit_issues = []
        cit_calculations: list[CalculationResult] = []
        if "企业所得税" in facts.requested_tax_types:
            cit_rules = self.rule_loader.load(valid_on, facts.region, "企业所得税")
            cit_bundle = self.rule_engine.evaluate_all(cit_rules, graph, valid_on)
            cit_issues = self.cit_issue_engine.identify(case, graph)
            cit_calculations = [self._cit_calculation(facts, cit_bundle)]

        combined_bundle = self._merge_bundles(vat_bundle, cit_bundle)
        issues = vat_issues + cit_issues
        calculations = vat_calculations + cit_calculations
        scenarios = (
            self.multitax_aggregator.combine(vat_scenarios, cit_calculations)
            if cit_calculations else vat_scenarios
        )
        if any(issue.risk_level == "high" or issue.status == "manual_review_required" for issue in cit_issues):
            for scenario in scenarios:
                scenario.human_review_required = True
        scores = self.scenario_engine.rank(
            scenarios,
            PlanningObjective(
                desired_invoice_type=facts.invoice_need
                if facts.invoice_need in {"普通发票", "专用发票"} else ""
            ),
        )
        evidence = self._evidence(facts)
        return case, graph, combined_bundle, issues, calculations, scenarios, scores, evidence

    def _result(self, facts, case, graph, bundle, issues, calculations, scenarios, scores, evidence):
        vat_requested = "增值税" in facts.requested_tax_types
        cit_requested = "企业所得税" in facts.requested_tax_types
        threshold = self._selected(bundle, "vat_threshold")
        threshold_ok = bool(threshold and threshold.status == RuleEvaluationStatus.APPLICABLE)
        special = facts.region == "CN-HI" and (
            facts.hainan_special_scene or facts.transaction_type == "进口货物" or facts.cross_border
        )
        cit_calc = next((item for item in calculations if item.tax_type == "企业所得税"), None)

        if not vat_requested and cit_requested:
            if cit_calc and cit_calc.status == "determinate":
                initial = f"企业所得税已完成初步计算，应纳所得税额为 {cit_calc.tax_amount}，应补退税候选为 {cit_calc.payable_or_credit}。"
            elif cit_calc and cit_calc.status == "not_applicable":
                initial = "当前实体形式不适用企业所得税法，本模块不计算企业所得税。"
            else:
                initial = "企业所得税关键事实或适用范围不足，当前不能输出确定税额。"
        elif special:
            initial = "海南自贸港特殊政策关键事实不足，目前不能确定零关税或其他优惠是否适用。"
        elif vat_requested and threshold_ok:
            initial = (
                {"月": "月10万元", "季度": "季度30万元", "单次": "每次（日）1000元"}.get(facts.amount_period, "起征点")
                + "起征点条件已由规则引擎初步命中；仍需确认同期间全部销售额和是否放弃免税。"
            )
        else:
            initial = "当前未命中增值税起征点候选，需按规则结果继续计算。"
        if vat_requested and cit_requested and cit_calc:
            initial += f" 企业所得税已纳入综合方案，当前应纳所得税额为 {cit_calc.tax_amount if cit_calc.tax_amount is not None else '待补资料'}。"

        regional = (
            "新疆事项采用全国规则底座并叠加新疆覆盖层。"
            if facts.region == "CN-XJ" else
            "该事项进入海南特殊政策门禁，享惠主体、HS编码、流向和用途必须人工复核。"
            if facts.region == "CN-HI" and special else
            "海南普通境内业务先适用全国税收规则。"
            if facts.region == "CN-HI" else "适用全国税收法规。"
        )
        calc_by_id = {item.calculation_id: item for item in calculations}
        schemes = []
        for scenario in scenarios:
            related = [calc_by_id[cid] for cid in scenario.calculation_ids if cid in calc_by_id]
            formulas = [item.formula for item in related if item.formula]
            summary = "；".join(dict.fromkeys(formulas)) or "需要补齐资料后计算。"
            if any(item.inputs.get("levy_rate") == Decimal("0.01") for item in related):
                summary += "；符合条件时体现1%征收率方向。"
            breakdown = {
                key: TaxAmount(value)
                for key, value in dict(getattr(scenario, "tax_breakdown", {}) or {}).items()
            }
            schemes.append(MultiTaxSchemeOption(
                name=scenario.name,
                summary=summary,
                actions=["确认事实和规则命中", "核对发票、申报和付款时间", "正式执行前保存完整资料链"],
                benefits=["税额和现金流可追溯", "税种分项和评分构成透明"],
                risks=list(scenario.risks),
                required_documents=list(scenario.required_documents),
                estimated_tax=str(scenario.total_tax) if scenario.total_tax is not None else "无法确定",
                tax_breakdown=breakdown,
            ))

        risks = list(dict.fromkeys(risk for scenario in scenarios for risk in scenario.risks))
        missing = list(dict.fromkeys(
            facts.missing_facts()
            + [fact_id for issue in issues for fact_id in issue.missing_fact_ids]
            + [fact_id for calc in calculations for fact_id in calc.missing_fact_ids]
        ))
        review = (
            any(scenario.human_review_required for scenario in scenarios)
            or bool(bundle.conflicts)
            or any(issue.risk_level == "high" or issue.status == "manual_review_required" for issue in issues)
        )
        vat_rule_present = any(item.rule_id.startswith(("VAT-", "HI-")) for item in bundle.evaluations)
        cit_rule_present = any(item.rule_id.startswith("CIT-") for item in bundle.evaluations)
        if vat_requested and not vat_rule_present:
            risks.append("目标日期缺少已验证增值税规则集。")
            missing.append("目标日期有效增值税规则集")
            review = True
        if cit_requested and not cit_rule_present:
            risks.append("目标日期缺少已验证企业所得税规则集。")
            missing.append("目标日期有效企业所得税规则集")
            review = True
        if not evidence:
            risks.append("未检索到足够的A级有效法规证据，当前结果不得作为确定结论。")
            missing.append("A级有效法规证据")
            review = True

        return PlanningResult(
            initial_conclusion=initial,
            applicable_conditions=[
                f"分析税种：{', '.join(facts.requested_tax_types)}",
                f"地区：{facts.region}",
                f"纳税人类型：{facts.taxpayer_type}",
                f"增值税身份：{facts.vat_status}",
                f"企业实体形式：{facts.entity_form or '未选择'}",
                f"业务时间：{facts.business_date}",
                f"交易类型：{facts.transaction_type}",
            ],
            evidence=evidence,
            explanation="系统已通过事实图谱、分税种规则引擎和Decimal计算器生成结果。",
            regional_application=regional,
            schemes=schemes,
            risks=list(dict.fromkeys(risks)),
            missing_facts=list(dict.fromkeys(missing)),
            human_review_required=review,
            kb_version=KB_VERSION,
            verified_at=VERIFIED_AT,
            case_id=case.case_id,
            case_state=case.state.value,
            issues=[item.to_dict() for item in issues],
            rule_trace=[item.to_dict() for item in bundle.evaluations + bundle.conflicts],
            calculations=[item.to_dict() for item in calculations],
            scenario_scores=[{
                "scenario_id": score.scenario_id,
                "total_score": str(score.total_score),
                "components": {key: str(value) for key, value in score.components.items()},
            } for score in scores],
        )

    def analyze(self, facts: TaxFacts, *, case_id: str | None = None):
        artifacts = self._run(facts, case_id)
        result = self._result(facts, *artifacts)
        if case_id is None:
            result.case_id = ""
            result.case_state = "stateless_analysis"
        return result

    def _next(self, case_id, kind):
        try:
            return self.storage.latest_version(case_id, kind) + 1
        except FileNotFoundError:
            return 1

    def _persist(self, facts, artifacts, result, create=False):
        case, graph, bundle, issues, calculations, scenarios, scores, evidence = artifacts
        if create:
            self.storage.create(case)
            self.storage.write_version(case.case_id, "facts", 1, graph.to_dict())
        for kind, payload in (
            ("issues", {"issues": [item.to_dict() for item in issues]}),
            ("evidence", {"items": [item.to_dict() for item in evidence]}),
            ("decisions", {"evaluations": [item.to_dict() for item in bundle.evaluations + bundle.conflicts]}),
            ("calculations", {"calculations": [item.to_dict() for item in calculations]}),
            ("scenarios", {"scenarios": [item.to_dict() for item in scenarios], "scores": result.scenario_scores}),
        ):
            self.storage.write_version(case.case_id, kind, self._next(case.case_id, kind), payload)
        saved = self.storage.load(case.case_id)
        saved.issues_version = self.storage.latest_version(case.case_id, "issues")
        saved.calculations_version = self.storage.latest_version(case.case_id, "calculations")
        saved.scenarios_version = self.storage.latest_version(case.case_id, "scenarios")
        saved.state = CaseState.HUMAN_REVIEW_PENDING if result.human_review_required else CaseState.SCENARIOS_READY
        saved.updated_at = datetime.now(timezone.utc)
        self.storage.update_case(saved)
        result.case_state = saved.state.value
        self.storage.append_event(case.case_id, {
            "event": "analysis_persisted", "at": saved.updated_at.isoformat(),
            "facts_version": saved.facts_version, "issues_version": saved.issues_version,
            "calculations_version": saved.calculations_version, "scenarios_version": saved.scenarios_version,
        })
        return result

    def create_case(self, facts: TaxFacts):
        case_id = f"case-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
        artifacts = self._run(facts, case_id)
        return self._persist(facts, artifacts, self._result(facts, *artifacts), create=True)

    def analyze_case(self, case_id: str):
        facts = self.adapter.from_graph(self.fact_service.load_graph(case_id))
        artifacts = self._run(facts, case_id)
        return self._persist(facts, artifacts, self._result(facts, *artifacts), create=False)

    def get_case(self, case_id: str):
        case = self.storage.load(case_id)
        payload = {"case": case.to_dict(), "facts": self.fact_service.load_graph(case_id).to_dict()}
        for kind in ("issues", "evidence", "decisions", "calculations", "scenarios"):
            try:
                payload[kind] = self.storage.load_version(case_id, kind, self.storage.latest_version(case_id, kind))
            except FileNotFoundError:
                payload[kind] = None
        return payload

    def revise_case_fact(self, case_id: str, fact_id: str, value: Any, actor: str = "user"):
        impact = self.fact_service.revise_fact(case_id, fact_id, value, actor)
        rerun = self.workflow.replay_affected(case_id, impact.affected_nodes)
        return {
            "fact_id": fact_id, "new_version": impact.new_version,
            "affected_nodes": list(impact.affected_nodes), "rerun_nodes": list(rerun),
            "case_state": self.storage.load(case_id).state.value,
        }

    def review_case(self, case_id: str, approved: bool, actor: str, note: str = ""):
        state = self.workflow.record_review(case_id, approved, actor, note)
        return {"case_id": case_id, "state": state.value}

    def audit_case(self, case_id: str):
        self.storage.load(case_id)
        path = self.storage.root / case_id / "timeline.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
