# -*- coding: utf-8 -*-
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import store  # noqa: E402


def make_data(root):
    os.makedirs(os.path.join(root, "posts", "20261019-a", "photos"))
    os.makedirs(os.path.join(root, "voice"))
    with open(os.path.join(root, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"voice_note": "반말"}, f)
    with open(os.path.join(root, "ledger.json"), "w", encoding="utf-8") as f:
        json.dump([{"id": "1", "amount": 1000}], f)
    with open(os.path.join(root, "posts", "20261019-a", "memo.txt"), "w", encoding="utf-8") as f:
        f.write("개월 수: 생후 5개월 (163일)")
    with open(os.path.join(root, "posts", "20261019-a", "photos", "p.jpg"), "wb") as f:
        f.write(b"x" * 100)
    with open(os.path.join(root, "voice", "v.txt"), "w", encoding="utf-8") as f:
        f.write("내 글")
    with open(os.path.join(root, "config.json.tmp"), "w") as f:      # 임시 파일은 빠져야 한다
        f.write("x")


class PlatformDirsTest(unittest.TestCase):
    """기본 데이터 자리 — OS 마다(어느 OS 에서 돌려도 같은 답이 나오게 platform·home 을 넘긴다)."""

    def test_windows(self):
        env = {"APPDATA": os.path.join("C:", "R"), "LOCALAPPDATA": os.path.join("C:", "L")}
        data, local, logs = store.default_dirs("PostKit", env, "win32", home="H")
        self.assertEqual((data, local, logs), (os.path.join(env["APPDATA"], "PostKit"),) + (os.path.join(env["LOCALAPPDATA"], "PostKit"),) * 2)

    def test_mac(self):
        data, local, logs = store.default_dirs("PostKit", {}, "darwin", home="/Users/me")
        self.assertEqual(data, os.path.join("/Users/me", "Library", "Application Support", "PostKit"))
        self.assertEqual(local, os.path.join("/Users/me", "Library", "Application Support", "PostKit-local"))
        self.assertEqual(logs, os.path.join("/Users/me", "Library", "Logs", "PostKit"))
        self.assertNotEqual(data, local)             # 자동 백업이 데이터 폴더 안에 쌓이지 않게

    def test_mac_cloud_folders(self):
        with tempfile.TemporaryDirectory() as home:
            cs = os.path.join(home, "Library", "CloudStorage")
            for d in ("OneDrive-Personal", "OneDrive-회사", os.path.join("GoogleDrive-me@example.com", "내 드라이브")):
                os.makedirs(os.path.join(cs, d))
            os.makedirs(os.path.join(home, "Library", "Mobile Documents", "com~apple~CloudDocs"))
            names = [c["name"] for c in store.cloud_folders("darwin", home)]
            self.assertEqual(names, ["구글 드라이브", "OneDrive(개인)", "iCloud Drive"])      # 회사 OneDrive 는 빼고
            self.assertTrue(store.company_onedrive("darwin", home).endswith("OneDrive-회사"))
            self.assertEqual(store.cloud_folders("linux", home), [])


class LocationTest(unittest.TestCase):
    def test_location_and_target(self):
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cloud:
            self.assertEqual(store.load_location(home), "")
            store.save_location(home, cloud)
            self.assertEqual(store.load_location(home), cloud)
            store.save_location(home, home)                         # 기본 자리로 돌아가면 기록을 지운다
            self.assertEqual(store.load_location(home), "")
            self.assertEqual(store.target_dir(cloud), os.path.join(os.path.abspath(cloud), "PostKit"))
            make_data(cloud)
            self.assertEqual(store.target_dir(cloud), os.path.abspath(cloud))    # 이미 데이터가 있으면 그대로

    def test_copy(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_data(a)
            n = store.copy_data(a, os.path.join(b, "PostKit"))
            self.assertEqual(n, 5)
            self.assertTrue(os.path.isfile(os.path.join(b, "PostKit", "posts", "20261019-a", "photos", "p.jpg")))
            self.assertFalse(os.path.exists(os.path.join(b, "PostKit", "config.json.tmp")))


class BackupTest(unittest.TestCase):
    def test_zip_restore(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_data(a)
            z = os.path.join(b, "full.zip")
            self.assertEqual(store.make_zip(a, z, photos=True), 5)
            self.assertEqual(store.make_zip(a, os.path.join(b, "nophoto.zip"), photos=False), 4)
            dst = os.path.join(b, "restored")
            os.makedirs(dst)
            with open(os.path.join(dst, "keep.txt"), "w") as f:
                f.write("x")
            self.assertEqual(store.restore_zip(z, dst), 5)
            with open(os.path.join(dst, "ledger.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)[0]["amount"], 1000)
            self.assertTrue(os.path.exists(os.path.join(dst, "keep.txt")))

    def test_bad_zip(self):
        with tempfile.TemporaryDirectory() as b:
            for names in (["../evil.txt"], ["posts/../../evil.txt"], ["C:/evil.txt"], ["other/x.txt"]):
                p = os.path.join(b, "bad.zip")
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr("postkit-backup.json", "{}")
                    for n in names:
                        z.writestr(n, "x")
                with self.assertRaises(ValueError):
                    store.restore_zip(p, os.path.join(b, "out"))
            p = os.path.join(b, "notours.zip")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("config.json", "{}")
            with self.assertRaises(ValueError):
                store.restore_zip(p, os.path.join(b, "out"))

    def test_auto_backup(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            make_data(a)
            for d in range(1, 10):
                store.auto_backup(a, b, keep=7, today=datetime(2026, 10, d))
            self.assertEqual(store.auto_backup(a, b, keep=7, today=datetime(2026, 10, 9)), "")   # 같은 날은 한 번
            files = sorted(os.listdir(b))
            self.assertEqual(len(files), 7)
            self.assertEqual(files[0], "auto-20261003.zip")


class GrowthTest(unittest.TestCase):
    def test_entry_and_compose(self):
        memo = "개월 수: 생후 5개월 (163일)\n오늘의 장면: 손 잡고 잠듦\n첫째: 뒤집기\n둘째: \n새로 한 것(뒤집기·이유식·첫걸음 등): 뒤집기\n날짜: 2026년 10월 18일 (일)"
        e = store.growth_entry("a", memo, ["p.jpg"])
        self.assertEqual((e["month"], e["second"], e["new"], e["photo"]), (5, "", "뒤집기", "p.jpg"))
        self.assertIsNone(store.growth_entry("b", "그냥 메모", []))
        e2 = store.growth_entry("c", "개월 수: 생후 3개월 (100일)\n오늘의 장면: 백일", [])
        m = store.compose_memo([e, e2], ["콩이", "팥이"])
        self.assertIn("생후 3개월부터 5개월까지", m)
        self.assertLess(m.index("백일"), m.index("손 잡고"))           # 개월 순서
        self.assertIn("콩이: 뒤집기", m)
        self.assertNotIn("팥이:", m)                                    # 빈 칸은 안 넣는다


if __name__ == "__main__":
    unittest.main()
