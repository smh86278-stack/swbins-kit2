# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gen  # noqa: E402

BLOG = {"id": "naver_blog", "name": "네이버 블로그", "prompt": "naver_blog.md", "length": "1500~2500자", "hashtags": 5}
CAFE = {"id": "naver_cafe", "name": "네이버 카페", "prompt": "naver_cafe.md", "length": "600~1200자", "hashtags": 0}


class PromptTest(unittest.TestCase):
    def test_platforms_have_prompt_files(self):
        ps = gen.load_platforms()
        self.assertGreaterEqual(len(ps), 4)
        for p in ps:
            self.assertTrue(gen.read_prompt(p["prompt"]), p["id"])

    def test_build_prompt_has_rules_material_and_voice(self):
        s = gen.build_prompt(BLOG, "을지로 김치찌개 7천원, 웨이팅 20분", "", ["a.jpg", "b.png"], ["예전 글 하나"], "반말, 이모지 적게")
        self.assertIn("인생 맛집", s)               # 뻔한 표현 금지 목록
        self.assertIn("[확인:", s)                  # 지어내지 말 것
        self.assertIn("./photos/a.jpg", s)
        self.assertIn("./photos/b.png", s)
        self.assertIn("예전 글 하나", s)
        self.assertIn("반말, 이모지 적게", s)
        self.assertIn("7천원", s)
        self.assertIn("5개 안팎", s)

    def test_no_hashtags_and_no_voice(self):
        s = gen.build_prompt(CAFE, "메모", "", [], [], "")
        self.assertIn("쓰지 않음", s)
        self.assertIn("사진 없음", s)
        self.assertNotIn("글쓴이 말투", s)

    def test_photo_limit(self):
        names = ["%02d.jpg" % i for i in range(13)]
        s = gen.build_prompt(BLOG, "m", "", names, [], "")
        self.assertIn("./photos/09.jpg", s)
        self.assertNotIn("./photos/10.jpg", s)
        self.assertIn("3장 더", s)

    def test_refine_prompt(self):
        s = gen.build_refine_prompt(BLOG, "더 짧게", "지금 글 내용")
        self.assertIn("지금 글 내용", s)
        self.assertIn("더 짧게", s)
        self.assertNotIn("인생 맛집", s)            # 세션 이어받기면 규칙을 다시 붙이지 않는다
        s2 = gen.build_refine_prompt(BLOG, "더 짧게", "x", standalone=True, voice_texts=["내 글"], voice_note="")
        self.assertIn("인생 맛집", s2)
        self.assertIn("내 글", s2)


class PhotoTest(unittest.TestCase):
    def test_shrink_turn_and_date(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as root:
            p = os.path.join(root, "a.jpg")
            im = Image.new("RGB", (4000, 3000), (200, 100, 100))
            ex = Image.Exif()
            ex[274] = 6                                          # 90도 돌아간 사진
            ex.get_ifd(0x8769)[36867] = "2026:10:18 12:30:00"
            im.save(p, exif=ex.tobytes())
            self.assertEqual(gen.process_photo(p), "2026-10-18")
            with Image.open(p) as out:
                self.assertEqual(out.size, (1200, 1600))         # 바로 세우고 긴 변 1600
                self.assertNotIn(274, out.getexif())
            small = os.path.join(root, "b.png")
            Image.new("RGB", (300, 200)).save(small)
            before = os.path.getmtime(small)
            self.assertEqual(gen.process_photo(small), "")
            self.assertEqual(os.path.getmtime(small), before)    # 작은 사진은 손대지 않는다
            bad = os.path.join(root, "c.jpg")
            with open(bad, "wb") as f:
                f.write(b"not an image")
            self.assertEqual(gen.process_photo(bad), "")

    def test_date_text_and_templates(self):
        self.assertEqual(gen.date_text("2026-10-18"), "2026년 10월 18일 (일)")
        self.assertEqual(gen.date_text("x"), "")
        ts = gen.load_templates()
        self.assertGreaterEqual(len(ts), 4)
        self.assertTrue(all(t["memo"] and t["name"] for t in ts))


class ParseTest(unittest.TestCase):
    def test_single_json(self):
        r = gen.parse_result(json.dumps({"type": "result", "subtype": "success", "result": "본문", "session_id": "abc"}))
        self.assertEqual(r, {"text": "본문", "session_id": "abc", "error": ""})

    def test_last_json_line_and_code_fence(self):
        out = "잡소리\n" + json.dumps({"subtype": "success", "result": "```\n본문\n```", "session_id": "s"})
        self.assertEqual(gen.parse_result(out)["text"], "본문")

    def test_error_and_garbage(self):
        r = gen.parse_result(json.dumps({"is_error": True, "subtype": "success", "result": "로그인 필요", "session_id": ""}))
        self.assertEqual(r["text"], "")
        self.assertIn("로그인", r["error"])
        self.assertTrue(gen.parse_result("not json")["error"])


class PathTest(unittest.TestCase):
    def test_new_post_dir(self):
        with tempfile.TemporaryDirectory() as root:
            now = datetime(2026, 10, 19)
            a = gen.new_post_dir(root, "을지로 김치찌개!! 7천원 웨이팅", now)
            self.assertEqual(os.path.basename(a), "20261019-을지로-김치찌개-7천원")
            self.assertTrue(os.path.isdir(os.path.join(a, "photos")))
            b = gen.new_post_dir(root, "을지로 김치찌개!! 7천원 웨이팅", now)
            self.assertTrue(b.endswith("-2"))
            self.assertEqual(os.path.basename(gen.new_post_dir(root, "", now)), "20261019-글")
            self.assertEqual(gen.safe_slug("동네 카페 딸기라떼 6500원"), "동네-카페-딸기라떼")

    def test_inside(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertTrue(gen.inside(root, os.path.join(root, "a", "b")))
            self.assertFalse(gen.inside(root, root))
            self.assertFalse(gen.inside(root, os.path.join(root, "..", "x")))

    def test_voice_and_photos(self):
        with tempfile.TemporaryDirectory() as root:
            for i in range(7):
                with open(os.path.join(root, "%d.txt" % i), "w", encoding="utf-8") as f:
                    f.write("가" * 2000)
                os.utime(os.path.join(root, "%d.txt" % i), (i, i))
            v = gen.load_voice(root)
            self.assertEqual(len(v), 5)
            self.assertEqual(len(v[0]), 1500)
            os.makedirs(os.path.join(root, "photos"))
            for n in ("b.JPG", "a.png", "memo.txt"):
                open(os.path.join(root, "photos", n), "w").close()
            self.assertEqual(gen.photo_names(root), ["a.png", "b.JPG"])
            open(os.path.join(root, "photos", "c.jpg"), "w").close()
            gen.save_photo_order(root, ["b.JPG", "없는것.jpg", "b.JPG", "a.png"])
            self.assertEqual(gen.photo_names(root), ["b.JPG", "a.png", "c.jpg"])     # 새로 넣은 건 뒤에


if __name__ == "__main__":
    unittest.main()
