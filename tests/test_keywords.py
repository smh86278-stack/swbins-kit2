# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import keywords  # noqa: E402

SEEN = {}


class Fake(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN["path"], SEEN["headers"] = self.path, self.headers      # 대소문자 안 가리는 Message
        if self.headers.get("X-API-KEY") == "bad":
            self.send_response(401); self.end_headers(); return          # noqa: E702
        body = json.dumps({"keywordList": [
            {"relKeyword": "을지로맛집", "monthlyPcQcCnt": 5400, "monthlyMobileQcCnt": 32100, "compIdx": "높음"},
            {"relKeyword": "을지로김치찌개", "monthlyPcQcCnt": "< 10", "monthlyMobileQcCnt": 880, "compIdx": "낮음"},
        ]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()  # noqa: E702
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class KeywordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.api = "http://127.0.0.1:%d" % cls.srv.server_port

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_hints(self):
        self.assertEqual(keywords.hints_of("을지로 맛집, 김치찌개\n김치찌개, a,b,c,d"), ["을지로맛집", "김치찌개", "a", "b", "c"])

    def test_related(self):
        rows = keywords.related(("123", "lic", "sec"), ["을지로맛집"], api=self.api)
        self.assertEqual([r["keyword"] for r in rows], ["을지로맛집", "을지로김치찌개"])
        self.assertEqual(rows[1]["total"], 885)                          # '< 10' 은 5 로 어림
        h = SEEN["headers"]
        self.assertEqual(h["X-Customer"], "123")
        self.assertEqual(h["X-API-KEY"], "lic")
        want = base64.b64encode(hmac.new(b"sec", ("%s.GET./keywordstool" % h["X-Timestamp"]).encode(), hashlib.sha256).digest()).decode()
        self.assertEqual(h["X-Signature"], want)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(SEEN["path"]).query)
        self.assertEqual(q["hintKeywords"], ["을지로맛집"])
        self.assertEqual(q["showDetail"], ["1"])

    def test_bad_key(self):
        with self.assertRaisesRegex(ValueError, "키가 맞지 않아요"):
            keywords.related(("123", "bad", "sec"), ["a"], api=self.api)
        with self.assertRaises(ValueError):
            keywords.related(("123", "lic", "sec"), [], api=self.api)

    def test_keys_roundtrip(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(keywords.load_keys(d))
        with self.assertRaises(ValueError):
            keywords.save_keys(d, "abc", "lic", "sec")                    # 고객 ID 는 숫자
        keywords.save_keys(d, " 123 ", "lic", "비밀키-sec")
        with open(keywords.keys_path(d), encoding="utf-8") as f:
            raw = f.read()
        if sys.platform == "win32":                                       # 윈도우는 비밀 키가 그대로 안 남는다(DPAPI)
            self.assertNotIn("비밀키-sec", raw)
            self.assertIn("dpapi:", raw)
        self.assertEqual(keywords.load_keys(d), ("123", "lic", "비밀키-sec"))
        with open(keywords.keys_path(d), "w", encoding="utf-8") as f:     # 다른 PC 에서 잠근 것처럼 — 못 풀면 None
            json.dump({"customer": "1", "license": "l", "secret": "dpapi:" + base64.b64encode(b"garbage").decode()}, f)
        self.assertIsNone(keywords.load_keys(d))
        keywords.delete_keys(d)
        self.assertFalse(os.path.exists(keywords.keys_path(d)))


if __name__ == "__main__":
    unittest.main()
