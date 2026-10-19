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

    def test_fixed_tags(self):
        self.assertEqual(gen.parse_tags("#을지로 맛집, #닉네임 을지로"), ["#을지로", "#맛집", "#닉네임"])
        self.assertIn("꼭 그대로 넣는다", gen.build_prompt(BLOG, "m", "", [], [], "", ["#을지로"]))
        self.assertNotIn("꼭 그대로", gen.build_prompt(CAFE, "m", "", [], [], "", ["#을지로"]))   # 태그 안 쓰는 곳
        self.assertEqual(gen.ensure_tags("본문\n\n#카페 #라떼", ["#라떼", "#을지로"]), "본문\n\n#카페 #라떼 #을지로")
        self.assertEqual(gen.ensure_tags("본문만", ["#을지로"]), "본문만\n\n#을지로")
        tik = gen.ensure_tags("[캡션]\n한 줄 #카페\n\n[자막 대본]\n(사진 1) 첫 줄", ["#을지로"])
        self.assertEqual(tik, "[캡션]\n한 줄 #카페 #을지로\n\n[자막 대본]\n(사진 1) 첫 줄")
        self.assertEqual(gen.ensure_tags("본문 #을지로", ["#을지로"]), "본문 #을지로")

    def test_campaign(self):
        c = {"kind": "experience", "brand": "OO식당", "provided": "2인 식사권", "keywords": [{"word": "을지로 김치찌개", "min": 3}, {"word": "", "min": 1}],
             "tags": "#OO식당 체험단", "links": ["https://map.naver.com/x"], "notes": "주차 정보 꼭"}
        blog = dict(BLOG, title=True)
        s = gen.build_prompt(blog, "m", "", [], [], "", campaign=c)
        for w in ("을지로 김치찌개", "3번 이상", "#OO식당", "#체험단", "https://map.naver.com/x", "주차 정보 꼭", "2인 식사권", "제목 다음"):
            self.assertIn(w, s)
        line = gen.disclosure(c)
        self.assertEqual(line, "이 글은 OO식당으로부터 2인 식사권을 제공받아 솔직하게 작성했습니다.")
        self.assertEqual(gen.josa("카페", ("으로", "로")) + gen.josa("서울", ("으로", "로")) + gen.josa("커피", ("을", "를")) + gen.josa("ABC", ("을", "를")), "로로를를")
        out = gen.apply_campaign("제목줄\n\n본문\n\n#맛집", c, blog)
        self.assertEqual(out.split("\n")[:3], ["제목줄", "", line])
        self.assertTrue(out.endswith("#맛집 #OO식당 #체험단"))
        self.assertEqual(gen.ensure_disclosure("제목\n" + line + "\n본문", line, True), "제목\n" + line + "\n본문")   # 이미 있으면 그대로
        self.assertTrue(gen.apply_campaign("본문", c, CAFE).startswith(line))     # 제목 없는 플랫폼은 맨 앞(CAFE 시험값엔 title 없음)
        gb = {"kind": "groupbuy", "brand": "OO", "start": "2026-10-20", "deadline": "2026-10-25", "price": "39,000원", "sale_price": "29,000원"}
        s = gen.build_prompt(BLOG, "m", "", [], [], "", campaign=gb)
        self.assertIn("2026년 10월 25일", s)
        self.assertIn("29,000원", s)
        self.assertIn("수수료", gen.disclosure(gb))
        self.assertEqual(gen.build_prompt(BLOG, "m", "", [], [], "").count("조건 (꼭"), 0)

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
