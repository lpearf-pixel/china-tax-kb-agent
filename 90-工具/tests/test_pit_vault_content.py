import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "90-工具"))
from taxkb_core import parse_frontmatter


class PitVaultContentTests(unittest.TestCase):
    def test_required_pit_sources_and_provisions_exist(self):
        cases = [
            ("01-法规原文/国家/个人所得税/中华人民共和国个人所得税法.md", "document_id", "DOC-CN-PIT-LAW-2018"),
            ("01-法规原文/国家/个人所得税/中华人民共和国个人所得税法实施条例.md", "document_id", "DOC-CN-PIT-REG-2018"),
            ("01-法规原文/国家/个人所得税/个体工商户个人所得税计税办法.md", "document_id", "DOC-CN-PIT-ORDER-35"),
            ("01-法规原文/国家/个人所得税/个人所得税扣缴申报管理办法_2018年第61号.md", "document_id", "DOC-CN-PIT-STA-2018-61"),
            ("01-法规原文/国家/个人所得税/个体工商户减半优惠征管_2023年第12号.md", "expiry_date", "2027-12-31"),
            ("02-条款结构/个人所得税/个人所得税法_居民身份与所得分类.md", "provision_id", "PROV-PIT-LAW-001-003"),
            ("02-条款结构/个人所得税/个人所得税法_经营所得税率表.md", "provision_id", "PROV-PIT-BUSINESS-RATE-TABLE"),
            ("02-条款结构/个人所得税/2023年第12号_个体工商户减半.md", "provision_valid_to", "2027-12-31"),
            ("02-条款结构/个人所得税/2018年第61号_劳务报酬预扣.md", "provision_id", "PROV-PIT-LABOR-WITHHOLDING"),
        ]
        for relative, key, value in cases:
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(path.exists(), relative)
                meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
                self.assertEqual(str(meta.get(key) or ""), value)


if __name__ == "__main__":
    unittest.main()
