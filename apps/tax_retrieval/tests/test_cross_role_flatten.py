import unittest

from apps.tax_retrieval.models import EvidenceBundle, EvidenceRecord


class CrossRoleFlattenTests(unittest.TestCase):
    def test_same_provision_is_preserved_across_support_and_exclusion_roles(self):
        bundle = EvidenceBundle(
            support=[EvidenceRecord(path="x.md", title="支持", role="support", provision_id="P1")],
            exclusion=[EvidenceRecord(path="x.md", title="排除", role="exclusion", provision_id="P1")],
        )
        rows = bundle.flatten_current()
        self.assertEqual([row.role for row in rows], ["support", "exclusion"])


if __name__ == "__main__":
    unittest.main()
