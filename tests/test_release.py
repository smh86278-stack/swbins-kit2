# -*- coding: utf-8 -*-
"""release.py — GitHub 에 닿지 않는 부분만(인자 검사·저장소 이름·커밋 안 한 변경이면 멈춤)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import release  # noqa: E402


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.real = release.git
        self.addCleanup(setattr, release, "git", self.real)

    def test_bad_tag_or_missing_notes(self):
        for argv in ([], ["0.3.1", "n.md"], ["v0.3", "n.md"], ["v0.3.1"]):
            with self.assertRaises(SystemExit):
                release.main(argv)

    def test_repo_name(self):
        for url in ("https://github.com/me/swbins-kit2.git", "https://me@github.com/me/swbins-kit2", "git@github.com:me/swbins-kit2.git"):
            release.git = lambda *a, u=url, **k: u + "\n"
            self.assertEqual(release.repo_name(), "me/swbins-kit2")
        release.git = lambda *a, **k: "https://example.com/x.git\n"
        with self.assertRaises(SystemExit):
            release.repo_name()

    def test_stops_on_uncommitted_change(self):
        notes = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_notes.md")
        with open(notes, "w", encoding="utf-8") as f:
            f.write("본문")
        self.addCleanup(os.remove, notes)
        calls = []
        release.git = lambda *a, **k: (calls.append(a), " M app.py\n")[1] if a[0] == "status" else ""
        with self.assertRaises(SystemExit) as cm:
            release.main(["v9.9.9", notes])
        self.assertIn("커밋", str(cm.exception))
        self.assertNotIn("tag", [c[0] for c in calls])            # 태그·push 까지 안 갔다


if __name__ == "__main__":
    unittest.main()
