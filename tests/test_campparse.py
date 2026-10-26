# -*- coding: utf-8 -*-
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cal        # noqa: E402
import campparse  # noqa: E402

NOTICE = """[OO식당] 10월 신메뉴 방문 체험단 모집
제공: 2인 식사권(4만원 상당)
방문: 10/28(화) 18:30 예약 · 포스팅 마감 11/4
필수 키워드: 을지로 맛집 3회 이상, 은주정 2회
필수 태그 #을지로맛집 #은주정
지도 첨부 필수, 사진 15장 이상, 주차 정보 꼭 넣어 주세요
업체 링크 https://naver.me/xAbC12. 문의는 카톡"""


class CampParseTest(unittest.TestCase):
    def test_prompt(self):
        p = campparse.prompt(NOTICE, today=date(2026, 10, 26))
        self.assertIn("2026-10-26", p)
        self.assertIn("OO식당", p)
        self.assertIn('"need_map"', p)

    def test_scan(self):
        links, tags = campparse.scan(NOTICE)
        self.assertEqual(links, ["https://naver.me/xAbC12"])
        self.assertEqual(tags, ["을지로맛집", "은주정"])

    def test_parse_and_normalize(self):
        reply = """좋아요, 결과예요:
```json
{"kind": "experience", "brand": "OO식당", "title": "10월 신메뉴 체험단", "visit": "2026-10-28 18:30", "deadline": "2026-11-04",
 "start": "2026-10-01", "provided": "2인 식사권", "keywords": [{"word": "을지로 맛집", "min": 3}, {"word": "은주정", "min": "2"}, "주차"],
 "tags": "#을지로맛집", "links": ["javascript:alert(1)"], "min_photos": "15", "need_map": true,
 "notes": ["주차 정보 꼭"], "platforms": ["naver_blog", "facebook"]}
```"""
        d = campparse.normalize(campparse.parse_reply(reply), NOTICE)
        self.assertEqual(d["visit"], "2026-10-28T18:30")
        self.assertEqual(d["deadline"], "2026-11-04")
        self.assertEqual(d["start"], "")                                  # 공구가 아니면 시작일 버림
        self.assertEqual(d["keywords"], [{"word": "을지로 맛집", "min": 3}, {"word": "은주정", "min": 2}, {"word": "주차", "min": 1}])
        self.assertEqual(d["tags"], "#을지로맛집 #은주정")                   # AI 가 놓친 태그는 안내문에서
        self.assertEqual(d["links"], ["https://naver.me/xAbC12"])          # javascript: 는 버리고 안내문 링크
        self.assertEqual(d["min_photos"], 15)
        self.assertTrue(d["need_map"])
        self.assertEqual(d["notes"], "주차 정보 꼭")
        self.assertEqual(d["platforms"], ["naver_blog"])

    def test_bad_reply(self):
        with self.assertRaises(ValueError):
            campparse.parse_reply("모르겠어요")
        d = campparse.normalize({"kind": "이상한", "deadline": "11월 4일", "min_photos": "많이"})
        self.assertEqual((d["kind"], d["deadline"], d["min_photos"]), ("experience", "", 0))

    def test_midnight_visit_is_all_day(self):
        ev = cal.events([{"id": "a", "brand": "B", "visit": "2026-10-28T00:00"}])
        self.assertEqual(ev[0]["time"], "")


if __name__ == "__main__":
    unittest.main()
