from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apps.tax_decision_core.rule_loader import RuleLoader
from apps.tax_decision_core.rule_schema import RuleDefinition

VALID_RULE = {
    "rule_id": "VAT-SMALL-THRESHOLD-QUARTER-2026", "version": 1, "status": "effective",
    "valid_from": "2026-01-01", "valid_to": "2027-12-31", "jurisdiction": "CN",
    "tax_type": "增值税", "priority": 100, "exclusive_group": "vat_threshold",
    "when": {"all": [
        {"fact": "taxpayer.vat_status", "operator": "equals", "value": "小规模纳税人"},
        {"fact": "transaction.amount_period", "operator": "equals", "value": "季度"},
        {"fact": "transaction.total_sales_same_period", "operator": "less_or_equal", "value": 300000}
    ]},
    "then": {"outcome": "threshold_exempt_candidate", "value": True, "confidence": "deterministic"},
    "requires": ["transaction.total_sales_same_period", "invoice.waive_exemption"],
    "legal_basis": [{"document_id": "DOC-CN-VAT-MOF-STA-2026-10", "provision_id": "PROV-VAT-ANN10-THRESHOLD"}]
}


class RuleSchemaTests(unittest.TestCase):
    def test_valid_rule_parses_dates_and_round_trips(self):
        rule = RuleDefinition.from_mapping(VALID_RULE)
        self.assertEqual(rule.rule_id, "VAT-SMALL-THRESHOLD-QUARTER-2026")
        self.assertEqual(rule.valid_from, date(2026, 1, 1))
        self.assertEqual(rule.valid_to, date(2027, 12, 31))
        self.assertEqual(rule.to_mapping()["when"], VALID_RULE["when"])

    def test_missing_required_field_and_invalid_operator_are_rejected(self):
        broken = dict(VALID_RULE); broken.pop("legal_basis")
        with self.assertRaisesRegex(ValueError, "legal_basis"): RuleDefinition.from_mapping(broken)
        broken = json.loads(json.dumps(VALID_RULE, ensure_ascii=False)); broken["when"]["all"][0]["operator"] = "run_python"
        with self.assertRaisesRegex(ValueError, "operator"): RuleDefinition.from_mapping(broken)

    def test_unsafe_dsl_keys_are_rejected_at_any_depth(self):
        for key in ("python", "eval", "exec", "import", "expression", "callable"):
            broken = json.loads(json.dumps(VALID_RULE, ensure_ascii=False)); broken["when"]["all"].append({key: "os.system('whoami')"})
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, "unsafe"): RuleDefinition.from_mapping(broken)


class RuleLoaderTests(unittest.TestCase):
    def write_rule(self, root: Path, rel: str, payload: dict) -> None:
        path = root / rel; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_vault(self, root: Path) -> None:
        law = root / "01-法规原文" / "国家" / "规则.md"; provision = root / "02-条款结构" / "增值税" / "条款.md"
        law.parent.mkdir(parents=True, exist_ok=True); provision.parent.mkdir(parents=True, exist_ok=True)
        law.write_text("---\ndocument_id: DOC-CN-VAT-MOF-STA-2026-10\n---\n# 法规\n", encoding="utf-8")
        provision.write_text("---\nprovision_id: PROV-VAT-ANN10-THRESHOLD\n---\n# 条款\n", encoding="utf-8")

    def test_load_keeps_national_and_target_region_and_filters_dates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); rules = root / "rules"; vault = root / "vault"; self.write_vault(vault)
            self.write_rule(rules, "vat/national/quarter.yaml", VALID_RULE)
            hainan = json.loads(json.dumps(VALID_RULE, ensure_ascii=False)); hainan.update({"rule_id": "HI-GATE", "jurisdiction": "CN-HI", "priority": 200})
            self.write_rule(rules, "vat/hainan/gate.yaml", hainan)
            xinjiang = json.loads(json.dumps(VALID_RULE, ensure_ascii=False)); xinjiang.update({"rule_id": "XJ-RULE", "jurisdiction": "CN-XJ"})
            self.write_rule(rules, "vat/xinjiang/rule.yaml", xinjiang)
            expired = json.loads(json.dumps(VALID_RULE, ensure_ascii=False)); expired.update({"rule_id": "OLD", "valid_from": "2023-01-01", "valid_to": "2025-12-31"})
            self.write_rule(rules, "vat/national/old.yaml", expired)
            loaded = RuleLoader(rules, vault=vault).load(date(2026, 7, 18), "CN-HI", "增值税")
            self.assertEqual([rule.rule_id for rule in loaded], ["HI-GATE", "VAT-SMALL-THRESHOLD-QUARTER-2026"])

    def test_missing_legal_basis_in_vault_stops_loading(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); rules = root / "rules"; vault = root / "vault"; vault.mkdir()
            self.write_rule(rules, "vat/national/quarter.yaml", VALID_RULE)
            with self.assertRaisesRegex(ValueError, "legal basis"):
                RuleLoader(rules, vault=vault).load(date(2026, 7, 18), "CN", "增值税")


if __name__ == "__main__": unittest.main()
