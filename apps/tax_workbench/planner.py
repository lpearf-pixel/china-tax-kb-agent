from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from apps.tax_decision_core.domain import (
    CalculationResult,
    CaseState,
    RuleEvaluationStatus,
)
from apps.tax_decision_core.fact_graph import FactGraphService
from apps.tax_decision_core.issues import IssueEngine
from apps.tax_decision_core.rule_engine import RuleEngine
from apps.tax_decision_core.rule_loader import RuleLoader
from apps.tax_decision_core.scenarios import PlanningObjective, ScenarioEngine
from apps.tax_decision_core.storage import CaseStorage
from apps.tax_decision_core.v6_adapter import V6Adapter
from apps.tax_decision_core.vat_calculator import CalculationContext, VatCalculator
from apps.tax_decision_core.workflow import CaseWorkflow

from .models import EvidenceItem, PlanningResult, SchemeOption, TaxFacts
from .retrieval import EvidenceRetriever

KB_VERSION = "KB-2026.07.17-V5-PILOT-XJ-HI"
VERIFIED_AT = "2026-07-18"


class TaxPlanningService:
    def __init__(
        self,
        vault: Path,
        *,
        retriever=None,
        rule_loader=None,
        case_root: Path | None = None,
    ):
        self.vault = Path(vault).resolve()
        self.retriever = retriever or EvidenceRetriever(self.vault)
        self.rule_loader = rule_loader or RuleLoader(
            self.vault / "rules",
            vault=self.vault,
        )
        self.adapter = V6Adapter()
        self.issue_engine = IssueEngine()
        self.rule_engine = RuleEngine()
        self.calculator = VatCalculator()
        self.scenario_engine = ScenarioEngine()
        self.storage = CaseStorage(case_root or self.vault / "cases")
        self.fact_service = FactGraphService(self.storage)
        self.workflow = CaseWorkflow(self.storage)

    def _evidence(self, facts: TaxFacts) -> list[EvidenceItem]:
        return list(self.retriever.search(facts, top_k=8))

    @staticmethod
    def _selected(bundle, group: str):
        return bundle.selected.get(group)

    def _calculations(self, facts: TaxFacts, bundle) -> list[CalculationResult]:
        threshold = self._selected(bundle, "vat_threshold")
        threshold_ok = bool(
            threshold
            and threshold.status == RuleEvaluationStatus.APPLICABLE
            and threshold.outcome == "threshold_exempt_candidate"
            and threshold.value is True
        )
        rate_evaluation = self._selected(bundle, "vat_levy_rate")
        hainan_special = facts.region == "CN-HI" and (
            facts.hainan_special_scene
            or facts.transaction_type == "进口货物"
            or facts.cross_border
        )
        if hainan_special or (
            rate_evaluation and rate_evaluation.outcome == "levy_rate_excluded"
        ):
            return [
                CalculationResult(
                    calculation_id="calc-baseline",
                    status="unable_to_calculate",
                    tax_type="增值税",
                    inputs={
                        "scenario_name": "普通税制保守基线",
                        "decision_variables": {},
                    },
                    missing_fact_ids=facts.missing_facts()
                    or ["applicable_levy_rate"],
                )
            ]

        levy_rate = (
            Decimal(str(rate_evaluation.value))
            if rate_evaluation and rate_evaluation.outcome == "levy_rate"
            else (
                Decimal(str(facts.extra.get("original_levy_rate", "0.03")))
                if facts.vat_status == "小规模纳税人"
                else None
            )
        )
        payment_due = date.fromisoformat(facts.business_date) + timedelta(days=30)
        applicable_rule_ids = [
            evaluation.rule_id
            for evaluation in bundle.evaluations
            if evaluation.status == RuleEvaluationStatus.APPLICABLE
        ]

        baseline = self.calculator.calculate(
            CalculationContext(
                calculation_id="calc-baseline",
                taxpayer_status=facts.vat_status,
                amount=facts.amount,
                amount_tax_inclusive=facts.amount_tax_inclusive,
                levy_rate=levy_rate,
                threshold_exempt_candidate=threshold_ok,
                waive_exemption=False,
                invoice_type="普通发票",
                payment_due_date=payment_due,
                rule_ids=applicable_rule_ids,
            )
        )
        baseline.inputs.update(
            {
                "scenario_name": "合规基线",
                "decision_variables": {
                    "invoice_type": "普通发票",
                    "waive_exemption": False,
                },
            }
        )

        invoice = self.calculator.calculate(
            CalculationContext(
                calculation_id="calc-invoice",
                taxpayer_status=facts.vat_status,
                amount=facts.amount,
                amount_tax_inclusive=facts.amount_tax_inclusive,
                levy_rate=levy_rate,
                threshold_exempt_candidate=threshold_ok,
                waive_exemption=True,
                invoice_type="专用发票",
                payment_due_date=payment_due,
                rule_ids=applicable_rule_ids,
            )
        )
        invoice.inputs.update(
            {
                "scenario_name": "发票与申报协同",
                "decision_variables": {
                    "invoice_type": "专用发票",
                    "waive_exemption": True,
                },
            }
        )

        growth = CalculationResult(
            calculation_id="calc-growth",
            status="conditional_determinate",
            tax_type="增值税",
            taxable_amount=baseline.taxable_amount,
            tax_amount=baseline.tax_amount,
            payable_or_credit=baseline.payable_or_credit,
            formula=(
                "基于当前身份的增长敏感性基线；登记一般纳税人后需补充"
                "进项结构和具体适用税率。"
            ),
            inputs={
                "scenario_name": "纳税人身份与增长评估",
                "decision_variables": {"voluntary_general_taxpayer": True},
            },
            rule_ids=applicable_rule_ids,
        )
        return [baseline, invoice, growth]

    def _run(self, facts: TaxFacts, case_id: str | None = None):
        errors = facts.validate()
        if errors:
            raise ValueError("; ".join(errors))
        case, graph = self.adapter.to_v7(facts, case_id)
        valid_on = date.fromisoformat(facts.business_date)
        rules = self.rule_loader.load(valid_on, facts.region, "增值税")
        bundle = self.rule_engine.evaluate_all(rules, graph, valid_on)
        issues = self.issue_engine.identify(case, graph)
        calculations = self._calculations(facts, bundle)
        scenarios = self.scenario_engine.generate(
            case,
            issues,
            bundle.evaluations + bundle.conflicts,
            calculations,
        )
        objective = PlanningObjective(
            desired_invoice_type=(
                facts.invoice_need
                if facts.invoice_need in {"普通发票", "专用发票"}
                else ""
            )
        )
        scores = self.scenario_engine.rank(scenarios, objective)
        evidence = self._evidence(facts)
        return case, graph, bundle, issues, calculations, scenarios, scores, evidence

    def _result(
        self,
        facts: TaxFacts,
        case,
        graph,
        bundle,
        issues,
        calculations,
        scenarios,
        scores,
        evidence,
    ) -> PlanningResult:
        threshold = self._selected(bundle, "vat_threshold")
        threshold_ok = bool(
            threshold and threshold.status == RuleEvaluationStatus.APPLICABLE
        )
        hainan_special = facts.region == "CN-HI" and (
            facts.hainan_special_scene
            or facts.transaction_type == "进口货物"
            or facts.cross_border
        )
        if hainan_special:
            initial = (
                "海南自贸港特殊政策关键事实不足，目前不能确定零关税或"
                "其他优惠是否适用。"
            )
        elif threshold_ok:
            threshold_name = {
                "月": "月10万元",
                "季度": "季度30万元",
                "单次": "每次（日）1000元",
            }.get(facts.amount_period, "起征点")
            initial = (
                f"{threshold_name}起征点条件已由规则引擎初步命中；"
                "仍需确认同期间全部销售额和是否放弃免税。"
            )
        else:
            initial = "当前未命中起征点候选，需按规则结果和适用征收率继续计算。"

        if facts.region == "CN-XJ":
            regional = "新疆事项采用全国规则底座并叠加新疆覆盖层。"
        elif facts.region == "CN-HI" and not hainan_special:
            regional = (
                "该事项属于海南普通境内服务或交易，先适用全国增值税规则，"
                "不因注册在海南而自动适用零关税。"
            )
        elif facts.region == "CN-HI":
            regional = (
                "该事项进入海南特殊政策门禁，享惠主体、HS编码、流向和用途"
                "必须人工复核。"
            )
        else:
            regional = "适用全国税收法规。"

        schemes: list[SchemeOption] = []
        for scenario, calculation in zip(scenarios, calculations):
            summary = calculation.formula or "需要补齐资料后计算。"
            if (
                calculation.inputs.get("levy_rate") == Decimal("0.01")
                or "0.01" in summary
            ):
                summary += "；符合条件时体现1%征收率方向。"
            schemes.append(
                SchemeOption(
                    name=scenario.name,
                    summary=summary,
                    actions=[
                        "确认事实和规则命中",
                        "核对发票、申报和付款时间",
                        "正式执行前保存完整资料链",
                    ],
                    benefits=["税额和现金流可追溯", "评分构成透明"],
                    risks=list(scenario.risks),
                    required_documents=list(scenario.required_documents),
                    estimated_tax=(
                        str(scenario.total_tax)
                        if scenario.total_tax is not None
                        else "无法确定"
                    ),
                )
            )

        risks = list(dict.fromkeys(risk for item in scenarios for risk in item.risks))
        missing = list(
            dict.fromkeys(
                facts.missing_facts()
                + [missing_id for issue in issues for missing_id in issue.missing_fact_ids]
            )
        )
        review = any(item.human_review_required for item in scenarios) or bool(
            bundle.conflicts
        )
        return PlanningResult(
            initial_conclusion=initial,
            applicable_conditions=[
                f"地区：{facts.region}",
                f"纳税人类型：{facts.taxpayer_type}",
                f"增值税身份：{facts.vat_status}",
                f"业务时间：{facts.business_date}",
                f"交易类型：{facts.transaction_type}",
            ],
            evidence=evidence,
            explanation="系统已通过事实图谱、规则引擎和Decimal计算器生成结果。",
            regional_application=regional,
            schemes=schemes,
            risks=risks,
            missing_facts=missing,
            human_review_required=review,
            kb_version=KB_VERSION,
            verified_at=VERIFIED_AT,
            case_id=case.case_id,
            case_state=case.state.value,
            issues=[issue.to_dict() for issue in issues],
            rule_trace=[
                evaluation.to_dict()
                for evaluation in bundle.evaluations + bundle.conflicts
            ],
            calculations=[calculation.to_dict() for calculation in calculations],
            scenario_scores=[
                {
                    "scenario_id": score.scenario_id,
                    "total_score": str(score.total_score),
                    "components": {
                        key: str(value) for key, value in score.components.items()
                    },
                }
                for score in scores
            ],
        )

    def analyze(
        self,
        facts: TaxFacts,
        *,
        case_id: str | None = None,
    ) -> PlanningResult:
        artifacts = self._run(facts, case_id)
        return self._result(facts, *artifacts)

    def _next_version(self, case_id: str, kind: str) -> int:
        try:
            return self.storage.latest_version(case_id, kind) + 1
        except FileNotFoundError:
            return 1

    def _persist(self, artifacts, result: PlanningResult, *, create: bool) -> PlanningResult:
        case, graph, bundle, issues, calculations, scenarios, scores, evidence = artifacts
        if create:
            self.storage.create(case)
            self.storage.write_version(case.case_id, "facts", 1, graph.to_dict())

        payloads = (
            ("issues", {"issues": [item.to_dict() for item in issues]}),
            ("evidence", {"items": [item.to_dict() for item in evidence]}),
            (
                "decisions",
                {
                    "evaluations": [
                        item.to_dict()
                        for item in bundle.evaluations + bundle.conflicts
                    ]
                },
            ),
            (
                "calculations",
                {"calculations": [item.to_dict() for item in calculations]},
            ),
            (
                "scenarios",
                {
                    "scenarios": [item.to_dict() for item in scenarios],
                    "scores": result.scenario_scores,
                },
            ),
        )
        for kind, payload in payloads:
            self.storage.write_version(
                case.case_id,
                kind,
                self._next_version(case.case_id, kind),
                payload,
            )

        saved = self.storage.load(case.case_id)
        saved.issues_version = self.storage.latest_version(case.case_id, "issues")
        saved.calculations_version = self.storage.latest_version(
            case.case_id, "calculations"
        )
        saved.scenarios_version = self.storage.latest_version(case.case_id, "scenarios")
        saved.state = (
            CaseState.HUMAN_REVIEW_PENDING
            if result.human_review_required
            else CaseState.SCENARIOS_READY
        )
        saved.updated_at = datetime.now(timezone.utc)
        self.storage.update_case(saved)
        result.case_state = saved.state.value
        self.storage.append_event(
            case.case_id,
            {
                "event": "analysis_persisted",
                "at": saved.updated_at.isoformat(),
                "facts_version": saved.facts_version,
                "issues_version": saved.issues_version,
                "calculations_version": saved.calculations_version,
                "scenarios_version": saved.scenarios_version,
            },
        )
        return result

    def create_case(self, facts: TaxFacts) -> PlanningResult:
        case_id = (
            f"case-{datetime.now().strftime('%Y%m%d%H%M%S')}-"
            f"{uuid4().hex[:6]}"
        )
        artifacts = self._run(facts, case_id)
        result = self._result(facts, *artifacts)
        return self._persist(artifacts, result, create=True)

    def analyze_case(self, case_id: str) -> PlanningResult:
        graph = self.fact_service.load_graph(case_id)
        facts = self.adapter.from_graph(graph)
        artifacts = self._run(facts, case_id)
        result = self._result(facts, *artifacts)
        return self._persist(artifacts, result, create=False)

    def get_case(self, case_id: str) -> dict[str, Any]:
        case = self.storage.load(case_id)
        payload: dict[str, Any] = {
            "case": case.to_dict(),
            "facts": self.fact_service.load_graph(case_id).to_dict(),
        }
        for kind in ("issues", "evidence", "decisions", "calculations", "scenarios"):
            try:
                payload[kind] = self.storage.load_version(
                    case_id,
                    kind,
                    self.storage.latest_version(case_id, kind),
                )
            except FileNotFoundError:
                payload[kind] = None
        return payload

    def revise_case_fact(
        self,
        case_id: str,
        fact_id: str,
        value: Any,
        actor: str = "user",
    ) -> dict[str, Any]:
        impact = self.fact_service.revise_fact(case_id, fact_id, value, actor)
        rerun = self.workflow.replay_affected(case_id, impact.affected_nodes)
        return {
            "fact_id": fact_id,
            "new_version": impact.new_version,
            "affected_nodes": list(impact.affected_nodes),
            "rerun_nodes": list(rerun),
            "case_state": self.storage.load(case_id).state.value,
        }

    def review_case(
        self,
        case_id: str,
        approved: bool,
        actor: str,
        note: str = "",
    ) -> dict[str, str]:
        state = self.workflow.record_review(case_id, approved, actor, note)
        return {"case_id": case_id, "state": state.value}

    def audit_case(self, case_id: str) -> list[dict[str, Any]]:
        path = self.storage.root / case_id / "timeline.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
