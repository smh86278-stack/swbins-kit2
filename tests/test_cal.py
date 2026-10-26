# -*- coding: utf-8 -*-
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cal      # noqa: E402

CAMPS = [
    {"id": "a1", "kind": "experience", "brand": "OO식당", "title": "신메뉴, 체험단", "visit": "2026-10-28T18:30", "deadline": "2026-11-04"},
    {"id": "b2", "kind": "groupbuy", "brand": "OO", "start": "2026-10-30", "deadline": "2026-11-02"},
    {"id": "c3", "kind": "sponsor", "brand": "끝난곳", "deadline": "2026-10-27", "status": "done"},
    {"id": "d4", "kind": "sponsor", "brand": "시작일무시", "start": "2026-10-29"},
]


class CalTest(unittest.TestCase):
    def test_events(self):
        ev = cal.events(CAMPS)
        self.assertEqual([(e["camp"], e["kind"]) for e in ev],
                         [("a1", "visit"), ("b2", "start"), ("b2", "deadline"), ("a1", "deadline")])
        self.assertEqual(ev[0]["time"], "18:30")
        self.assertIn("방문·체험 — OO식당 · 신메뉴, 체험단", ev[0]["title"])

    def test_ics(self):
        s = cal.ics(cal.events(CAMPS), now=datetime(2026, 10, 26, 9, 0))
        self.assertTrue(s.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertEqual(s.count("BEGIN:VEVENT"), 4)
        self.assertIn("DTSTART:20261028T183000", s)
        self.assertIn("DTSTART;VALUE=DATE:20261104", s)
        self.assertIn("DTEND;VALUE=DATE:20261105", s)
        self.assertIn("UID:a1-visit@postkit", s)
        self.assertIn("신메뉴\\, 체험단", s)                       # 쉼표는 이스케이프
        self.assertIn("TRIGGER:-PT2H", s)
        self.assertIn("TRIGGER:PT9H", s)
        self.assertNotIn("\n\n", s.replace("\r\n", "\n"))
        for line in s.split("\r\n"):                                     # 한 줄 75바이트 이하(접힌 줄 포함)
            self.assertLessEqual(len(line.encode("utf-8")), 75)

    def test_fold_long_korean(self):
        ev = cal.events([{"id": "x", "brand": "아주아주긴가게이름" * 6, "deadline": "2026-11-04"}])
        s = cal.ics(ev)
        unfolded = s.replace("\r\n ", "")
        self.assertIn("SUMMARY:글 마감 — " + "아주아주긴가게이름" * 6, unfolded)
        self.assertTrue(all(len(l.encode("utf-8")) <= 75 for l in s.split("\r\n")))


if __name__ == "__main__":
    unittest.main()
