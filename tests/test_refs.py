# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen      # noqa: E402
import refs     # noqa: E402


class RefsTest(unittest.TestCase):
    def test_parse_urls(self):
        t = "참고: https://blog.naver.com/a/1, https://blog.naver.com/a/1\nhttps://x.com/2) https://y.com/3 https://z.com/4"
        self.assertEqual(refs.parse_urls(t), ["https://blog.naver.com/a/1", "https://x.com/2", "https://y.com/3"])

    def test_naver_blog(self):
        self.assertEqual(refs.naver_blog("https://blog.naver.com/abc_1/223456?x=1"), "https://m.blog.naver.com/abc_1/223456")
        self.assertEqual(refs.naver_blog("https://blog.naver.com/PostView.naver?blogId=abc&logNo=99"), "https://m.blog.naver.com/abc/99")
        self.assertIsNone(refs.naver_blog("https://blog.naver.com/abc"))
        self.assertIsNone(refs.naver_blog("https://example.com/abc/1"))

    def test_page_text(self):
        page = '<html><script>x=1</script><div>메뉴</div><div class="se-main-container"><p>첫 줄&amp;</p><p>둘째<br>셋째</p></div>'
        self.assertEqual(refs.page_text(page), "첫 줄&\n둘째\n셋째")

    def test_load_cache_and_error(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "refs.txt"), "w", encoding="utf-8") as f:
            f.write("https://a.com/1\nftp://no\n")
        page = "<title>제목</title><p>" + "본문 " * 50 + "</p>"
        with mock.patch.object(refs, "fetch", return_value=("https://a.com/1", page)) as m:
            r = refs.load(d)
            refs.load(d)                               # 두 번째는 캐시에서
        self.assertEqual(m.call_count, 1)
        self.assertEqual(r[0]["title"], "제목")
        self.assertIn("본문", r[0]["text"])
        with mock.patch.object(refs, "fetch", side_effect=OSError("막힘")):
            self.assertIn("막힘", refs.read_one("https://b.com/")["error"])

    def test_prompt_block(self):
        self.assertEqual(gen.refs_block([{"text": "", "error": "x"}]), "")
        s = gen.build_prompt({"name": "블로그", "prompt": "naver_blog.md"}, "m", "", [], [], "",
                             refs=[{"url": "u", "title": "남의 글", "text": "남의 본문", "error": ""}])
        self.assertIn("참고 글 (구성만 참고)", s)
        self.assertIn("남의 본문", s)
        self.assertLess(s.index("참고 글"), s.index("## 재료"))


if __name__ == "__main__":
    unittest.main()
