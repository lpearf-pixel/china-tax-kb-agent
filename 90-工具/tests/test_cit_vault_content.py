import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "90-工具"))

from taxkb_core import parse_frontmatter


class CitVaultContentTests(unittest.TestCase):
    def check_note(self, relative, key, value):
        path = ROOT / relative
        self.assertTrue(path.exists(), relative)
        metadata, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(str(metadata.get(key) or ""), value)

    def test_required_cit_sources_and_provisions_exist(self):
        cases = [
            ("01-法规原文/国家/企业所得税/中华人民共和国企业所得税法.md", "document_id", "DOC-CN-CIT-LAW-2018"),
            ("01-法规原文/国家/企业所得税/中华人民共和国企业所得税法实施条例_2024修订.md", "document_id", "DOC-CN-CIT-REG-2024"),
            ("01-法规原文/国家/企业所得税/小型微利企业优惠延续_2023年第12号.md", "expiry_date", "2027-12-31"),
            ("01-法规原文/国家/企业所得税/小型微利企业优惠征管_2023年第6号.md", "document_id", "DOC-CN-CIT-STA-2023-6"),
            ("02-条款结构/企业所得税/企业所得税法_第一至四条_纳税人与税率.md", "provision_id", "PROV-CIT-LAW-001-004"),
            ("02-条款结构/企业所得税/企业所得税法_第五条_应纳税所得额.md", "provision_id", "PROV-CIT-LAW-005"),
            ("02-条款结构/企业所得税/2023年第12号_小型微利企业优惠.md", "provision_valid_to", "2027-12-31"),
            ("02-条款结构/企业所得税/2023年第6号_小型微利企业征管.md", "provision_id", "PROV-CIT-SME-ADMIN-2023-6"),
        ]
        for relative, key, value in cases:
            with self.subTest(path=relative):
                self.check_note(relative, key, value)


if __name__ == "__main__":
    unittest.main()
