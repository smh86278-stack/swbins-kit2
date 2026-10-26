# -*- coding: utf-8 -*-
import io
import os
import re
import sys
import unittest
import zipfile
from xml.dom import minidom

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import taxbook  # noqa: E402
import xlsx     # noqa: E402

ROWS = [
    {"date": "2026-03-02", "kind": "원고료", "platform": "naver_blog", "what": "OO식당 체험단", "amount": 100000, "value": 0, "tax": 3300},
    {"date": "2026-03-20", "kind": "협찬 물품", "platform": "instagram", "what": "OO샴푸 & <협찬>", "amount": 0, "value": 39000},
    {"date": "2026-11-01", "kind": "원고료", "platform": "naver_blog", "what": "OO식당 체험단", "amount": "50,000", "value": 20000},
    {"date": "2025-12-31", "kind": "원고료", "what": "작년 것", "amount": 999999},
]


class XlsxTest(unittest.TestCase):
    def test_col(self):
        self.assertEqual([xlsx.col(i) for i in (0, 25, 26, 27, 701, 702)], ["A", "Z", "AA", "AB", "ZZ", "AAA"])

    def test_book(self):
        data = taxbook.build(ROWS, 2026, {"naver_blog": "네이버 블로그"})
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        self.assertIn("xl/workbook.xml", names)
        for n in names:                                   # 모든 xml 이 올바른지
            minidom.parseString(z.read(n))
        wb = z.read("xl/workbook.xml").decode()
        self.assertEqual(re.findall(r'name="([^"]+)"', wb), ["요약", "내역", "월별", "업체별"])
        detail = z.read("xl/worksheets/sheet2.xml").decode()
        self.assertIn("네이버 블로그", detail)
        self.assertIn("OO샴푸 &amp; &lt;협찬&gt;", detail)
        self.assertNotIn("작년 것", detail)
        self.assertIn("<f>SUM(E2:E4)</f><v>150000</v>", detail)           # 받은 돈 합계(쉼표 든 값도)
        self.assertIn("<f>SUM(H2:H4)</f><v>3300</v>", detail)
        summary = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("<v>209000</v>", summary)                            # 총수입 150000 + 59000
        month = z.read("xl/worksheets/sheet3.xml").decode()
        self.assertIn("<v>139000</v>", month)                              # 3월 100000 + 39000
        payer = z.read("xl/worksheets/sheet4.xml").decode()
        self.assertLess(payer.index("OO식당 체험단"), payer.index("OO샴푸"))  # 합계 큰 업체가 위

    def test_empty_year(self):
        z = zipfile.ZipFile(io.BytesIO(taxbook.build([], 2030)))
        minidom.parseString(z.read("xl/worksheets/sheet2.xml"))


if __name__ == "__main__":
    unittest.main()
