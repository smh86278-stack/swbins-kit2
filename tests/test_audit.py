# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audit    # noqa: E402

PAGE = ('<script>var gsTagName = "을지로맛집,김치찌개";</script><meta property="og:title" content="을지로 김치찌개 후기">'
        '<div class="se-main-container"><p>이 글은 OO식당으로부터 식사를 제공받아 작성했습니다.</p>'
        '<img src="a.jpg?type=w80" data-lazy-src="a.jpg?type=w800" class="se-image-resource" />'
        '<img src="b.jpg?type=w80" class="se-image-resource" />'
        '<div class="se-component se-placesMap">지도</div>'
        '<p>' + "을지로 김치찌개 정말 맛있어요. " * 3 + '</p><a href="https://naver.me/abc">링크</a></div>')
CAMP = {"brand": "OO식당", "keywords": [{"word": "을지로 김치찌개", "min": 3}, {"word": "주차", "min": 1}],
        "tags": "#을지로맛집 #방산시장", "links": ["https://naver.me/abc"], "min_photos": 3, "need_map": True}


class AuditTest(unittest.TestCase):
    def facts(self):
        with mock.patch.object(audit.refs, "fetch", return_value=("https://m.blog.naver.com/a/1", PAGE)):
            return audit.facts("https://blog.naver.com/a/1")

    def test_facts(self):
        f = self.facts()
        self.assertEqual(f["error"], "")
        self.assertEqual(f["photos"], 2)
        self.assertTrue(f["map"])
        self.assertEqual(f["tags"], ["을지로맛집", "김치찌개"])

    def test_check(self):
        rows = {r["item"]: r for r in audit.check(self.facts(), CAMP)}
        self.assertTrue(rows["키워드 을지로 김치찌개"]["ok"])           # 본문 3번 + 제목 1번
        self.assertFalse(rows["키워드 주차"]["ok"])
        self.assertTrue(rows["태그 #을지로맛집"]["ok"])
        self.assertFalse(rows["태그 #방산시장"]["ok"])
        self.assertTrue(rows["링크"]["ok"])
        self.assertFalse(rows["사진"]["ok"])                             # 2장 / 3장 이상
        self.assertTrue(rows["지도"]["ok"])
        self.assertTrue(rows["협찬 표기"]["ok"])

    def test_disclosure_only_at_end(self):
        f = dict(self.facts(), text="본문 " * 400 + "협찬")
        r = [x for x in audit.check(f, {"brand": "OO"}) if x["item"] == "협찬 표기"][0]
        self.assertFalse(r["ok"])

    def test_error_and_report(self):
        with mock.patch.object(audit.refs, "fetch", side_effect=OSError("막힘")):
            f = audit.facts("https://blog.naver.com/a/1")
        self.assertEqual(audit.check(f, CAMP)[0]["ok"], False)
        f = self.facts()
        rep = audit.report(CAMP, f, audit.check(f, CAMP))
        self.assertIn("OO식당", rep)
        self.assertIn("✗ 키워드 주차", rep)


if __name__ == "__main__":
    unittest.main()
